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
