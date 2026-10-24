"""Exercise the running local Compose stack using its browser-facing HTTP API."""
import hashlib
import io
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor

BASE = os.environ.get('LIGHTNING_SMOKE_BASE', 'http://127.0.0.1:8000')
COMPOSE = ['docker', 'compose', '-f', 'deploy/local/compose.yaml']
if os.environ.get('LIGHTNING_COMPOSE_PROJECT'):
    COMPOSE.extend(['-p', os.environ['LIGHTNING_COMPOSE_PROJECT']])


def call(path, method='GET', data=None, headers=None):
    request = urllib.request.Request(BASE + path, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def pack(name):
    body = io.BytesIO()
    manifest = {'schema_version': 1, 'interface_version': 1, 'name': name,
                'description': '容器验证', 'markets': ['US'], 'bar_interval': '1m',
                'required_fields': ['close'], 'entrypoint': 'strategy:on_bar',
                'python': '3.13', 'dependencies': [],
                'parameters': [{'name': 'window', 'type': 'integer', 'required': True,
                                'default': 5, 'min': 1, 'max': 20}]}
    with zipfile.ZipFile(body, 'w') as archive:
        archive.writestr('strategy.json', json.dumps(manifest, ensure_ascii=False))
        archive.writestr('strategy.py', 'def on_bar(event):\n    return None\n')
    return body.getvalue()


def upload(path, content, token, filename='demo.zip', media_type='application/zip'):
    boundary = uuid.uuid4().hex
    data = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f'Content-Type: {media_type}\r\n\r\n').encode() + content + f'\r\n--{boundary}--\r\n'.encode()
    return call(path, 'POST', data, {'Content-Type': f'multipart/form-data; boundary={boundary}', 'X-Lightning-Token': token})


def main():
    for attempt in range(30):
        try:
            if call('/api/status')[0] == 200:
                break
        except OSError:
            pass
        if attempt == 29:
            raise RuntimeError('本地应用未就绪')
        time.sleep(0.2)
    status, data = call('/api/status')
    assert status == 200, (status, data)
    token = json.loads(data)['token']
    original = pack('容器验证_' + uuid.uuid4().hex[:8])
    assert upload('/api/strategies', original, 'wrong')[0] == 403
    status, data = upload('/api/strategies', original, token)
    assert status == 201, (status, data)
    version = json.loads(data)
    assert version['sha256'] == hashlib.sha256(original).hexdigest()
    assert upload('/api/strategies', original, token)[0] == 409
    assert call(f"/api/versions/{version['id']}/download")[1] == original
    daily = b'symbol,exchange,date,open,high,low,close,volume\n600000,SH,2026-10-23,10,11,9,10,100\n'
    status, data = upload('/api/market/drafts', daily, token, 'daily.csv', 'text/csv')
    assert status == 201, (status, data)
    draft = json.loads(data)['draft_id']
    choice = {'provider':'容器验证提供方_'+uuid.uuid4().hex[:8], 'product':'日线', 'price_mode':'raw', 'volume_unit':'shares'}
    status, data = call(f'/api/market/drafts/{draft}/publish', 'POST', json.dumps(choice).encode(),
                        {'Content-Type':'application/json', 'X-Lightning-Token':token})
    assert status == 200 and json.loads(data)['status'] == 'published', (status, data)
    market_version = json.loads(data)
    revision = b'symbol,exchange,date,open,high,low,close,volume\n600000,SH,2026-10-22,9,10,8,9,80\n'
    status, data = upload('/api/market/drafts', revision, token, 'revision.csv', 'text/csv')
    assert status == 201, (status, data)
    revision_draft = json.loads(data)['draft_id']
    def publish_revision():
        return call(f'/api/market/drafts/{revision_draft}/publish', 'POST', json.dumps(choice).encode(),
                    {'Content-Type':'application/json', 'X-Lightning-Token':token})
    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = list(pool.map(lambda _: publish_revision(), range(2)))
    assert all(code == 200 for code, _ in answers), answers
    assert len({json.loads(body)['version_id'] for _, body in answers}) == 1, answers
    assert len(json.loads(call(f"/api/market/datasets/{market_version['dataset_id']}/versions")[1])) == 2
    assert json.loads(call('/api/market/search?symbol=600000&period=day&from_date=2026-10-23&to_date=2026-10-23')[1])['reason'] == 'found'
    subprocess.run([*COMPOSE, 'restart', 'app'], check=True, capture_output=True)
    for _ in range(20):
        try:
            if call('/api/status')[0] == 200:
                break
        except OSError:
            time.sleep(0.2)
    status, data = call(f"/api/versions/{version['id']}")
    assert status == 200 and json.loads(data)['version']['id'] == version['id']
    assert call(f"/api/versions/{version['id']}/download")[1] == original
    chart_path = f"/api/market/datasets/{market_version['dataset_id']}/versions/{market_version['version_id']}/chart?symbol=600000&from_date=2026-10-23&to_date=2026-10-23"
    status, data = call(chart_path)
    assert status == 200 and json.loads(data)['bars'][0]['close'] == '10', (status, data)
    print(json.dumps({'strategy_version_id': version['id'], 'market_version_id': market_version['version_id']}))


if __name__ == '__main__':
    main()
