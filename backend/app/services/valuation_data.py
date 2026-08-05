from __future__ import annotations

import re
from datetime import date
from typing import Any

import httpx

from app.config import get_settings
from app.domain import ValuationMetrics
from app.services.market_data import is_common_stock


def _roc_date(value: str) -> date:
    raw = re.sub(r"\D", "", value)
    if len(raw) != 7:
        raise ValueError(f"Invalid ROC date: {value!r}")
    year = int(raw[:3]) + 1911
    return date(year, int(raw[3:5]), int(raw[5:7]))


def _number(value: Any) -> float | None:
    text = str(value).replace(",", "").strip()
    if text in {"", "-", "--", "---", "N/A", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


class OfficialValuationClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.settings = get_settings()
        self.client = client or httpx.Client(
            timeout=30,
            headers={"User-Agent": "tw-stock-scanner/0.1"},
            follow_redirects=True,
        )

    def fetch_all(self) -> dict[str, ValuationMetrics]:
        rows: dict[str, ValuationMetrics] = {}
        rows.update(self._fetch_twse())
        rows.update(self._fetch_tpex())
        return rows

    def _fetch_twse(self) -> dict[str, ValuationMetrics]:
        response = self.client.get(self.settings.twse_valuation_url)
        response.raise_for_status()
        rows: dict[str, ValuationMetrics] = {}
        for item in response.json():
            symbol = str(item.get("Code", "")).strip()
            if not is_common_stock(symbol):
                continue
            dividend_yield = _number(item.get("DividendYield"))
            if dividend_yield is None:
                continue
            try:
                rows[symbol] = ValuationMetrics(
                    symbol=symbol,
                    name=str(item.get("Name", "")).strip(),
                    market="TWSE",
                    trade_date=_roc_date(str(item.get("Date", ""))),
                    pe_ratio=_number(item.get("PEratio")),
                    dividend_yield=dividend_yield,
                    dividend_per_share=None,
                    pb_ratio=_number(item.get("PBratio")),
                )
            except ValueError:
                continue
        return rows

    def _fetch_tpex(self) -> dict[str, ValuationMetrics]:
        response = self.client.get(self.settings.tpex_valuation_url)
        response.raise_for_status()
        rows: dict[str, ValuationMetrics] = {}
        for item in response.json():
            symbol = str(item.get("SecuritiesCompanyCode", "")).strip()
            if not is_common_stock(symbol):
                continue
            dividend_yield = _number(item.get("YieldRatio"))
            if dividend_yield is None:
                continue
            try:
                rows[symbol] = ValuationMetrics(
                    symbol=symbol,
                    name=str(item.get("CompanyName", "")).strip(),
                    market="TPEX",
                    trade_date=_roc_date(str(item.get("Date", ""))),
                    pe_ratio=_number(item.get("PriceEarningRatio")),
                    dividend_yield=dividend_yield,
                    dividend_per_share=_number(item.get("DividendPerShare")),
                    pb_ratio=_number(item.get("PriceBookRatio")),
                )
            except ValueError:
                continue
        return rows
