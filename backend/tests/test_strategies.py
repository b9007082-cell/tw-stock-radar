from datetime import date, timedelta

from app.domain import Bar, SignalLevel
from app.services.strategies import (
    consolidation_signal,
    pullback_resume_signal,
    scan_bars,
    trend_confirmation_signal,
)


def _bar(index: int, close: float, volume: int = 1_000_000) -> Bar:
    return Bar(
        date=date(2026, 1, 1) + timedelta(days=index),
        open=close - 0.1,
        high=close + 0.3,
        low=close - 0.3,
        close=close,
        volume=volume,
        turnover=50_000_000,
    )


def _uptrend_base() -> list[Bar]:
    bars: list[Bar] = []
    offsets = (0.0, 1.5, 3.0, 1.5, 0.5)
    for index in range(65):
        cycle, position = divmod(index, 5)
        close = 50 + cycle * 3 + offsets[position]
        bars.append(_bar(index, close))
    return bars


def _pullback_bars(level: SignalLevel) -> list[Bar]:
    bars = _uptrend_base()
    closes = [87.2, 86.7, 87.2]
    if level == SignalLevel.WATCH:
        closes.append(86.7)
    elif level == SignalLevel.TRIAL:
        closes.append(87.3)
    else:
        closes.append(87.6)
    for close in closes:
        bars.append(_bar(len(bars), close, 800_000))
    return bars


def _breakout_bars(level: SignalLevel) -> list[Bar]:
    bars = _uptrend_base()
    for close in (87.2, 86.7, 87.2):
        bars.append(_bar(len(bars), close, 800_000))
    if level == SignalLevel.WATCH:
        bars.append(_bar(len(bars), 89.0, 800_000))
    elif level == SignalLevel.TRIAL:
        trial = _bar(len(bars), 89.0, 900_000)
        bars.append(
            Bar(
                date=trial.date,
                open=trial.open,
                high=89.6,
                low=trial.low,
                close=trial.close,
                volume=trial.volume,
                turnover=trial.turnover,
            )
        )
    else:
        bars.append(_bar(len(bars), 89.7, 1_600_000))
    return bars


def test_trend_confirmation_requires_full_structure_and_ma_alignment() -> None:
    signal = trend_confirmation_signal(_uptrend_base())
    assert signal is not None
    assert signal.strategy == "TREND_CONFIRMATION"
    assert signal.level == SignalLevel.WATCH
    assert signal.executable is False
    assert signal.metrics["higher_high"] is True
    assert signal.metrics["higher_low"] is True
    assert float(signal.metrics["ma5"]) > float(signal.metrics["ma10"])
    assert float(signal.metrics["ma10"]) > float(signal.metrics["ma20"])


def test_trend_confirmation_rejects_downtrend() -> None:
    bars = [
        _bar(index, 120 - index * 0.7)
        for index in range(70)
    ]
    assert trend_confirmation_signal(bars) is None


def test_pullback_watch_stays_above_ma20() -> None:
    signal = pullback_resume_signal(_pullback_bars(SignalLevel.WATCH))
    assert signal is not None
    assert signal.level == SignalLevel.WATCH
    assert signal.executable is False
    assert signal.metrics["held_ma20"] is True


def test_pullback_trial_is_not_actionable() -> None:
    signal = pullback_resume_signal(_pullback_bars(SignalLevel.TRIAL))
    assert signal is not None
    assert signal.level == SignalLevel.TRIAL
    assert signal.executable is False
    assert signal.metrics["back_above_ma5"] is True
    assert signal.metrics["broke_previous_high"] is False


def test_pullback_resume_is_confirmed_after_previous_high_break() -> None:
    signal = pullback_resume_signal(_pullback_bars(SignalLevel.CONFIRMED))
    assert signal is not None
    assert signal.level == SignalLevel.CONFIRMED
    assert signal.executable is True
    assert signal.entry_zone_low == signal.trigger_price
    assert signal.entry_zone_high == signal.close
    assert signal.stop_price is not None
    assert signal.stop_price < signal.entry_price


def test_pullback_below_ma20_is_rejected() -> None:
    bars = _pullback_bars(SignalLevel.CONFIRMED)
    broken = bars[-3]
    bars[-3] = Bar(
        date=broken.date,
        open=70,
        high=71,
        low=69,
        close=70,
        volume=broken.volume,
        turnover=broken.turnover,
    )
    assert pullback_resume_signal(bars) is None


def test_consolidation_watch_uses_latest_confirmed_peak() -> None:
    signal = consolidation_signal(_breakout_bars(SignalLevel.WATCH))
    assert signal is not None
    assert signal.level == SignalLevel.WATCH
    assert signal.trigger_price == round(float(signal.metrics["latest_peak"]), 2)
    assert signal.executable is False


def test_intraday_breakout_without_close_is_trial_only() -> None:
    signal = consolidation_signal(_breakout_bars(SignalLevel.TRIAL))
    assert signal is not None
    assert signal.level == SignalLevel.TRIAL
    assert signal.executable is False


def test_close_breakout_with_volume_is_confirmed() -> None:
    signal = consolidation_signal(_breakout_bars(SignalLevel.CONFIRMED))
    assert signal is not None
    assert signal.level == SignalLevel.CONFIRMED
    assert signal.executable is True
    assert signal.metrics["volume_confirmed"] is True


def test_scan_keeps_direction_and_buy_point_signals() -> None:
    signals = scan_bars(_pullback_bars(SignalLevel.CONFIRMED))
    strategies = {signal.strategy for signal in signals}
    assert "TREND_CONFIRMATION" in strategies
    assert "PULLBACK_RESUME" in strategies
