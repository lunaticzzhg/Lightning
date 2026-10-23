"""REQ-001 strategy identity and immutable versions."""
from uuid import uuid4
from datetime import timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.infra.database import now, strategies, versions
from backend.features.strategies.package import PackageError, validate_package


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def uid():
    return str(uuid4())


def utc_iso(value):
    # MySQL DATETIME drops tzinfo; stored values are defined to be UTC.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def row(connection, statement):
    item = connection.execute(statement).first()
    if item is None:
        raise NotFound()
    return dict(item._mapping)


def strategy_summary(connection, strategy):
    count = connection.scalar(select(func.count()).select_from(versions).where(versions.c.strategy_id == strategy['id']))
    latest = connection.scalar(select(func.max(versions.c.number)).where(versions.c.strategy_id == strategy['id']))
    return {'id': strategy['id'], 'name': strategy['name'], 'version_count': count, 'latest_version': latest}


def version_public(version):
    return {k: (utc_iso(v) if k == 'uploaded_at' else v) for k, v in version.items() if k != 'zip_bytes'}


def list_strategies(engine):
    with engine.connect() as connection:
        return [strategy_summary(connection, dict(r._mapping)) for r in connection.execute(select(strategies).order_by(strategies.c.created_at.desc()))]


def get_strategy(engine, strategy_id):
    with engine.connect() as connection:
        strategy = row(connection, select(strategies).where(strategies.c.id == strategy_id))
        items = [version_public(dict(r._mapping)) for r in connection.execute(select(versions).where(versions.c.strategy_id == strategy_id).order_by(versions.c.number.desc()))]
        return {'strategy': strategy_summary(connection, strategy), 'versions': items}


def upload(engine, file_name, data, strategy_id=None):
    manifest, checksum = validate_package(data)
    name = manifest['name'].strip()
    canonical = name.casefold()
    if len(name) > 255 or len(canonical) > 255 or not file_name or len(file_name) > 255 or any(ord(char) < 32 for char in file_name):
        raise PackageError('名称或文件名过长')
    try:
        with engine.begin() as connection:
            if strategy_id is None:
                existing = connection.execute(select(strategies.c.id).where(strategies.c.canonical_name == canonical)).first()
                if existing:
                    same = connection.execute(select(versions.c.id).where(versions.c.strategy_id == existing.id, versions.c.sha256 == checksum)).first()
                    if same:
                        raise Conflict(f'相同策略包已有版本：{same.id}')
                    raise Conflict('策略名称已存在，请在已有策略下上传新版本')
                strategy_id = uid()
                connection.execute(strategies.insert().values(id=strategy_id, name=name, canonical_name=canonical, created_at=now()))
                number = 1
            else:
                strategy = row(connection, select(strategies).where(strategies.c.id == strategy_id).with_for_update())
                if canonical != strategy['canonical_name']:
                    raise PackageError('策略包名称与所选策略不一致')
                existing = connection.execute(select(versions.c.id).where(versions.c.strategy_id == strategy_id, versions.c.sha256 == checksum)).first()
                if existing:
                    raise Conflict(f'相同策略包已有版本：{existing.id}')
                number = (connection.scalar(select(func.max(versions.c.number)).where(versions.c.strategy_id == strategy_id)) or 0) + 1
            version = {'id': uid(), 'strategy_id': strategy_id, 'number': number,
                       'file_name': file_name, 'uploaded_at': now(), 'sha256': checksum,
                       'manifest': manifest, 'status': '已导入，未运行验证', 'zip_bytes': data}
            connection.execute(versions.insert().values(**version))
            return version_public(version)
    except IntegrityError as exc:
        raise Conflict('策略名称、版本号或策略包与已有记录冲突') from exc


def get_version(engine, version_id):
    with engine.connect() as connection:
        version = row(connection, select(versions).where(versions.c.id == version_id))
        strategy = row(connection, select(strategies).where(strategies.c.id == version['strategy_id']))
        return {'version': version_public(version), 'strategy': strategy_summary(connection, strategy)}


def download(engine, version_id):
    with engine.connect() as connection:
        version = row(connection, select(versions.c.file_name, versions.c.zip_bytes).where(versions.c.id == version_id))
        return version['file_name'], version['zip_bytes']
