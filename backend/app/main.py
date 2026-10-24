"""Container entry point. Deployment owns migration and shutdown."""
import os
from pathlib import Path

import uvicorn

from backend.app.api import create_app
from backend.infra.database import make_engine


def run():
    static = Path(__file__).resolve().parents[2] / 'web/dist'
    if not (static / 'index.html').is_file():
        raise RuntimeError('缺少已构建的管理页面')
    uvicorn.run(
        create_app(make_engine(), static_dir=static, market_dir=Path(os.environ.get('LIGHTNING_MARKET_DIR', '/srv/market'))),
        host='0.0.0.0',
        port=int(os.environ.get('LIGHTNING_PORT', '8000')),
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get('LIGHTNING_TRUSTED_PROXIES', '127.0.0.1'),
    )


if __name__ == '__main__':
    run()
