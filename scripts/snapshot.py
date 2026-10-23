"""Fingerprint all REQ-001 records, references, and original ZIP bytes."""
import hashlib
import json
from datetime import datetime

from sqlalchemy import create_engine, text

from backend.infra.database import database_url

TABLES = ('strategies', 'versions')
BUSINESS_COLUMNS = {
    'strategies': 'id, name, canonical_name, created_at',
    'versions': 'id, strategy_id, number, file_name, uploaded_at, sha256, manifest, status, zip_bytes',
}


def snapshot():
    engine = create_engine(database_url())
    try:
        with engine.connect() as db:
            result = {}
            for table in TABLES:
                rows = db.execute(text(f'SELECT {BUSINESS_COLUMNS[table]} FROM {table} ORDER BY id')).mappings()
                encoded = []
                for row in rows:
                    values = dict(row)
                    if table == 'versions':
                        blob = values.pop('zip_bytes')
                        checksum = hashlib.sha256(blob).hexdigest()
                        if checksum != values['sha256']:
                            raise RuntimeError(f'原始包校验不一致: {values["id"]}')
                        values['zip_sha256'] = checksum
                    for key, value in values.items():
                        if isinstance(value, datetime):
                            values[key] = value.isoformat()
                    encoded.append(values)
                result[table] = encoded
            for table, parent, key in (
                ('versions', 'strategies', 'strategy_id'),
            ):
                parent_ids = {row['id'] for row in result[parent]}
                if any(row[key] not in parent_ids for row in result[table]):
                    raise RuntimeError(f'孤立的 {table} 记录')
            payload = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            return {'counts': {table: len(result[table]) for table in TABLES},
                    'sha256': hashlib.sha256(payload.encode()).hexdigest()}
    finally:
        engine.dispose()


if __name__ == '__main__':
    print(json.dumps(snapshot(), ensure_ascii=False, sort_keys=True))
