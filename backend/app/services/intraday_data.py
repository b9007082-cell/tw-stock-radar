from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.domain import IntradayBar

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"


def yahoo_ticker(symbol: str, market: str) -> str:
    suffix = ".TWO" if market.upper() == "TPEX" else ".TW"
    return f"{symbol}{suffix}"


class YahooIntradayClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(
            timeout=12,
            follow_redirects=True,
            headers={"User-Agent": "tw-stock-radar/0.2 intraday-ma60"},
        )

    def fetch_60m(self, symbol: str, market: str) -> list[IntradayBar]:
        ticker = yahoo_ticker(symbol, market)
        response = self.client.get(
            YAHOO_CHART_URL.format(ticker=ticker),
            params={
                "range": "3mo",
                "interval": "60m",
                "includePrePost": "false",
                "events": "history",
            },
        )
        response.raise_for_status()
        return parse_yahoo_chart(response.json())


def parse_yahoo_chart(payload: dict[str, Any]) -> list[IntradayBar]:
    result = payload.get("chart", {}).get("result") or []
    if not result:
        return []
    chart = result[0]
    timestamps = chart.get("timestamp") or []
    quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    timezone_name = (chart.get("meta") or {}).get("exchangeTimezoneName") or "Asia/Taipei"
    exchange_tz = ZoneInfo(str(timezone_name))

    bars: list[IntradayBar] = []
    for index, raw_timestamp in enumerate(timestamps):
        try:
            open_price = opens[index]
            high_price = highs[index]
            low_price = lows[index]
            close_price = closes[index]
            volume = volumes[index]
        except IndexError:
            continue
        if None in (open_price, high_price, low_price, close_price, volume):
            continue
        bars.append(
            IntradayBar(
                timestamp=datetime.fromtimestamp(int(raw_timestamp), exchange_tz),
                open=float(open_price),
                high=float(high_price),
                low=float(low_price),
                close=float(close_price),
                volume=int(volume),
            )
        )
    return bars
