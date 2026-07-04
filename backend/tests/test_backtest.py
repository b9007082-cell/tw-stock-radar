from datetime import date, timedelta

from app.domain import Bar
from app.services.backtest import backtest


def test_backtest_reports_zero_trade_dataset() -> None:
    start = date(2026, 1, 1)
    bars = [
        Bar(
            date=start + timedelta(days=index),
            open=50,
            high=50.5,
            low=49.5,
            close=50,
            volume=1_000_000,
            turnover=50_000_000,
        )
        for index in range(90)
    ]
    report = backtest(bars)
    assert report["trades"] == 0
    assert report["total_return"] == 0
