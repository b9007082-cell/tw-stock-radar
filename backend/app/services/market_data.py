import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import DailyPrice, Instrument


@dataclass(frozen=True)
class MarketRow:
    symbol: str
    name: str
    market: str
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    turnover: Decimal
    source: str


def _roc_date(value: str) -> date:
    raw = re.sub(r"\D", "", value)
    if len(raw) != 7:
        raise ValueError(f"Invalid ROC date: {value!r}")
    year = int(raw[:3]) + 1911
    return date(year, int(raw[3:5]), int(raw[5:7]))


def _decimal(value: Any) -> Decimal:
    text = str(value).replace(",", "").replace("+", "").strip()
    if text in {"", "--", "---", "除權", "除息"}:
        raise ValueError(f"Not a numeric price: {value!r}")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Not a numeric value: {value!r}") from exc


def _integer(value: Any) -> int:
    return int(_decimal(value))


def is_common_stock(symbol: str) -> bool:
    return bool(re.fullmatch(r"[1-9]\d{3}", symbol))


class OfficialSnapshotClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.settings = get_settings()
        self.client = client or httpx.Client(
            timeout=30,
            headers={"User-Agent": "tw-stock-scanner/0.1"},
            follow_redirects=True,
        )

    def fetch_all(self) -> list[MarketRow]:
        rows: list[MarketRow] = []
        rows.extend(self._fetch_twse())
        rows.extend(self._fetch_tpex())
        return rows

    def _fetch_twse(self) -> list[MarketRow]:
        response = self.client.get(self.settings.twse_url)
        response.raise_for_status()
        parsed: list[MarketRow] = []
        for item in response.json():
            symbol = str(item.get("Code", "")).strip()
            if not is_common_stock(symbol):
                continue
            try:
                parsed.append(
                    MarketRow(
                        symbol=symbol,
                        name=str(item["Name"]).strip(),
                        market="TWSE",
                        trade_date=_roc_date(str(item["Date"])),
                        open=_decimal(item["OpeningPrice"]),
                        high=_decimal(item["HighestPrice"]),
                        low=_decimal(item["LowestPrice"]),
                        close=_decimal(item["ClosingPrice"]),
                        volume=_integer(item["TradeVolume"]),
                        turnover=_decimal(item["TradeValue"]),
                        source="TWSE_OPENAPI",
                    )
                )
            except (KeyError, ValueError):
                continue
        return parsed

    def _fetch_tpex(self) -> list[MarketRow]:
        response = self.client.get(self.settings.tpex_url)
        response.raise_for_status()
        parsed: list[MarketRow] = []
        for item in response.json():
            symbol = str(item.get("SecuritiesCompanyCode", "")).strip()
            if not is_common_stock(symbol):
                continue
            try:
                parsed.append(
                    MarketRow(
                        symbol=symbol,
                        name=str(item["CompanyName"]).strip(),
                        market="TPEX",
                        trade_date=_roc_date(str(item["Date"])),
                        open=_decimal(item["Open"]),
                        high=_decimal(item["High"]),
                        low=_decimal(item["Low"]),
                        close=_decimal(item["Close"]),
                        volume=_integer(item["TradingShares"]),
                        turnover=_decimal(item["TransactionAmount"]),
                        source="TPEX_OPENAPI",
                    )
                )
            except (KeyError, ValueError):
                continue
        return parsed


def upsert_market_rows(session: Session, rows: list[MarketRow]) -> int:
    count = 0
    for row in rows:
        instrument = session.scalar(
            select(Instrument).where(Instrument.symbol == row.symbol)
        )
        if instrument is None:
            instrument = Instrument(
                symbol=row.symbol,
                name=row.name,
                market=row.market,
                security_type="COMMON_STOCK",
            )
            session.add(instrument)
            session.flush()
        else:
            instrument.name = row.name
            instrument.market = row.market
            instrument.is_active = True

        price = session.scalar(
            select(DailyPrice).where(
                DailyPrice.instrument_id == instrument.id,
                DailyPrice.trade_date == row.trade_date,
            )
        )
        if price is None:
            price = DailyPrice(
                instrument_id=instrument.id,
                trade_date=row.trade_date,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
                turnover=row.turnover,
                source=row.source,
            )
            session.add(price)
        else:
            price.open = row.open
            price.high = row.high
            price.low = row.low
            price.close = row.close
            price.volume = row.volume
            price.turnover = row.turnover
            price.source = row.source
        count += 1
    session.commit()
    return count


REQUIRED_CSV_COLUMNS = {
    "symbol",
    "name",
    "market",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover",
}


def parse_history_csv(content: str, source: str = "CSV_IMPORT") -> list[MarketRow]:
    reader = csv.DictReader(io.StringIO(content))
    missing = REQUIRED_CSV_COLUMNS - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"CSV missing columns: {', '.join(sorted(missing))}")

    rows: list[MarketRow] = []
    for line_number, item in enumerate(reader, start=2):
        symbol = item["symbol"].strip()
        if not is_common_stock(symbol):
            continue
        try:
            rows.append(
                MarketRow(
                    symbol=symbol,
                    name=item["name"].strip(),
                    market=item["market"].strip().upper(),
                    trade_date=datetime.strptime(item["date"], "%Y-%m-%d").date(),
                    open=_decimal(item["open"]),
                    high=_decimal(item["high"]),
                    low=_decimal(item["low"]),
                    close=_decimal(item["close"]),
                    volume=_integer(item["volume"]),
                    turnover=_decimal(item["turnover"]),
                    source=source,
                )
            )
        except (KeyError, ValueError) as exc:
            raise ValueError(f"Invalid CSV row {line_number}: {exc}") from exc
    return rows


def import_history_csv(session: Session, path: Path) -> int:
    return upsert_market_rows(session, parse_history_csv(path.read_text("utf-8-sig")))

