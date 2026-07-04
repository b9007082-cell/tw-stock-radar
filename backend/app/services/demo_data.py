import math
import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.services.market_data import MarketRow, upsert_market_rows


def _trading_days(end: date, count: int) -> list[date]:
    days: list[date] = []
    cursor = end
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(days))


def seed_demo(session: Session, end: date | None = None) -> int:
    end = end or date.today()
    days = _trading_days(end, 140)
    randomizer = random.Random(20260704)
    specs = [
        ("2330", "示範趨勢", "TWSE", "trend"),
        ("6488", "示範盤整", "TPEX", "base"),
        ("3017", "示範回檔", "TWSE", "pullback"),
        ("2603", "示範對照", "TWSE", "control"),
        ("5274", "示範強勢", "TPEX", "strong"),
    ]
    rows: list[MarketRow] = []
    for symbol, name, market, pattern in specs:
        closes: list[float] = []
        for index in range(len(days)):
            noise = randomizer.uniform(-0.35, 0.35)
            if pattern == "base":
                if index < 80:
                    value = 42 + index * 0.09 + noise
                else:
                    value = 49 + math.sin(index / 3) * 1.2 + noise
                if index == len(days) - 1:
                    value = 50.8
            elif pattern == "pullback":
                value = 55 + index * 0.22 + noise
                if index >= len(days) - 4:
                    value -= [0, 3.6, 4.1, 4.5][index - (len(days) - 4)]
            elif pattern == "strong":
                value = 35 + index * 0.31 + noise
                if index == len(days) - 2:
                    value -= 4.0
                if index == len(days) - 1:
                    value += 1.8
            elif pattern == "trend":
                value = 70 + index * 0.18 + math.sin(index / 8) + noise
            else:
                value = 60 + math.sin(index / 5) * 5 + noise
            closes.append(round(max(10, value), 2))

        for index, trade_date in enumerate(days):
            close = closes[index]
            previous = closes[index - 1] if index else close
            open_price = round(previous + randomizer.uniform(-0.4, 0.4), 2)
            high = round(max(open_price, close) + randomizer.uniform(0.2, 0.8), 2)
            low = round(min(open_price, close) - randomizer.uniform(0.2, 0.8), 2)
            base_volume = 1_200_000
            volume = int(base_volume * randomizer.uniform(0.65, 1.15))
            if pattern == "base" and index >= len(days) - 5:
                volume = int(base_volume * 0.55)
            if pattern == "strong" and index == len(days) - 1:
                volume = int(base_volume * 1.7)
            rows.append(
                MarketRow(
                    symbol=symbol,
                    name=name,
                    market=market,
                    trade_date=trade_date,
                    open=Decimal(str(open_price)),
                    high=Decimal(str(high)),
                    low=Decimal(str(low)),
                    close=Decimal(str(close)),
                    volume=volume,
                    turnover=Decimal(str(round(volume * close, 2))),
                    source="DEMO_SEED",
                )
            )
    return upsert_market_rows(session, rows)

