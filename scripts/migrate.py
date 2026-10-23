"""Run Alembic with deployment-supplied database credentials."""
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from backend.infra.database import database_url


def main():
    url = database_url()
    engine = create_engine(url)
    try:
        for attempt in range(30):
            try:
                with engine.connect() as connection:
                    connection.exec_driver_sql('SELECT 1')
                break
            except SQLAlchemyError:
                if attempt == 29:
                    raise
                time.sleep(2)
    finally:
        engine.dispose()
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / 'backend/alembic.ini'))
    config.set_main_option('script_location', str(root / 'backend/migrations'))
    connection_url = url.render_as_string(hide_password=False) if hasattr(url, 'render_as_string') else str(url)
    config.set_main_option('sqlalchemy.url', connection_url.replace('%', '%%'))
    command.upgrade(config, 'head')


if __name__ == '__main__':
    main()
