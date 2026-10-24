"""REQ-002 draft, comparison, immutable publication and bounded reads."""
import hashlib
import os
import uuid
import re
from decimal import Decimal
from datetime import timedelta, date
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from backend.infra.database import (now, market_sources as sources, market_datasets as datasets,
    market_drafts as drafts, market_imports as imports, market_versions as versions)
from .importer import InvalidFile, parse, normalize, EXCHANGES, infer_exchange, infer_market
from .storage import Store, CorruptVersion

class NotFound(Exception): pass
class Conflict(Exception): pass

DIFF_PAGE = 50


def _warning_rules():
    rules = {}
    for kind, env in [('price_ratio','LIGHTNING_MARKET_PRICE_ALERT_RATIO'),
                      ('volume_ratio','LIGHTNING_MARKET_VOLUME_ALERT_RATIO')]:
        raw = os.environ.get(env)
        if raw:
            try:
                ratio = Decimal(raw)
                if not ratio.is_finite() or ratio <= 1: raise ValueError
            except (ValueError, ArithmeticError) as exc:
                raise RuntimeError(f'{env} 必须是大于 1 的数字') from exc
            rules[kind] = str(ratio)
    return rules

def _observations(rows, rules):
    if not rules: return []
    grouped = {}
    for key, bar in rows.items(): grouped.setdefault((bar['exchange'],bar['symbol']), []).append((key,bar))
    found = []
    for series in grouped.values():
        series.sort(key=lambda pair: pair[1]['time'])
        for (key, current), (_, previous) in zip(series[1:], series[:-1]):
            close, before = Decimal(current['close']), Decimal(previous['close'])
            volume, old_volume = Decimal(current['volume']), Decimal(previous['volume'])
            if rules.get('price_ratio') and (close/before >= Decimal(rules['price_ratio']) or before/close >= Decimal(rules['price_ratio'])):
                found.append({'key':key,'kind':'price_change','message':f'收盘价由 {before} 变为 {close}'})
            if rules.get('volume_ratio') and old_volume > 0 and volume > 0 and (volume/old_volume >= Decimal(rules['volume_ratio']) or old_volume/volume >= Decimal(rules['volume_ratio'])):
                found.append({'key':key,'kind':'volume_change','message':f'成交量由 {old_volume} 变为 {volume}'})
    return found

def _id(): return str(uuid.uuid4())
def _row(db, table, key):
    result = db.execute(select(table).where(table.c.id == key)).mappings().first()
    if result is None: raise NotFound
    return dict(result)
def _latest(db, dataset_id, lock=False):
    query = select(versions).where(versions.c.dataset_id == dataset_id).order_by(versions.c.number.desc()).limit(1)
    if lock: query = query.with_for_update()
    row = db.execute(query).mappings().first()
    return dict(row) if row else None

def stage(engine, store: Store, name, raw, target_dataset_id=None):
    if not name.lower().endswith('.csv'): raise InvalidFile('请选择 CSV 文件')
    if len(raw) > 30_000_000: raise InvalidFile('文件超过当前单次上传保护上限 30 MB；请拆分文件')
    summary, _ = parse(raw)
    path, digest = store.original(raw)
    draft_id = _id()
    with engine.begin() as db:
        target = _row(db, datasets, target_dataset_id) if target_dataset_id else None
        mismatch = bool(target and (target['market'] != summary['market'] or target['period'] != summary['period']))
        db.execute(drafts.insert().values(id=draft_id, file_name=name[:255], raw_path=path, sha256=digest,
            period=summary['period'], market=summary['market'], summary=summary, created_at=now(), result=None))
    return {'draft_id': draft_id, **summary, 'target_mismatch': mismatch,
            'needs': ['source', 'price_mode', 'volume_unit'] + (['exchange'] if summary['needs_exchange'] else [])
                     + (['minute_position'] if summary['period']=='minute' else [])}

def _draft(db, draft_id, lock=False):
    if lock:
        row = db.execute(select(drafts).where(drafts.c.id == draft_id).with_for_update()).mappings().first()
        if row is None: raise NotFound
        draft = dict(row)
    else:
        draft = _row(db, drafts, draft_id)
    if now() - draft['created_at'] > timedelta(days=2) and not draft['result']:
        raise Conflict('导入草稿已过期，请重新选择文件')
    return draft

def preview(engine, store, draft_id, unit, minute_position=None, exchange=None):
    with engine.connect() as db: draft = _draft(db, draft_id)
    _, records = parse(store.read(draft['raw_path'], draft['sha256']))
    rows = normalize(records, draft['period'], draft['market'], unit, minute_position, exchange)
    return {'examples': list(rows.values())[:3], 'count': len(rows)}

def _identity(db, choice):
    source = db.execute(select(sources).where(sources.c.provider == choice['provider'], sources.c.product == choice['product'])).mappings().first()
    if not source: return None, None
    dataset = db.execute(select(datasets).where(datasets.c.source_id == source['id'], datasets.c.market == choice['market'],
        datasets.c.period == choice['period'], datasets.c.price_mode == choice['price_mode'],
        datasets.c.adjustment == choice['adjustment'], datasets.c.reference_date == choice['reference_date'],
        datasets.c.session == 'regular')).mappings().first()
    return source, dataset

def _choice(draft, payload):
    provider = payload.provider.strip(); product = payload.product.strip()
    if not provider or not product: raise InvalidFile('请填写数据提供方和数据产品')
    if payload.price_mode not in ('raw', 'adjusted'): raise InvalidFile('请选择价格处理方式')
    if payload.price_mode == 'adjusted' and (not payload.adjustment or not payload.reference_date):
        raise InvalidFile('调整后价格需要计算方法和参照日期')
    if payload.price_mode == 'adjusted':
        try: date.fromisoformat(payload.reference_date)
        except ValueError as exc: raise InvalidFile('参照日期无效') from exc
    return {'provider': provider, 'product': product, 'market': draft['market'], 'period': draft['period'],
        'price_mode': payload.price_mode, 'adjustment': payload.adjustment.strip() if payload.price_mode == 'adjusted' else '',
        'reference_date': payload.reference_date if payload.price_mode == 'adjusted' else ''}

def compare(engine, store, draft_id, payload, page=1):
    if page < 1: raise InvalidFile('页码无效')
    with engine.connect() as db:
        draft = _draft(db, draft_id)
        if draft['result']: return draft['result']
        choice = _choice(draft, payload)
        _, dataset = _identity(db, choice)
        if payload.target_dataset_id and (not dataset or dataset['id'] != payload.target_dataset_id):
            raise Conflict('文件归属与目标数据集不符；可按文件另行导入')
        latest = _latest(db, dataset['id']) if dataset else None
        existing = store.bars(latest['files']) if latest else {}
        _, records = parse(store.read(draft['raw_path'], draft['sha256']))
        incoming = normalize(records, draft['period'], draft['market'], payload.volume_unit, payload.minute_position, payload.exchange)
        additions, changes = {}, []
        for key, value in incoming.items():
            if key not in existing: additions[key] = value
            elif any(Decimal(existing[key][f]) != Decimal(value[f]) for f in ('open','high','low','close','volume')):
                changes.append({'key': key, 'old': existing[key], 'new': value})
        changes.sort(key=lambda item: item['key'])
        affected_days = [bar['market_time'][:10] for bar in additions.values()] + [item['new']['market_time'][:10] for item in changes]
        fingerprint = hashlib.sha256(repr((draft_id, latest['id'] if latest else '', sorted(incoming.items()), choice)).encode()).hexdigest()
        return {'status': 'changes' if changes else 'additions' if additions else 'unchanged',
            'dataset_id': dataset['id'] if dataset else None, 'version_id': latest['id'] if latest else None,
            'version_number': latest['number'] if latest else None, 'added': len(additions), 'changed': len(changes),
            'affected_first': min(affected_days) if affected_days else None, 'affected_last': max(affected_days) if affected_days else None,
            'page': page, 'pages': max(1, (len(changes)+DIFF_PAGE-1)//DIFF_PAGE),
            'differences': changes[(page-1)*DIFF_PAGE:page*DIFF_PAGE], 'confirmation': fingerprint}

def publish(engine, store, draft_id, payload, confirmation=None):
    try:
        return _publish_once(engine, store, draft_id, payload, confirmation)
    except IntegrityError:
        # A concurrent first import may create the same source/dataset/draft first.
        return _publish_once(engine, store, draft_id, payload, confirmation)

def _publish_once(engine, store, draft_id, payload, confirmation=None):
    comparison = compare(engine, store, draft_id, payload)
    if comparison['status'] == 'published': return comparison
    if comparison['status'] == 'unchanged': return comparison
    if comparison['status'] == 'changes' and confirmation != comparison['confirmation']:
        return comparison
    with engine.begin() as db:
        draft = _draft(db, draft_id, lock=True)
        if draft['result']: return draft['result']
        choice = _choice(draft, payload)
        source, dataset = _identity(db, choice)
        if not source:
            source_id = _id(); db.execute(sources.insert().values(id=source_id, provider=choice['provider'], product=choice['product']))
        else: source_id = source['id']
        if not dataset:
            dataset_id = _id(); db.execute(datasets.insert().values(id=dataset_id, source_id=source_id,
                market=choice['market'], period=choice['period'], price_mode=choice['price_mode'],
                adjustment=choice['adjustment'], reference_date=choice['reference_date'], session='regular'))
        else: dataset_id = dataset['id']
        # Lock parent identity even when no version exists; unique constraints are final race guard.
        db.execute(select(datasets.c.id).where(datasets.c.id == dataset_id).with_for_update()).first()
        latest = _latest(db, dataset_id, lock=True)
        if (latest['id'] if latest else None) != comparison['version_id']:
            raise Conflict('期间已有新版本，请重新比较差异')
        _, records = parse(store.read(draft['raw_path'], draft['sha256']))
        incoming = normalize(records, draft['period'], draft['market'], payload.volume_unit, payload.minute_position, payload.exchange)
        existing = store.bars(latest['files']) if latest else {}
        delta = {key: value for key, value in incoming.items() if key not in existing or
                 any(Decimal(existing[key][f]) != Decimal(value[f]) for f in ('open','high','low','close','volume'))}
        if not delta: return comparison
        path, checksum = store.delta(delta)
        files = [*latest['files'], {'path': path, 'sha256': checksum}] if latest else [{'path': path, 'sha256': checksum}]
        # Verify every referenced file before the directory becomes visible.
        merged = store.bars(files)
        raw_path, raw_digest = store.original(store.read(draft['raw_path'], draft['sha256']))
        import_id, version_id = _id(), _id()
        timestamp = now()
        db.execute(imports.insert().values(id=import_id, dataset_id=dataset_id, draft_id=draft_id,
            file_name=draft['file_name'], raw_path=raw_path, sha256=raw_digest, created_at=timestamp,
            summary={'added': comparison['added'], 'changed': comparison['changed'],
                     'affected_first':comparison['affected_first'], 'affected_last':comparison['affected_last']}))
        changed_keys = {key for key in delta if key in existing}
        warnings = [w for w in (latest['warnings'] if latest else []) if w['kind'] == 'value_changed' and w['key'] not in changed_keys]
        warnings += [{'key':key, 'kind':'value_changed', 'message':'此时点价格或成交量与前一版本不同'}
                     for key in sorted(changed_keys)]
        rules = _warning_rules()
        warnings += _observations(merged, rules)
        coverage = {}
        by_time = {}
        for key, bar in merged.items():
            identity = f"{bar['exchange']}:{bar['symbol']}"
            coverage.setdefault(identity, {'dates':set(), 'first':bar['market_time'][:10], 'last':bar['market_time'][:10], 'warning_count':{}})
            date_value = bar['market_time'][:10]
            coverage[identity]['dates'].add(date_value)
            coverage[identity]['first'] = min(coverage[identity]['first'], date_value)
            coverage[identity]['last'] = max(coverage[identity]['last'], date_value)
            by_time[key] = date_value
        for warning in warnings:
            identity = warning['key'].split('|')[0]
            date_value = by_time.get(warning['key'])
            if identity in coverage and date_value:
                counts = coverage[identity]['warning_count']
                counts[date_value] = counts.get(date_value, 0) + 1
        for info in coverage.values(): info['dates'] = sorted(info['dates'])
        db.execute(versions.insert().values(id=version_id, dataset_id=dataset_id, import_id=import_id,
            number=(latest['number']+1 if latest else 1), previous_id=latest['id'] if latest else None,
            parquet_path=path, parquet_sha256=checksum, files=files, coverage=coverage, row_count=len(merged),
            created_at=timestamp, warning_rules=rules, warnings=warnings))
        result = {'status':'published', 'dataset_id':dataset_id, 'version_id':version_id,
                  'version_number':latest['number']+1 if latest else 1, 'added':comparison['added'],
                  'changed':comparison['changed'], 'affected_first':comparison['affected_first'],
                  'affected_last':comparison['affected_last'], 'symbols':sorted({key.split('|')[0] for key in incoming})}
        db.execute(drafts.update().where(drafts.c.id == draft_id).values(result=result))
        return result

def result(engine, draft_id):
    with engine.connect() as db:
        draft = _draft(db, draft_id)
        return draft['result'] or {'status':'pending'}

def stock_candidates(engine, period, query=''):
    if period not in ('day', 'minute'): raise InvalidFile('周期无效')
    if len(query) > 32: raise InvalidFile('代码片段过长')
    needle = query.strip().upper()
    candidates = set()
    with engine.connect() as db:
        rows = db.execute(select(datasets.c.id, datasets.c.market).where(datasets.c.period == period)).mappings().all()
        for row in rows:
            latest = _latest(db, row['id'])
            if not latest: continue
            for identity in latest['coverage']:
                exchange, symbol = identity.split(':', 1)
                if needle in symbol:
                    candidates.add((row['market'], exchange, symbol))
    return [{'market': market, 'exchange': exchange, 'symbol': symbol}
            for market, exchange, symbol in sorted(candidates, key=lambda item: (item[2], item[0], item[1]))[:50]]

def search(engine, store, symbol, period, from_date, to_date, market=None, exchange=None):
    if period not in ('day','minute'): raise InvalidFile('周期无效')
    try: first_day, last_day = date.fromisoformat(from_date), date.fromisoformat(to_date)
    except ValueError as exc: raise InvalidFile('日期无效') from exc
    if first_day > last_day: raise InvalidFile('开始日期不能晚于结束日期')
    if period == 'minute' and first_day != last_day: raise InvalidFile('分钟线请只选一个日期')
    if market and market not in ('CN','US'): raise InvalidFile('市场无效')
    symbol = symbol.strip().upper()
    if exchange:
        if exchange not in EXCHANGES: raise InvalidFile('交易所无效')
        if market and EXCHANGES[exchange] != market: raise InvalidFile('市场与交易所不一致')
        if infer_market(symbol) and EXCHANGES[exchange] != infer_market(symbol): raise InvalidFile('股票代码与交易所不一致')
        if infer_exchange(symbol) and exchange != infer_exchange(symbol): raise InvalidFile('股票代码与交易所不一致')
        market = EXCHANGES[exchange]
    if not market:
        market = 'CN' if re.fullmatch(r'[0-9]{6}', symbol) else 'US' if re.fullmatch(r'[A-Za-z.]{1,8}', symbol) else None
    if market is None: return {'reason':'choose_market', 'results':[]}
    with engine.connect() as db:
        total = db.execute(select(func.count()).select_from(datasets)).scalar_one()
        rows = db.execute(select(datasets, sources.c.provider, sources.c.product).join(sources).where(
            datasets.c.period == period, *([datasets.c.market == market] if market else []))).mappings().all()
        found = []
        for row in rows:
            latest = _latest(db, row['id'])
            if not latest: continue
            for identity, info in latest['coverage'].items():
                listed_exchange, listed_symbol = identity.split(':', 1)
                if listed_symbol != symbol or (exchange and exchange != listed_exchange): continue
                found.append({'dataset_id':row['id'], 'provider':row['provider'], 'product':row['product'],
                    'market':row['market'], 'exchange':listed_exchange, 'period':period, 'price_mode':row['price_mode'],
                    'adjustment':row['adjustment'], 'reference_date':row['reference_date'],
                    'first':info['first'], 'last':info['last'], 'has_bars':any(from_date <= value <= to_date for value in info['dates']),
                    'warning_count':sum(count for key,count in info['warning_count'].items() if from_date <= key <= to_date),
                    'version_id':latest['id'], 'version_number':latest['number']})
        reason = 'never_imported' if total == 0 else 'closed_day' if not any((first_day+timedelta(days=i)).weekday() < 5 for i in range(min((last_day-first_day).days+1, 7))) else 'no_source' if not found else 'no_date' if not any(r['has_bars'] for r in found) else 'found'
        return {'reason': reason, 'results':found}

def chart(engine, store, dataset_id, version_id, symbol, from_date, to_date, exchange=None, start=None, end=None):
    try: first_day, last_day = date.fromisoformat(from_date), date.fromisoformat(to_date)
    except ValueError as exc: raise InvalidFile('日期无效') from exc
    if first_day > last_day: raise InvalidFile('开始日期不能晚于结束日期')
    with engine.connect() as db:
        version = _row(db, versions, version_id)
        if version['dataset_id'] != dataset_id: raise NotFound
        dataset = _row(db, datasets, dataset_id)
        if dataset['period'] == 'minute' and first_day != last_day:
            raise InvalidFile('分钟线请只选一个日期')
        source = _row(db, sources, dataset['source_id'])
        snapshot = store.bars(version['files'])
        matching_exchanges = {row['exchange'] for row in snapshot.values() if row['symbol'] == symbol.upper()}
        if not exchange and len(matching_exchanges) > 1:
            raise InvalidFile('该股票代码对应多个交易所，请选择交易所')
        exchange = exchange or next(iter(matching_exchanges), None)
        bars = [row for row in snapshot.values() if row['symbol'] == symbol.upper() and row['exchange'] == exchange
                and from_date <= row['market_time'][:10] <= to_date and (not start or row['market_time'][11:16] >= start)
                and (not end or row['market_time'][11:16] < end)]
        bars.sort(key=lambda row: row['time'])
        return {'version_id':version_id, 'version_number':version['number'], 'dataset_id':dataset_id,
            'period':dataset['period'], 'market':dataset['market'], 'exchange':exchange,
            'provider':source['provider'], 'product':source['product'], 'price_mode':dataset['price_mode'],
            'adjustment':dataset['adjustment'], 'reference_date':dataset['reference_date'], 'bars':bars,
            'warnings':[w for w in version['warnings'] if any(w['key'] == f"{b['exchange']}:{b['symbol']}|{b['time']}" for b in bars)]}

def import_record(engine, version_id):
    with engine.connect() as db:
        version = _row(db, versions, version_id)
        dataset = _row(db, datasets, version['dataset_id'])
        source = _row(db, sources, dataset['source_id'])
        files = []
        current = version
        while current:
            imported = _row(db, imports, current['import_id'])
            files.append({'file_name': imported['file_name'], 'created_at': imported['created_at'].isoformat()})
            current = _row(db, versions, current['previous_id']) if current['previous_id'] else None
        files.reverse()
        return {'provider':source['provider'], 'product':source['product'],
                'files':files, 'previous_version_id':version['previous_id']}


def source_list(engine):
    with engine.connect() as db:
        return [dict(row) for row in db.execute(select(sources).order_by(sources.c.provider, sources.c.product)).mappings()]

def version_list(engine, dataset_id):
    with engine.connect() as db:
        _row(db, datasets, dataset_id)
        return [{'id':r['id'], 'number':r['number'], 'created_at':r['created_at'].isoformat()}
            for r in db.execute(select(versions).where(versions.c.dataset_id == dataset_id).order_by(versions.c.number.desc())).mappings()]
