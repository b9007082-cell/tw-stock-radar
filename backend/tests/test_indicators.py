from datetime import date, timedelta

from app.domain import Bar
from app.services.indicators import confirmed_swings, sma


def test_sma_has_expected_warmup_and_values() -> None:
    assert sma([1, 2, 3, 4], 3) == [None, None, 2.0, 3.0]


def test_confirmed_swings_do_not_use_unconfirmed_edge() -> None:
    start = date(2026, 1, 1)
    highs = [1, 2, 5, 2, 1, 2, 9]
    bars = [
        Bar(
            date=start + timedelta(days=index),
            open=value,
            high=value,
            low=value - 0.5,
            close=value,
            volume=100,
        )
        for index, value in enumerate(highs)
    ]
    peaks, _ = confirmed_swings(bars)
    assert peaks == [(2, 5)]

