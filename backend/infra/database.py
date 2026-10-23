"""Database connection and REQ-001 tables. MySQL is the deployed source of truth."""
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (JSON, Column, DateTime, ForeignKey, Integer, LargeBinary,
                        MetaData, String, Table, UniqueConstraint, create_engine)
from sqlalchemy.engine import Engine, URL

metadata = MetaData()
strategies = Table(
    'strategies', metadata,
    Column('id', String(36), primary_key=True),
    Column('name', String(255), nullable=False),
    Column('canonical_name', String(255), nullable=False, unique=True),
    Column('created_at', DateTime(timezone=True), nullable=False),
)
versions = Table(
    'versions', metadata,
    Column('id', String(36), primary_key=True),
    Column('strategy_id', String(36), ForeignKey('strategies.id', ondelete='RESTRICT'), nullable=False),
    Column('number', Integer, nullable=False),
    Column('file_name', String(255), nullable=False),
    Column('uploaded_at', DateTime(timezone=True), nullable=False),
    Column('sha256', String(64), nullable=False),
    Column('manifest', JSON, nullable=False),
    Column('status', String(64), nullable=False),
    Column('zip_bytes', LargeBinary(length=50_000_000), nullable=False),
    UniqueConstraint('strategy_id', 'number'), UniqueConstraint('strategy_id', 'sha256'),
)

def now():
    # MySQL DATETIME does not retain an offset; every stored timestamp is UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def database_url():
    explicit = os.environ.get('LIGHTNING_DATABASE_URL')
    if explicit:
        return explicit
    password_file = os.environ.get('LIGHTNING_DB_PASSWORD_FILE')
    if not password_file:
        raise RuntimeError('缺少数据库密码文件 LIGHTNING_DB_PASSWORD_FILE')
    password = Path(password_file).read_text().rstrip('\r\n')
    if not password:
        raise RuntimeError('数据库密码不能为空')
    return URL.create(
        'mysql+pymysql',
        username=os.environ.get('LIGHTNING_DB_USER', 'lightning_app'),
        password=password,
        host=os.environ.get('LIGHTNING_DB_HOST', 'db'),
        port=int(os.environ.get('LIGHTNING_DB_PORT', '3306')),
        database=os.environ.get('LIGHTNING_DB_NAME', 'lightning'),
        query={'charset': 'utf8mb4'},
    )


def make_engine(url=None) -> Engine:
    return create_engine(url or database_url(), pool_pre_ping=True)


def ensure_schema(engine: Engine):
    """First-install bootstrap only. Existing schemas must be upgraded separately."""
    metadata.create_all(engine)
