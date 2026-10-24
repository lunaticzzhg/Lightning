"""Strict UTF-8 CSV interpretation, market-clock normalization, and validation."""
import csv
import io
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

class InvalidFile(ValueError):
    pass

EXCHANGES = {'SH': 'CN', 'SZ': 'CN', 'BJ': 'CN', 'NYSE': 'US', 'NASDAQ': 'US', 'AMEX': 'US'}
CLOCKS = {'CN': ('Asia/Shanghai', time(9, 30), time(11, 30), time(13), time(15)),
          'US': ('America/New_York', time(9, 30), time(16))}
FIELDS = ('open', 'high', 'low', 'close', 'volume')

def infer_exchange(symbol):
    if re.fullmatch(r'6[0-9]{5}', symbol): return 'SH'
    if re.fullmatch(r'[03][0-9]{5}', symbol): return 'SZ'
    if re.fullmatch(r'[48][0-9]{5}', symbol): return 'BJ'
    return None

def infer_market(symbol):
    if re.fullmatch(r'[0-9]{6}', symbol): return 'CN'
    if re.fullmatch(r'[A-Z.]{1,8}', symbol): return 'US'
    return None

def parse(raw: bytes):
    try:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
        headers = set(reader.fieldnames or ())
        period = 'minute' if 'timestamp' in headers else 'day' if 'date' in headers else None
        needed = {'symbol', *FIELDS, 'timestamp' if period == 'minute' else 'date'}
        if period is None or not needed <= headers:
            raise InvalidFile(f'缺少必需列：{", ".join(sorted(needed - headers))}')
        records = list(reader)
    except UnicodeDecodeError as exc:
        raise InvalidFile('文件必须是 UTF-8 CSV') from exc
    if not records:
        raise InvalidFile('CSV 没有行情记录')
    if len(records) > 200_000:
        raise InvalidFile('文件超过当前单次导入保护上限 200000 行；请拆分文件')
    markets, symbols, needs_exchange = set(), set(), False
    for line, row in enumerate(records, 2):
        exchange = (row.get('exchange') or '').strip().upper()
        symbol = (row.get('symbol') or '').strip().upper()
        if not symbol:
            raise InvalidFile(f'第 {line} 行 symbol：股票代码不能为空')
        if exchange and exchange not in EXCHANGES:
            raise InvalidFile(f'第 {line} 行 exchange：交易所无效')
        inferred_market = infer_market(symbol)
        if exchange and inferred_market and EXCHANGES[exchange] != inferred_market:
            raise InvalidFile(f'第 {line} 行 exchange：与股票代码可确定的市场不符')
        if exchange and infer_exchange(symbol) and exchange != infer_exchange(symbol):
            raise InvalidFile(f'第 {line} 行 exchange：与股票代码可确定的交易所不符')
        resolved = exchange or infer_exchange(symbol)
        market = EXCHANGES[resolved] if resolved else inferred_market
        if not market:
            raise InvalidFile(f'第 {line} 行 symbol：无法判断市场，请使用可识别代码并填写 exchange')
        markets.add(market)
        needs_exchange |= resolved is None
        symbols.add(f'{resolved or "?"}:{symbol}')
        try:
            if period == 'day':
                date.fromisoformat((row.get('date') or '').strip())
            else:
                dt = datetime.fromisoformat((row.get('timestamp') or '').strip())
                if dt.tzinfo is None or dt.utcoffset() is None:
                    raise ValueError('缺少时区')
        except ValueError as exc:
            raise InvalidFile(f'第 {line} 行时间：需要有效的 ISO 日期或带时区时间') from exc
        for field in FIELDS:
            try:
                value = Decimal((row.get(field) or '').strip())
                if not value.is_finite(): raise InvalidOperation
            except InvalidOperation as exc:
                raise InvalidFile(f'第 {line} 行 {field}：需要有限数字') from exc
    if len(markets) != 1:
        raise InvalidFile('文件混合 A 股和美股，请按市场拆分')
    return {'period': period, 'market': next(iter(markets)), 'symbols': sorted(symbols), 'count': len(records),
            'needs_exchange': needs_exchange,
            'first': min((r.get('timestamp') or r.get('date')) for r in records),
            'last': max((r.get('timestamp') or r.get('date')) for r in records)}, records

def normalize(records, period, market, unit, minute_position=None, exchange_override=None):
    if unit not in ('shares', 'lots100') or (market == 'US' and unit == 'lots100'):
        raise InvalidFile('请选择适用的成交量单位；美股仅支持股')
    if period == 'minute' and minute_position not in ('start', 'end'):
        raise InvalidFile('请选择分钟时间表示开始还是结束')
    if exchange_override and EXCHANGES.get(exchange_override) != market:
        raise InvalidFile('所选交易所与文件市场不符')
    factor = Decimal(1 if unit == 'shares' else 100)
    zone_name, *sessions = CLOCKS[market]
    zone = ZoneInfo(zone_name)
    found = {}
    for line, row in enumerate(records, 2):
        symbol = row['symbol'].strip().upper()
        explicit = (row.get('exchange') or '').strip().upper()
        inferred = infer_exchange(symbol)
        exchange = explicit or inferred or exchange_override
        if not exchange:
            raise InvalidFile(f'第 {line} 行 exchange：请选择交易所')
        if EXCHANGES.get(exchange) != market:
            raise InvalidFile(f'第 {line} 行 exchange：市场与目标不符')
        if infer_market(symbol) and infer_market(symbol) != market:
            raise InvalidFile(f'第 {line} 行 exchange：与股票代码可确定的市场不符')
        if inferred and exchange != inferred:
            raise InvalidFile(f'第 {line} 行 exchange：与股票代码可确定的交易所不符')
        try:
            if period == 'day':
                day = date.fromisoformat(row['date'].strip())
                local = datetime.combine(day, time(0), zone)
                key_time = day.isoformat()
            else:
                incoming = datetime.fromisoformat(row['timestamp'].strip())
                if incoming.tzinfo is None or incoming.utcoffset() is None:
                    raise ValueError('missing offset')
                if incoming.second or incoming.microsecond:
                    raise ValueError('not minute aligned')
                local = incoming.astimezone(zone)
                if minute_position == 'end': local -= timedelta(minutes=1)
                if local.weekday() >= 5 or not _in_session(local.time(), sessions):
                    raise ValueError('out of regular session')
                key_time = local.astimezone(timezone.utc).isoformat()
            if local.weekday() >= 5:
                raise ValueError('weekend')
        except ValueError as exc:
            raise InvalidFile(f'第 {line} 行时间：不在有效常规交易时段或时间格式无效') from exc
        values = {field: Decimal(row[field].strip()) for field in FIELDS}
        values['volume'] *= factor
        if any(values[f] <= 0 for f in ('open', 'high', 'low', 'close')) or values['volume'] < 0:
            raise InvalidFile(f'第 {line} 行价格/成交量：价格须大于零，成交量不能为负')
        if values['high'] < max(values[f] for f in ('open','close','low')) or values['low'] > min(values[f] for f in ('open','close','high')):
            raise InvalidFile(f'第 {line} 行价格：最高价或最低价与开收盘价不符')
        key = f'{exchange}:{symbol}|{key_time}'
        normalized = {'exchange': exchange, 'symbol': symbol, 'time': key_time,
                      'market_time': local.isoformat(), **{f: str(values[f]) for f in FIELDS}}
        if key in found and any(Decimal(found[key][f]) != values[f] for f in FIELDS):
            raise InvalidFile(f'第 {line} 行时间：文件内同一股票同一时点数值冲突')
        found[key] = normalized
    return found

def _in_session(value, sessions):
    return any(start <= value < end for start, end in zip(sessions[::2], sessions[1::2]))
