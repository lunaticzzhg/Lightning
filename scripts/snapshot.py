"""Fingerprint SQL records and every referenced immutable market file."""
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from backend.infra.database import database_url
from backend.features.market_data.storage import Store

BASE = {
    'strategies': 'id, name, canonical_name, created_at',
    'versions': 'id, strategy_id, number, file_name, uploaded_at, sha256, manifest, status, zip_bytes',
}
MARKET = {
    'market_sources': 'id, provider, product',
    'market_datasets': 'id, source_id, market, period, price_mode, adjustment, reference_date, session',
    'market_drafts': 'id, file_name, raw_path, sha256, period, market, summary, created_at, result',
    'market_imports': 'id, dataset_id, draft_id, file_name, raw_path, sha256, created_at, summary',
    'market_versions': 'id, dataset_id, import_id, number, previous_id, parquet_path, parquet_sha256, files, coverage, row_count, created_at, warning_rules, warnings',
}

def snapshot():
    engine = create_engine(database_url())
    try:
        names = set(inspect(engine).get_table_names())
        columns = {**BASE, **(MARKET if set(MARKET) <= names else {})}
        result = {}
        with engine.connect() as db:
            for table, selected in columns.items():
                encoded = []
                for row in db.execute(text(f'SELECT {selected} FROM {table} ORDER BY id')).mappings():
                    values = dict(row)
                    if table == 'versions':
                        blob = values.pop('zip_bytes')
                        digest = hashlib.sha256(blob).hexdigest()
                        if digest != values['sha256']: raise RuntimeError(f'策略包校验失败：{values["id"]}')
                        values['zip_sha256'] = digest
                    for key, value in values.items():
                        if isinstance(value, datetime): values[key] = value.isoformat()
                    encoded.append(values)
                result[table] = encoded
        for child, parent, key in [('versions','strategies','strategy_id'),
                                   *([('market_datasets','market_sources','source_id'),('market_imports','market_datasets','dataset_id'),
                                      ('market_versions','market_datasets','dataset_id'),('market_versions','market_imports','import_id')]
                                     if 'market_sources' in result else [])]:
            ids = {r['id'] for r in result[parent]}
            if any(r[key] not in ids for r in result[child]): raise RuntimeError(f'孤立的 {child} 记录')
        if result.get('market_versions') or result.get('market_imports'):
            store = Store(Path(os.environ.get('LIGHTNING_MARKET_DIR', '/srv/market')))
            for row in result['market_imports']:
                store.read(row['raw_path'], row['sha256'])
            by_version = {r['id']:r for r in result['market_versions']}
            for row in result['market_versions']:
                previous = by_version.get(row['previous_id']) if row['previous_id'] else None
                if (row['number'] == 1 and row['previous_id']) or (row['number'] > 1 and (not previous or previous['dataset_id'] != row['dataset_id'] or previous['number'] != row['number']-1)):
                    raise RuntimeError(f'版本承接关系错误：{row["id"]}')
                files = row['files'] if isinstance(row['files'], list) else json.loads(row['files'])
                bars = store.bars(files)
                if len(bars) != row['row_count']: raise RuntimeError(f'行情条数不符：{row["id"]}')
                if not files or files[-1]['path'] != row['parquet_path'] or files[-1]['sha256'] != row['parquet_sha256']:
                    raise RuntimeError(f'版本文件目录不符：{row["id"]}')
                row['files'] = files
                coverage = row['coverage'] if isinstance(row['coverage'], dict) else json.loads(row['coverage'])
                actual_coverage = {}
                for bar in bars.values(): actual_coverage.setdefault(f"{bar['exchange']}:{bar['symbol']}", set()).add(bar['market_time'][:10])
                if {key:sorted(days) for key,days in actual_coverage.items()} != {key:value['dates'] for key,value in coverage.items()}:
                    raise RuntimeError(f'行情覆盖目录不符：{row["id"]}')
                row['coverage'] = coverage
        payload = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
        return {'counts': {table:len(rows) for table,rows in result.items()}, 'sha256':hashlib.sha256(payload.encode()).hexdigest()}
    finally:
        engine.dispose()

if __name__ == '__main__':
    print(json.dumps(snapshot(), ensure_ascii=False, sort_keys=True))
