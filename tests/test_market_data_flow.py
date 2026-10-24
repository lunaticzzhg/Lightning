from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from backend.app.api import create_app
from backend.infra.database import ensure_schema


def client(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "db.sqlite"}')
    ensure_schema(engine)
    api = TestClient(create_app(engine, market_dir=tmp_path / 'market'))
    token = api.get('/api/status').json()['token']
    return api, {'X-Lightning-Token': token}

def upload(api, headers, csv):
    response = api.post('/api/market/drafts', files={'file': ('daily.csv', csv, 'text/csv')}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()['draft_id']

def choice():
    return {'provider':'测试提供方','product':'日线','price_mode':'raw','volume_unit':'shares'}

def test_version_compare_and_old_read(tmp_path):
    api, headers = client(tmp_path)
    first = upload(api, headers, 'symbol,exchange,date,open,high,low,close,volume\n600000,SH,2026-10-23,10,11,9,10,100\n')
    result = api.post(f'/api/market/drafts/{first}/publish', json=choice(), headers=headers)
    assert result.status_code == 200, result.text
    v1 = result.json()
    search = api.get('/api/market/search', params={'symbol':'600000','period':'day','from_date':'2026-10-23','to_date':'2026-10-23'}).json()
    assert search['reason'] == 'found'
    second = upload(api, headers, 'symbol,exchange,date,open,high,low,close,volume\n600000,SH,2026-10-23,10,11,9,10,100\n600000,SH,2026-10-26,12,13,11,12,200\n')
    result = api.post(f'/api/market/drafts/{second}/publish', json=choice(), headers=headers)
    assert result.status_code == 200, result.text
    v2 = result.json()
    assert v2['version_number'] == 2 and v2['added'] == 1
    first_bars = api.get(f"/api/market/datasets/{v1['dataset_id']}/versions/{v1['version_id']}/chart", params={'symbol':'600000','from_date':'2026-10-26','to_date':'2026-10-26'}).json()['bars']
    assert first_bars == []
    update = upload(api, headers, 'symbol,exchange,date,open,high,low,close,volume\n600000,SH,2026-10-23,10,12,9,10,100\n')
    comparison = api.post(f'/api/market/drafts/{update}/compare', json=choice(), headers=headers).json()
    assert comparison['status'] == 'changes' and comparison['changed'] == 1
    assert api.post(f'/api/market/drafts/{update}/publish', json=choice(), headers=headers).json()['status'] == 'changes'
    confirmed = api.post(f'/api/market/drafts/{update}/publish', json={**choice(),'confirmation':comparison['confirmation']}, headers=headers).json()
    assert confirmed['version_number'] == 3
    assert api.post(f'/api/market/drafts/{update}/publish', json={**choice(),'confirmation':comparison['confirmation']}, headers=headers).json() == confirmed
    old = api.get(f"/api/market/datasets/{v1['dataset_id']}/versions/{v1['version_id']}/chart", params={'symbol':'600000','from_date':'2026-10-23','to_date':'2026-10-23'}).json()
    new = api.get(f"/api/market/datasets/{v1['dataset_id']}/versions/{confirmed['version_id']}/chart", params={'symbol':'600000','from_date':'2026-10-23','to_date':'2026-10-23'}).json()
    assert old['bars'][0]['high'] == '11' and new['bars'][0]['high'] == '12'

def test_minute_conversion_and_invalid(tmp_path):
    api, headers = client(tmp_path)
    draft = upload(api, headers, 'symbol,exchange,timestamp,open,high,low,close,volume\nAAPL,NASDAQ,2026-07-01T09:31:00-04:00,10,11,9,10,2\n')
    preview = api.post(f'/api/market/drafts/{draft}/preview', json={'volume_unit':'shares','minute_position':'end'}, headers=headers)
    assert preview.status_code == 200, preview.text
    assert preview.json()['examples'][0]['market_time'].startswith('2026-07-01T09:30')
    assert preview.json()['examples'][0]['volume'] == '2'
    invalid = api.post('/api/market/drafts', files={'file':('bad.csv','symbol,exchange,date,open,high,low,close,volume\nAAPL,NASDAQ,2026-07-04,10,11,9,10,1\n')}, headers=headers)
    assert invalid.status_code == 201
    result = api.post(f"/api/market/drafts/{invalid.json()['draft_id']}/publish", json=choice(), headers=headers)
    assert result.status_code == 400

def test_duplicate_and_corrupt_file(tmp_path):
    api, headers = client(tmp_path)
    csv = 'symbol,exchange,date,open,high,low,close,volume\n600000,SH,2026-10-23,10,11,9,10,100\n'
    first = upload(api, headers, csv)
    created = api.post(f'/api/market/drafts/{first}/publish', json=choice(), headers=headers).json()
    duplicate = upload(api, headers, csv)
    unchanged = api.post(f'/api/market/drafts/{duplicate}/compare', json=choice(), headers=headers).json()
    assert unchanged['status'] == 'unchanged'
    assert len(api.get(f"/api/market/datasets/{created['dataset_id']}/versions").json()) == 1
    for path in (tmp_path/'market'/'bars').rglob('*.parquet'):
        path.chmod(0o644)
        path.write_bytes(b'corrupt')
    assert api.get('/api/market/search', params={'symbol':'600000','period':'day','from_date':'2026-10-23','to_date':'2026-10-23'}).json()['reason'] == 'found'
    response = api.get(f"/api/market/datasets/{created['dataset_id']}/versions/{created['version_id']}/chart", params={'symbol':'600000','from_date':'2026-10-23','to_date':'2026-10-23'})
    assert response.status_code == 503 and response.json()['code'] == 'version_unreadable'

def test_configured_observation_and_weekend(tmp_path, monkeypatch):
    monkeypatch.setenv('LIGHTNING_MARKET_PRICE_ALERT_RATIO', '2')
    api, headers = client(tmp_path)
    draft = upload(api, headers, 'symbol,exchange,date,open,high,low,close,volume\n600000,SH,2026-10-22,10,10,10,10,1\n600000,SH,2026-10-23,20,20,20,20,1\n')
    result = api.post(f'/api/market/drafts/{draft}/publish', json=choice(), headers=headers).json()
    chart = api.get(f"/api/market/datasets/{result['dataset_id']}/versions/{result['version_id']}/chart", params={'symbol':'600000','from_date':'2026-10-23','to_date':'2026-10-23'}).json()
    assert chart['warnings'][0]['kind'] == 'price_change'
    weekend = api.get('/api/market/search', params={'symbol':'600000','period':'day','from_date':'2026-10-24','to_date':'2026-10-24'}).json()
    assert weekend['reason'] == 'closed_day'

def test_same_symbol_on_two_exchanges_is_separate(tmp_path):
    api, headers = client(tmp_path)
    draft = upload(api, headers, 'symbol,exchange,date,open,high,low,close,volume\nABC,NYSE,2026-10-23,10,11,9,10,1\nABC,NASDAQ,2026-10-23,20,21,19,20,1\n')
    result = api.post(f'/api/market/drafts/{draft}/publish', json=choice(), headers=headers).json()
    found = api.get('/api/market/search', params={'symbol':'ABC','period':'day','from_date':'2026-10-23','to_date':'2026-10-23'}).json()
    assert {r['exchange'] for r in found['results']} == {'NYSE','NASDAQ'}
    endpoint = f"/api/market/datasets/{result['dataset_id']}/versions/{result['version_id']}/chart"
    assert api.get(endpoint, params={'symbol':'ABC','from_date':'2026-10-23','to_date':'2026-10-23'}).status_code == 400
    chart = api.get(endpoint, params={'symbol':'ABC','from_date':'2026-10-23','to_date':'2026-10-23','exchange':'NASDAQ'}).json()
    assert len(chart['bars']) == 1 and chart['bars'][0]['close'] == '20'

def test_numeric_equivalence_is_not_a_correction(tmp_path):
    api, headers = client(tmp_path)
    original = upload(api, headers, 'symbol,exchange,date,open,high,low,close,volume\n600000,SH,2026-10-23,10,11,9,10,100\n')
    api.post(f'/api/market/drafts/{original}/publish', json=choice(), headers=headers)
    next_draft = upload(api, headers, 'symbol,exchange,date,open,high,low,close,volume\n600000,SH,2026-10-23,10.00,11.0,9.0,10.0,100.0\n')
    compared = api.post(f'/api/market/drafts/{next_draft}/compare', json=choice(), headers=headers).json()
    assert compared['status'] == 'unchanged'

def test_repository_minute_sample_infers_a_share_exchange(tmp_path):
    from pathlib import Path
    api, headers = client(tmp_path)
    raw = Path('docs/requirements/REQ-002/samples/new-minutes.csv').read_bytes()
    response = api.post('/api/market/drafts', files={'file':('new-minutes.csv', raw, 'text/csv')}, headers=headers)
    assert response.status_code == 201, response.text
    staged = response.json()
    assert staged['market'] == 'CN' and not staged['needs_exchange'] and staged['symbols'] == ['SH:600519']
    draft_id = staged['draft_id']
    preview = api.post(f'/api/market/drafts/{draft_id}/preview', json={'volume_unit':'shares','minute_position':'start'}, headers=headers)
    assert preview.status_code == 200, preview.text
    assert preview.json()['examples'][0]['exchange'] == 'SH'
    published = api.post(f'/api/market/drafts/{draft_id}/publish', json={**choice(),'minute_position':'start'}, headers=headers)
    assert published.status_code == 200 and published.json()['status'] == 'published', published.text


def test_us_exchange_confirmation_and_unit_restriction(tmp_path):
    api, headers = client(tmp_path)
    csv = 'symbol,timestamp,open,high,low,close,volume\nAAPL,2026-07-01T09:31:00-04:00,10,11,9,10,2\n'
    staged_response = api.post('/api/market/drafts', files={'file':('us.csv',csv,'text/csv')}, headers=headers)
    assert staged_response.status_code == 201, staged_response.text
    assert staged_response.json()['needs_exchange'] and 'exchange' in staged_response.json()['needs']
    draft = staged_response.json()['draft_id']
    staged = api.get(f'/api/market/drafts/{draft}/result').json()
    assert staged['status'] == 'pending'
    assert api.post(f'/api/market/drafts/{draft}/preview', json={'volume_unit':'shares','minute_position':'start'}, headers=headers).status_code == 400
    assert api.post(f'/api/market/drafts/{draft}/preview', json={'volume_unit':'lots100','minute_position':'start','exchange':'NASDAQ'}, headers=headers).status_code == 400
    confirmed = api.post(f'/api/market/drafts/{draft}/preview', json={'volume_unit':'shares','minute_position':'start','exchange':'NASDAQ'}, headers=headers)
    assert confirmed.status_code == 200 and confirmed.json()['examples'][0]['exchange'] == 'NASDAQ'
    published = api.post(f'/api/market/drafts/{draft}/publish', json={**choice(),'minute_position':'start','exchange':'NASDAQ'}, headers=headers)
    assert published.status_code == 200, published.text
    assert published.json()['symbols'] == ['NASDAQ:AAPL']


def test_explicit_exchange_cannot_contradict_symbol(tmp_path):
    api, headers = client(tmp_path)
    for symbol,exchange in [('AAPL','SH'),('600519','SZ')]:
        csv = f'symbol,exchange,date,open,high,low,close,volume\n{symbol},{exchange},2026-10-22,10,11,9,10,1\n'
        response = api.post('/api/market/drafts', files={'file':('wrong.csv',csv,'text/csv')}, headers=headers)
        assert response.status_code == 400 and 'exchange' in response.json()['message']


def test_daily_range_and_import_history(tmp_path):
    api, headers = client(tmp_path)
    first = upload(api, headers, 'symbol,exchange,date,open,high,low,close,volume\n600000,SH,2026-10-22,10,11,9,10,1\n')
    initial = api.post(f'/api/market/drafts/{first}/publish', json=choice(), headers=headers).json()
    second = upload(api, headers, 'symbol,exchange,date,open,high,low,close,volume\n600000,SH,2026-10-26,12,13,11,12,1\n')
    updated = api.post(f'/api/market/drafts/{second}/publish', json=choice(), headers=headers).json()
    params = {'symbol':'600000','period':'day','from_date':'2026-10-22','to_date':'2026-10-26'}
    assert api.get('/api/market/search', params=params).json()['results'][0]['has_bars']
    endpoint = f"/api/market/datasets/{updated['dataset_id']}/versions/{updated['version_id']}/chart"
    bars = api.get(endpoint, params={'symbol':'600000','from_date':'2026-10-22','to_date':'2026-10-26'}).json()['bars']
    assert [bar['market_time'][:10] for bar in bars] == ['2026-10-22','2026-10-26']
    history = api.get(f"/api/market/versions/{updated['version_id']}/import-record").json()
    assert len(history['files']) == 2 and history['previous_version_id'] == initial['version_id']
    old = api.get(f"/api/market/datasets/{initial['dataset_id']}/versions/{initial['version_id']}/chart", params={'symbol':'600000','from_date':'2026-10-22','to_date':'2026-10-26'}).json()
    assert len(old['bars']) == 1


def test_repository_daily_sample(tmp_path):
    api, headers = client(tmp_path)
    raw = Path('docs/requirements/REQ-002/samples/new-daily.csv').read_bytes()
    response = api.post('/api/market/drafts', files={'file':('new-daily.csv',raw,'text/csv')}, headers=headers)
    assert response.status_code == 201, response.text
    staged = response.json()
    assert staged['market'] == 'CN' and staged['period'] == 'day' and not staged['needs_exchange']
    published = api.post(f"/api/market/drafts/{staged['draft_id']}/publish", json=choice(), headers=headers)
    assert published.status_code == 200 and published.json()['status'] == 'published', published.text


def test_stale_correction_requires_fresh_comparison(tmp_path):
    api, headers = client(tmp_path)
    csv = 'symbol,exchange,date,open,high,low,close,volume\n600000,SH,2026-10-22,10,11,9,10,1\n'
    first = upload(api, headers, csv)
    api.post(f'/api/market/drafts/{first}/publish', json=choice(), headers=headers)
    correction = upload(api, headers, csv.replace('10,11,9,10', '10,12,9,10'))
    old_comparison = api.post(f'/api/market/drafts/{correction}/compare', json=choice(), headers=headers).json()
    assert old_comparison['status'] == 'changes'
    other = upload(api, headers, 'symbol,exchange,date,open,high,low,close,volume\n600000,SH,2026-10-23,12,13,11,12,1\n')
    api.post(f'/api/market/drafts/{other}/publish', json=choice(), headers=headers)
    current = api.post(f'/api/market/drafts/{correction}/publish', json={**choice(), 'confirmation':old_comparison['confirmation']}, headers=headers)
    assert current.status_code == 200 and current.json()['status'] == 'changes'
    fresh = api.post(f'/api/market/drafts/{correction}/compare', json=choice(), headers=headers).json()
    assert fresh['confirmation'] != old_comparison['confirmation']
    confirmed = api.post(f'/api/market/drafts/{correction}/publish', json={**choice(), 'confirmation':fresh['confirmation']}, headers=headers)
    assert confirmed.status_code == 200 and confirmed.json()['version_number'] == 3


def test_target_mismatch_reported_at_stage(tmp_path):
    api, headers = client(tmp_path)
    first = upload(api, headers, 'symbol,exchange,date,open,high,low,close,volume\n600000,SH,2026-10-22,10,11,9,10,1\n')
    dataset = api.post(f'/api/market/drafts/{first}/publish', json=choice(), headers=headers).json()['dataset_id']
    response = api.post('/api/market/drafts', params={'target_dataset_id':dataset}, files={'file':('minutes.csv','symbol,timestamp,open,high,low,close,volume\n600000,2026-10-22T09:31:00+08:00,10,11,9,10,1\n','text/csv')}, headers=headers)
    assert response.status_code == 201 and response.json()['target_mismatch']
    assert response.json()['draft_id']
