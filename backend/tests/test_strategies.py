from datetime import date, timedelta

from app.domain import Bar, SignalLevel
from app.services.strategies import _entry_timing, consolidation_signal


def _breakout_bars() -> list[Bar]:
    start = date(2026, 1, 1)
    bars: list[Bar] = []
    for index in range(70):
        if index < 30:
            close = 40 + index * 0.2
            volume = 1_000_000
        else:
            close = 49 + ((index % 6) - 3) * 0.12
            volume = 550_000
        bars.append(
            Bar(
                date=start + timedelta(days=index),
                open=close - 0.1,
                high=close + 0.35,
                low=close - 0.35,
                close=close,
                volume=volume,
            )
        )
    prior_top = max(bar.high for bar in bars[-41:-1])
    bars[-1] = Bar(
        date=bars[-1].date,
        open=prior_top - 0.1,
        high=prior_top + 1.2,
        low=prior_top - 0.2,
        close=prior_top + 0.8,
        volume=1_800_000,
    )
    return bars


def test_consolidation_breakout_is_confirmed() -> None:
    signal = consolidation_signal(_breakout_bars())
    assert signal is not None
    assert signal.level == SignalLevel.CONFIRMED
    assert signal.entry_price is not None
    assert signal.entry_zone_low is not None
    assert signal.entry_zone_high is not None
    assert signal.entry_zone_low <= signal.entry_zone_high
    assert signal.trigger_price is not None
    assert signal.timing_status in {"READY", "WAIT_PULLBACK"}
    assert signal.stop_price is not None


def test_wide_range_is_not_misclassified_as_consolidation() -> None:
    bars = _breakout_bars()
    for index in range(30, 50):
        bar = bars[index]
        bars[index] = Bar(
            date=bar.date,
            open=bar.open,
            high=bar.high + 8,
            low=bar.low - 8,
            close=bar.close,
            volume=bar.volume,
        )
    assert consolidation_signal(bars) is None


def test_entry_timing_rejects_overheated_price() -> None:
    latest = Bar(
        date=date(2026, 7, 3),
        open=108,
        high=111,
        low=107,
        close=110,
        volume=2_000_000,
    )
    _, _, status, note, overheated = _entry_timing(
        strategy="STRONG_PULLBACK",
        level=SignalLevel.CONFIRMED,
        latest=latest,
        ma5=100,
        ma10=97,
        trigger_price=108,
        support_price=97,
    )
    assert status == "OVERHEATED"
    assert overheated is True
    assert "不追價" in note
