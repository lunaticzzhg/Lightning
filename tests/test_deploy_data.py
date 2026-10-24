from backend.infra.database import metadata, now, strategies
from scripts import deploy_data, snapshot
from sqlalchemy import create_engine


def test_failed_backup_restarts_previous_app(tmp_path, monkeypatch):
    calls = []

    def fake_compose(_file, *args, **_kwargs):
        calls.append(args)
        if args[:3] == ('ps', '--status', 'running'):
            return 'app\n'
        if args[:3] == ('exec', '-T', 'db'):
            raise RuntimeError('dump failed')
        return ''

    monkeypatch.setattr(deploy_data, 'compose', fake_compose)
    monkeypatch.setattr(deploy_data, 'source_snapshot', lambda *_args: {'counts': {}, 'sha256': 'x'})
    destination = tmp_path / 'backup.sql'

    try:
        deploy_data.backup(tmp_path / 'compose.yaml', destination)
    except RuntimeError as exc:
        assert str(exc) == 'dump failed'
    else:
        assert False, '备份失败必须向调用方报错'

    assert ('up', '-d', '--no-deps', 'app') in calls
    assert not destination.exists()
    assert not (tmp_path / 'backup.sql.partial').exists()


def test_business_fingerprint_ignores_future_columns(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path / "data.sqlite"}'
    engine = create_engine(url)
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(strategies.insert().values(
            id='strategy-1', name='示例', canonical_name='示例', created_at=now()))
    monkeypatch.setattr(snapshot, 'database_url', lambda: url)
    before = snapshot.snapshot()
    with engine.begin() as connection:
        connection.exec_driver_sql('ALTER TABLE strategies ADD COLUMN future_note TEXT DEFAULT "new"')
    assert snapshot.snapshot() == before
    engine.dispose()


def test_market_snapshot_checks_referenced_files(tmp_path, monkeypatch):
    from backend.features.market_data import service
    from backend.features.market_data.storage import Store
    from types import SimpleNamespace
    url = f'sqlite:///{tmp_path / "market.sqlite"}'
    engine = create_engine(url)
    metadata.create_all(engine)
    store = Store(tmp_path / 'files')
    staged = service.stage(engine, store, 'daily.csv', b'symbol,exchange,date,open,high,low,close,volume\n600000,SH,2026-10-23,10,11,9,10,1\n')
    service.publish(engine, store, staged['draft_id'], SimpleNamespace(provider='P',product='D',price_mode='raw',adjustment='',reference_date='',volume_unit='shares',minute_position=None,exchange=None,target_dataset_id=None))
    monkeypatch.setattr(snapshot, 'database_url', lambda: url)
    monkeypatch.setenv('LIGHTNING_MARKET_DIR', str(tmp_path / 'files'))
    assert snapshot.snapshot()['counts']['market_versions'] == 1
    next((tmp_path / 'files' / 'bars').rglob('*.parquet')).unlink()
    try:
        snapshot.snapshot()
    except RuntimeError as exc:
        assert '版本文件缺失' in str(exc)
    else:
        assert False, '备份前必须检查行情文件'
    engine.dispose()


def test_prune_expired_draft_keeps_published_original(tmp_path):
    from datetime import timedelta
    from sqlalchemy import select, update
    from backend.infra.database import market_drafts, market_imports
    from backend.features.market_data import service
    from backend.features.market_data.storage import Store
    from scripts.prune_market import prune
    from types import SimpleNamespace
    url = f'sqlite:///{tmp_path / "prune.sqlite"}'
    engine = create_engine(url)
    metadata.create_all(engine)
    store = Store(tmp_path / 'files')
    published_raw = b'symbol,exchange,date,open,high,low,close,volume\n600000,SH,2026-10-22,10,11,9,10,1\n'
    first = service.stage(engine, store, 'published.csv', published_raw)
    service.publish(engine, store, first['draft_id'], SimpleNamespace(provider='P',product='D',price_mode='raw',adjustment='',reference_date='',volume_unit='shares',minute_position=None,exchange=None,target_dataset_id=None))
    duplicate = service.stage(engine, store, 'duplicate.csv', published_raw)
    orphan = service.stage(engine, store, 'orphan.csv', b'symbol,exchange,date,open,high,low,close,volume\n600000,SH,2026-10-23,10,11,9,10,1\n')
    with engine.begin() as db:
        rows = db.execute(select(market_drafts.c.id, market_drafts.c.raw_path)).all()
        paths = {row.id:row.raw_path for row in rows}
        db.execute(update(market_drafts).where(market_drafts.c.id.in_([duplicate['draft_id'],orphan['draft_id']])).values(created_at=now()-timedelta(days=3)))
    result = prune(engine, store)
    assert result == {'expired_drafts':2, 'removed_originals':1}
    assert (store.root / paths[first['draft_id']]).exists()
    assert not (store.root / paths[orphan['draft_id']]).exists()
    abandoned_path, _ = store.original(b'abandoned upload')
    assert prune(engine, store) == {'expired_drafts':0, 'removed_originals':1}
    assert not (store.root / abandoned_path).exists()
    assert (store.root / paths[first['draft_id']]).exists()
    with engine.connect() as db:
        assert len(db.execute(select(market_imports)).all()) == 1
    engine.dispose()
