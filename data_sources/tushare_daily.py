"""Fetch one A-share's unadjusted daily bars for Lightning's CSV importer."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from getpass import getpass
import os
from pathlib import Path
import re
import sys
import tempfile


COLUMNS = ("symbol", "exchange", "date", "open", "high", "low", "close", "volume")
EXPORT_DIR = Path(__file__).resolve().parent / "exports"


def parse_date(value: str) -> str:
    try:
        if not re.fullmatch(r"[0-9]{8}", value):
            raise ValueError(value)
        datetime.strptime(value, "%Y%m%d")
    except ValueError as error:
        raise argparse.ArgumentTypeError("日期须为 YYYYMMDD，例如 20260101") from error
    return value


def convert(records: list[dict], ts_code: str, start: str, end: str) -> list[dict]:
    symbol, exchange = ts_code.split(".")
    result = []
    seen_dates = set()
    for record in records:
        if record["ts_code"] != ts_code:
            raise ValueError("返回的股票代码与请求不符")
        raw_date = str(record["trade_date"])
        day = datetime.strptime(raw_date, "%Y%m%d").date()
        if not start <= raw_date <= end or raw_date in seen_dates:
            raise ValueError("返回的日期超出范围或重复")
        seen_dates.add(raw_date)
        result.append({
            "symbol": symbol,
            "exchange": exchange,
            "date": day.isoformat(),
            "open": record["open"],
            "high": record["high"],
            "low": record["low"],
            "close": record["close"],
            "volume": record["vol"],  # Tushare 的单位是“手”；导入页面也选择“手”。
        })
    return sorted(result, key=lambda item: item["date"])


def save_csv(rows: list[dict], output: Path) -> None:
    if output.exists():
        raise ValueError(f"输出文件已存在：{output}。请换路径或先移走旧文件")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=output.parent,
            prefix=f".{output.name}.", suffix=".tmp", delete=False,
        ) as file:
            temporary = Path(file.name)
            writer = csv.DictWriter(file, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="拉取 Tushare A 股未复权日线，导出 Lightning 可导入的 CSV")
    parser.add_argument("--symbol", required=True, help="Tushare 股票代码，如 600519.SH")
    parser.add_argument("--start", required=True, type=parse_date, help="开始日期 YYYYMMDD")
    parser.add_argument("--end", required=True, type=parse_date, help="结束日期 YYYYMMDD")
    parser.add_argument("--output", type=Path, help="CSV 输出路径；默认放在 data_sources/exports/")
    args = parser.parse_args()
    ts_code = args.symbol.upper()
    if not re.fullmatch(r"[0-9]{6}\.(SH|SZ|BJ)", ts_code):
        parser.error("股票代码须类似 600519.SH、000001.SZ 或 830799.BJ")
    if args.start > args.end:
        parser.error("开始日期不能晚于结束日期")
    output = (args.output or EXPORT_DIR / f"tushare-{ts_code}-{args.start}-{args.end}.csv").expanduser().resolve()
    if output.exists():
        parser.error(f"输出文件已存在：{output}。请换路径或先移走旧文件")

    try:
        import tushare as ts
    except ImportError as error:
        raise SystemExit("请先安装依赖：python3 -m pip install tushare") from error

    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        if not sys.stdin.isatty():
            parser.error("请在终端输入 Token，或设置 TUSHARE_TOKEN 环境变量")
        token = getpass("Tushare Token: ").strip()
    if not token:
        parser.error("Token 不能为空")

    try:
        frame = ts.pro_api(token).daily(
            ts_code=ts_code, start_date=args.start, end_date=args.end,
            fields="ts_code,trade_date,open,high,low,close,vol",
        )
        records = frame.to_dict("records")
        if not records:
            raise ValueError("没有取到行情；请检查股票、日期和账号权限")
        if len(records) >= 6000:
            raise ValueError("一次返回已达 6000 条；请缩短日期范围，避免数据被截断")
        rows = convert(records, ts_code, args.start, args.end)
        save_csv(rows, output)
    except Exception as error:
        raise SystemExit(f"拉取失败：{str(error).replace(token, '***')}") from error

    print(f"已保存 {len(rows)} 条日线：{output}")
    print("导入时选择未复权，成交量单位选择“手”。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
