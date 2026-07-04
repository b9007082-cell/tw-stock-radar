from __future__ import annotations

import gzip
import hashlib
import json
import time
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx

from app.services.market_data import MarketRow, _decimal, _integer, is_common_stock

SCHEMA_VERSION = 1
TWSE_HISTORY_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TPEX_HISTORY_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes"
TPEX_REFERER = "https://www.tpex.org.tw/zh-tw/mainboard/trading/info/pricing.html"


class DataQualityError(RuntimeError):
    """Raised when official market data is incomplete or inconsistent."""


def _request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    attempts: int = 3,
    **kwargs: Any,
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(0.75 * (2**attempt))
    raise RuntimeError(f"Official data request failed: {url}") from last_error


def _table_by_field(payload: dict[str, Any], field: str) -> dict[str, Any] | None:
    for table in payload.get("tables", []):
        if field in table.get("fields", []):
            return table
    return None


def parse_twse_history(payload: dict[str, Any], requested: date) -> list[MarketRow]:
    if payload.get("stat") != "OK":
        return []
    raw_date = str(payload.get("date", ""))
    if raw_date and raw_date != requested.strftime("%Y%m%d"):
        raise DataQualityError(
            f"TWSE date mismatch: requested {requested}, received {raw_date}"
        )
    table = _table_by_field(payload, "證券代號")
    if table is None:
        return []
    fields = table["fields"]
    positions = {name: fields.index(name) for name in fields}
    required = {
        "證券代號",
        "證券名稱",
        "成交股數",
        "成交金額",
        "開盤價",
        "最高價",
        "最低價",
        "收盤價",
    }
    if not required.issubset(positions):
        raise DataQualityError("TWSE historical table is missing required fields")

    rows: list[MarketRow] = []
    for item in table.get("data", []):
        symbol = str(item[positions["證券代號"]]).strip()
        if not is_common_stock(symbol):
            continue
        try:
            rows.append(
                MarketRow(
                    symbol=symbol,
                    name=str(item[positions["證券名稱"]]).strip(),
                    market="TWSE",
                    trade_date=requested,
                    open=_decimal(item[positions["開盤價"]]),
                    high=_decimal(item[positions["最高價"]]),
                    low=_decimal(item[positions["最低價"]]),
                    close=_decimal(item[positions["收盤價"]]),
                    volume=_integer(item[positions["成交股數"]]),
                    turnover=_decimal(item[positions["成交金額"]]),
                    source="TWSE_HISTORY",
                )
            )
        except ValueError:
            continue
    return rows


def parse_tpex_history(payload: dict[str, Any], requested: date) -> list[MarketRow]:
    if str(payload.get("stat", "")).lower() != "ok":
        return []
    raw_date = str(payload.get("date", ""))
    if raw_date and raw_date != requested.strftime("%Y%m%d"):
        raise DataQualityError(
            f"TPEx date mismatch: requested {requested}, received {raw_date}"
        )
    table = _table_by_field(payload, "代號")
    if table is None:
        return []
    fields = table["fields"]
    positions = {name: fields.index(name) for name in fields}
    required = {
        "代號",
        "名稱",
        "成交股數",
        "成交金額(元)",
        "開盤",
        "最高",
        "最低",
        "收盤",
    }
    if not required.issubset(positions):
        raise DataQualityError("TPEx historical table is missing required fields")

    rows: list[MarketRow] = []
    for item in table.get("data", []):
        symbol = str(item[positions["代號"]]).strip()
        if not is_common_stock(symbol):
            continue
        try:
            rows.append(
                MarketRow(
                    symbol=symbol,
                    name=str(item[positions["名稱"]]).strip(),
                    market="TPEX",
                    trade_date=requested,
                    open=_decimal(item[positions["開盤"]]),
                    high=_decimal(item[positions["最高"]]),
                    low=_decimal(item[positions["最低"]]),
                    close=_decimal(item[positions["收盤"]]),
                    volume=_integer(item[positions["成交股數"]]),
                    turnover=_decimal(item[positions["成交金額(元)"]]),
                    source="TPEX_HISTORY",
                )
            )
        except ValueError:
            continue
    return rows


class OfficialHistoryClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(
            timeout=45,
            follow_redirects=True,
            headers={"User-Agent": "tw-stock-radar/0.2 (+GitHub Pages pipeline)"},
        )

    def fetch_day(self, trade_date: date) -> list[MarketRow]:
        if trade_date.weekday() >= 5:
            return []
        twse_response = _request_with_retry(
            self.client,
            "GET",
            TWSE_HISTORY_URL,
            params={
                "date": trade_date.strftime("%Y%m%d"),
                "type": "ALLBUT0999",
                "response": "json",
            },
        )
        twse_payload = twse_response.json()
        twse = parse_twse_history(twse_payload, trade_date)
        if not twse and twse_payload.get("stat") != "OK":
            twse_fallback = _request_with_retry(
                self.client,
                "GET",
                TWSE_HISTORY_URL,
                params={
                    "date": trade_date.strftime("%Y%m%d"),
                    "type": "ALL",
                    "response": "json",
                },
            )
            twse = parse_twse_history(twse_fallback.json(), trade_date)
        tpex_response = _request_with_retry(
            self.client,
            "POST",
            TPEX_HISTORY_URL,
            data={
                "date": trade_date.strftime("%Y/%m/%d"),
                "response": "json",
            },
            headers={"Referer": TPEX_REFERER},
        )
        tpex = parse_tpex_history(tpex_response.json(), trade_date)
        if not twse and not tpex:
            return []
        if not twse or not tpex:
            raise DataQualityError(
                f"Only one market returned data for {trade_date}: "
                f"TWSE={len(twse)}, TPEX={len(tpex)}"
            )
        if len(twse) < 500 or len(tpex) < 400 or len(twse) + len(tpex) < 1_200:
            raise DataQualityError(
                f"Abnormal row count for {trade_date}: "
                f"TWSE={len(twse)}, TPEX={len(tpex)}"
            )
        symbols = [row.symbol for row in [*twse, *tpex]]
        if len(symbols) != len(set(symbols)):
            raise DataQualityError(f"Duplicate symbols across markets on {trade_date}")
        return [*twse, *tpex]


def _row_to_json(row: MarketRow) -> dict[str, str | int]:
    return {
        "symbol": row.symbol,
        "name": row.name,
        "market": row.market,
        "trade_date": row.trade_date.isoformat(),
        "open": str(row.open),
        "high": str(row.high),
        "low": str(row.low),
        "close": str(row.close),
        "volume": row.volume,
        "turnover": str(row.turnover),
        "source": row.source,
    }


def _row_from_json(item: dict[str, Any]) -> MarketRow:
    return MarketRow(
        symbol=str(item["symbol"]),
        name=str(item["name"]),
        market=str(item["market"]),
        trade_date=date.fromisoformat(str(item["trade_date"])),
        open=Decimal(str(item["open"])),
        high=Decimal(str(item["high"])),
        low=Decimal(str(item["low"])),
        close=Decimal(str(item["close"])),
        volume=int(item["volume"]),
        turnover=Decimal(str(item["turnover"])),
        source=str(item["source"]),
    )


def snapshot_path(raw_dir: Path, trade_date: date) -> Path:
    return raw_dir / f"{trade_date.isoformat()}.json.gz"


def write_snapshot(
    raw_dir: Path,
    trade_date: date,
    rows: list[MarketRow],
    *,
    ingested_at: str | None = None,
) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    counts = {
        "TWSE": sum(row.market == "TWSE" for row in rows),
        "TPEX": sum(row.market == "TPEX" for row in rows),
        "total": len(rows),
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "trade_date": trade_date.isoformat(),
        "ingested_at": ingested_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "sources": [TWSE_HISTORY_URL, TPEX_HISTORY_URL],
        "counts": counts,
        "rows": [_row_to_json(row) for row in sorted(rows, key=lambda row: row.symbol)],
    }
    raw = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    output = snapshot_path(raw_dir, trade_date)
    temporary = output.with_suffix(".tmp")
    buffer = BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as archive:
        archive.write(raw)
    temporary.write_bytes(buffer.getvalue())
    temporary.replace(output)
    return output


def read_snapshot(path: Path) -> tuple[dict[str, Any], list[MarketRow]]:
    with gzip.open(path, "rt", encoding="utf-8") as archive:
        payload = json.load(archive)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise DataQualityError(f"Unsupported snapshot schema: {path}")
    rows = [_row_from_json(item) for item in payload.get("rows", [])]
    expected = int(payload.get("counts", {}).get("total", -1))
    if expected != len(rows):
        raise DataQualityError(f"Snapshot row count mismatch: {path}")
    trade_date = date.fromisoformat(str(payload["trade_date"]))
    if any(row.trade_date != trade_date for row in rows):
        raise DataQualityError(f"Snapshot contains mixed trade dates: {path}")
    for market in ("TWSE", "TPEX"):
        expected_market = int(payload.get("counts", {}).get(market, -1))
        actual_market = sum(row.market == market for row in rows)
        if expected_market != actual_market:
            raise DataQualityError(
                f"Snapshot {market} count mismatch: {path}"
            )
    return payload, rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_weekdays(start: date, end: date):
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            yield cursor
        cursor += timedelta(days=1)


def backfill_history(
    raw_dir: Path,
    start: date,
    end: date,
    *,
    delay_seconds: float = 0.15,
    client: OfficialHistoryClient | None = None,
) -> dict[str, int]:
    source = client or OfficialHistoryClient()
    result = {"fetched": 0, "existing": 0, "holidays": 0}
    for trade_date in iter_weekdays(start, end):
        output = snapshot_path(raw_dir, trade_date)
        if output.exists():
            result["existing"] += 1
            continue
        rows = source.fetch_day(trade_date)
        if not rows:
            result["holidays"] += 1
        else:
            write_snapshot(raw_dir, trade_date, rows)
            result["fetched"] += 1
        if delay_seconds:
            time.sleep(delay_seconds)
    return result


def prune_history(raw_dir: Path, cutoff: date) -> int:
    removed = 0
    for path in raw_dir.glob("*.json.gz"):
        try:
            trade_date = date.fromisoformat(path.name.removesuffix(".json.gz"))
        except ValueError:
            continue
        if trade_date < cutoff:
            path.unlink()
            removed += 1
    return removed


def write_state_manifest(raw_dir: Path, state_path: Path) -> dict[str, Any]:
    snapshots = sorted(raw_dir.glob("*.json.gz"))
    dates = [path.name.removesuffix(".json.gz") for path in snapshots]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "first_trade_date": dates[0] if dates else None,
        "latest_trade_date": dates[-1] if dates else None,
        "trading_days": len(dates),
        "snapshots": {
            path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in snapshots
        },
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(state_path)
    return manifest
