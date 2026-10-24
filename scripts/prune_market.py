"""Remove expired unpublished drafts and originals while the app is stopped."""
import json
import os
from datetime import timedelta
from pathlib import Path
from sqlalchemy import select, delete
from backend.infra.database import make_engine, now, market_drafts, market_imports
from backend.features.market_data.storage import Store


def prune(engine, store, cutoff=None):
    cutoff = cutoff or now() - timedelta(days=2)
    with engine.begin() as db:
        expired = db.execute(select(market_drafts.c.raw_path).where(
            market_drafts.c.result.is_(None), market_drafts.c.created_at < cutoff)).scalars().all()
        for relative in expired:
            if not relative.startswith('originals/') or Path(relative).is_absolute() or '..' in Path(relative).parts:
                raise RuntimeError(f'草稿原件路径无效：{relative}')
        db.execute(delete(market_drafts).where(
            market_drafts.c.result.is_(None), market_drafts.c.created_at < cutoff))
    with engine.connect() as db:
        referenced = set(db.execute(select(market_drafts.c.raw_path)).scalars())
        referenced.update(db.execute(select(market_imports.c.raw_path)).scalars())
    removed_files = 0
    # Also remove originals left without a draft after a failed upload or interrupted cleanup.
    for path in (store.root / 'originals').rglob('*.csv'):
        relative = path.relative_to(store.root).as_posix()
        if relative in referenced: continue
        if not path.resolve().is_relative_to(store.root.resolve()):
            raise RuntimeError('草稿原件路径越界')
        path.unlink()
        removed_files += 1
    return {'expired_drafts': len(expired), 'removed_originals': removed_files}

if __name__ == '__main__':
    if os.environ.get('LIGHTNING_MARKET_APP_STOPPED') != '1':
        raise SystemExit('请先停止 app，并设置 LIGHTNING_MARKET_APP_STOPPED=1')
    db_engine = make_engine()
    try:
        print(json.dumps(prune(db_engine, Store(os.environ.get('LIGHTNING_MARKET_DIR', '/srv/market'))), ensure_ascii=False))
    finally:
        db_engine.dispose()
