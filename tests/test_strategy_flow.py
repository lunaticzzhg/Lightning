import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import pytest
from sqlalchemy import create_engine, func, select

from backend.app.api import create_app
from backend.features.strategies.manifest import Manifest
from backend.features.strategies.package import PackageError, validate_package
from backend.infra.database import ensure_schema, strategies, versions


def package(name='示例策略', source='def on_bar(event):\n    return None\n', parameters=None, overrides=None):
    manifest = {
        'schema_version': 1, 'interface_version': 1, 'name': name, 'description': '静态测试',
        'markets': ['US'], 'bar_interval': '1m', 'required_fields': ['close'],
        'entrypoint': 'strategy:on_bar', 'python': '3.13', 'dependencies': [],
        'parameters': parameters if parameters is not None else [
            {'name': 'window', 'type': 'integer', 'required': True, 'default': 5, 'min': 1, 'max': 20},
        ],
    }
    manifest.update(overrides or {})
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as archive:
        archive.writestr('strategy.json', json.dumps(manifest, ensure_ascii=False))
        archive.writestr('strategy.py', source)
    return out.getvalue()


def client(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "db.sqlite"}')
    ensure_schema(engine)
    test = TestClient(create_app(engine))
    test.headers.update({'X-Lightning-Token': test.get('/api/status').json()['token']})
    return test, engine


def upload(test, data, url='/api/strategies'):
    return test.post(url, files={'file': ('example.zip', data, 'application/zip')})


def test_published_manifest_schema_matches_runtime_contract():
    path = Path(__file__).resolve().parents[1] / 'contracts/strategy/strategy.schema.json'
    published = json.loads(path.read_text())
    assert published == Manifest.model_json_schema()
    validator = Draft202012Validator(published)
    properties = published['properties']
    for name in ('markets', 'required_fields', 'dependencies'):
        assert properties[name]['uniqueItems'] is True
    assert properties['dependencies']['items']['minLength'] == 1
    assert properties['dependencies']['items']['maxLength'] == 200
    assert published['$defs']['EnumParameter']['properties']['options']['uniqueItems'] is True
    assert published['$defs']['EnumParameter']['properties']['options']['items']['minLength'] == 1

    valid = json.loads(zipfile.ZipFile(io.BytesIO(package())).read('strategy.json'))
    for kind in ('integer', 'number', 'boolean', 'string', 'enum'):
        fields = ('default', 'min', 'max') if kind in ('integer', 'number') else ('default',)
        for field in fields:
            invalid = json.loads(json.dumps(valid))
            parameter = {'name': 'x', 'type': kind, 'required': True, field: None}
            if kind == 'enum':
                parameter['options'] = ['choice']
            invalid['parameters'] = [parameter]
            assert not validator.is_valid(invalid), (kind, field)
            with pytest.raises(PackageError):
                validate_package(package(parameters=invalid['parameters']))
    assert validator.is_valid(valid)


def test_versions_and_download(tmp_path):
    test, engine = client(tmp_path)
    original = package()
    first_response = upload(test, original)
    assert first_response.status_code == 201
    first = first_response.json()
    sid = first['strategy_id']
    assert first['number'] == 1 and first['status'] == '已导入，未运行验证'
    assert upload(test, original).status_code == 409
    assert upload(test, original, f'/api/strategies/{sid}/versions').status_code == 409
    assert upload(test, package('其他策略'), f'/api/strategies/{sid}/versions').status_code == 400
    assert upload(test, package(' 示例策略 ')).status_code == 409
    second = upload(test, package(source='def on_bar(event):\n    return []\n', parameters=[]), f'/api/strategies/{sid}/versions').json()
    assert second['number'] == 2
    download = test.get(f"/api/versions/{first['id']}/download")
    assert download.content == original
    assert download.headers['content-type'] == 'application/octet-stream'
    assert 'example.zip' in download.headers['content-disposition']
    missing = test.get('/api/versions/missing/download')
    assert missing.status_code == 404 and missing.json()['code'] == 'not_found'
    assert test.get(f"/api/versions/{first['id']}").json()['version']['manifest']['parameters'][0]['name'] == 'window'
    assert test.get(f"/api/versions/{second['id']}").json()['version']['manifest']['parameters'] == []
    assert test.get(f'/api/strategies/{sid}').json()['versions'][0]['id'] == second['id']
    assert test.get('/api/strategies').json()[0]['version_count'] == 2
    with engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(versions)) == 2
        assert set(db.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").scalars()) >= {'strategies', 'versions'}
        assert 'configs' not in set(db.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").scalars())
    assert test.post(f"/api/versions/{first['id']}/configs", json={'name':'x','values':{}}).status_code == 405


def test_invalid_upload_is_atomic(tmp_path):
    test, engine = client(tmp_path)
    invalid = [b'not zip', package(overrides={'markets':['CRYPTO']}), package(overrides={'parameters':[{'name':'api_key','type':'string','required':True}]}), package(source='def other(event): pass')]
    bad_path = io.BytesIO()
    with zipfile.ZipFile(bad_path, 'w') as archive:
        archive.writestr('../strategy.json', '{}')
        archive.writestr('strategy.py', 'def on_bar(event): pass')
    invalid.append(bad_path.getvalue())
    for data in invalid:
        assert upload(test, data).status_code == 400
    assert test.get('/api/strategies').json() == []
    with engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(strategies)) == 0
        assert db.scalar(select(func.count()).select_from(versions)) == 0


def test_concurrent_duplicate(tmp_path):
    test, engine = client(tmp_path)
    body = package()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: upload(test, body).status_code, range(4)))
    assert sorted(results) == [201, 409, 409, 409]
    with engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(strategies)) == 1
        assert db.scalar(select(func.count()).select_from(versions)) == 1


def test_guard_and_database_failure(tmp_path):
    test, _ = client(tmp_path)
    schema = test.get('/api/openapi.json')
    assert schema.status_code == 200
    assert '/api/strategies/{strategy_id}/versions' in schema.json()['paths']
    paths = schema.json()['paths']
    manifest = schema.json()['components']['schemas']['Manifest']
    assert manifest['properties']['parameters']['items']['discriminator']['propertyName'] == 'type'
    assert manifest['properties']['markets']['items']['enum'] == ['CN', 'US']
    for path in ('/api/strategies', '/api/strategies/{strategy_id}/versions'):
        operation = paths[path]['post']
        assert any(p['name'] == 'X-Lightning-Token' and p['in'] == 'header' and p['required'] for p in operation['parameters'])
        assert operation['requestBody']['content']['multipart/form-data']['schema']
        assert operation['responses']['403']['content']['application/json']['schema']['$ref'].endswith('/Error')
    binary = paths['/api/versions/{version_id}/download']['get']['responses']['200']['content']['application/octet-stream']['schema']
    assert binary == {'type': 'string', 'format': 'binary'}
    assert upload(test, package()).status_code == 201
    assert test.post('/api/strategies', files={'file': ('x.zip', package())}, headers={'X-Lightning-Token': 'wrong'}).status_code == 403
    assert test.post('/api/strategies', files={'file': ('x.zip', package())}, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert test.get('/api/status', headers={'Host': 'untrusted.example'}).status_code == 403
    unavailable = TestClient(create_app(create_engine(f'sqlite:///{tmp_path / "missing" / "db.sqlite"}')))
    assert unavailable.get('/health/live').status_code == 200
    assert unavailable.get('/api/status').status_code == 503
