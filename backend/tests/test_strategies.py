from datetime import date, timedelta
import math

from app.domain import Bar, SignalLevel
from app.services.strategies import (
    bollinger_squeeze_signal,
    bottom_reversal_signal,
    consolidation_signal,
    lorentzian_ml_signal,
    pullback_resume_signal,
    scan_bars,
    trend_confirmation_signal,
)


def _bar(index: int, close: float, volume: int = 3_000_000) -> Bar:
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
    for index, close in enumerate(closes):
        volume = (
            3_000_000
            if index == len(closes) - 1 and level != SignalLevel.WATCH
            else 2_400_000
        )
        bars.append(_bar(len(bars), close, volume))
    return bars


def _breakout_bars(level: SignalLevel) -> list[Bar]:
    bars = _uptrend_base()
    for close in (87.2, 86.7, 87.2):
        bars.append(_bar(len(bars), close, 2_400_000))
    if level == SignalLevel.WATCH:
        bars.append(_bar(len(bars), 89.0, 2_400_000))
    elif level == SignalLevel.TRIAL:
        trial = _bar(len(bars), 89.0, 3_000_000)
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
        bars.append(_bar(len(bars), 89.7, 3_600_000))
    return bars


def _bottom_reversal_watch_bars() -> list[Bar]:
    bars: list[Bar] = []
    for index in range(65):
        bars.append(_bar(index, 120 - index * 0.1, 2_400_000))
    for close in (118, 114, 110, 105, 99):
        bars.append(_bar(len(bars), close, 1_200_000))
    stop = Bar(
        date=date(2026, 1, 1) + timedelta(days=len(bars)),
        open=96,
        high=98,
        low=90,
        close=97,
        volume=3_000_000,
        turnover=80_000_000,
    )
    bars.append(stop)
    return bars


def _bottom_reversal_confirmed_bars() -> list[Bar]:
    bars = _bottom_reversal_watch_bars()
    confirm = Bar(
        date=date(2026, 1, 1) + timedelta(days=len(bars)),
        open=97.5,
        high=101,
        low=96,
        close=100,
        volume=3_200_000,
        turnover=90_000_000,
    )
    bars.append(confirm)
    return bars


def _lorentzian_bars(volume: int = 3_000_000) -> list[Bar]:
    bars: list[Bar] = []
    for index in range(120):
        close = 80 + (index // 5 % 2) * 2 + math.sin(index / 3) * 1.5 + index * 0.08
        bars.append(
            Bar(
                date=date(2026, 1, 1) + timedelta(days=index),
                open=close - 0.2,
                high=close + 0.8,
                low=close - 0.8,
                close=close,
                volume=volume,
                turnover=100_000_000,
            )
        )
    latest = bars[-1]
    bars[-1] = Bar(
        date=latest.date,
        open=latest.close - 0.4,
        high=max(latest.high, bars[-2].high + 1.0),
        low=latest.close - 1.2,
        close=bars[-2].high + 0.6,
        volume=volume,
        turnover=100_000_000,
    )
    return bars


def _bollinger_squeeze_bars(volume: int = 3_000_000) -> list[Bar]:
    bars: list[Bar] = []
    for index in range(130):
        close = 100 + math.sin(index / 3) * 5
        bars.append(_bar(index, close, volume))
    for index in range(30):
        close = 100 + math.sin(index) * 0.35
        bars.append(_bar(len(bars), close, volume))
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
    assert signal.metrics["pullback_volume_contracting"] is True


def test_pullback_trial_is_not_actionable() -> None:
    signal = pullback_resume_signal(_pullback_bars(SignalLevel.TRIAL))
    assert signal is not None
    assert signal.level == SignalLevel.TRIAL
    assert signal.executable is False
    assert signal.metrics["back_above_ma5"] is True
    assert signal.metrics["broke_previous_high"] is False
    assert signal.metrics["rebound_volume_expanding"] is True


def test_pullback_resume_is_confirmed_after_previous_high_break() -> None:
    signal = pullback_resume_signal(_pullback_bars(SignalLevel.CONFIRMED))
    assert signal is not None
    assert signal.level == SignalLevel.CONFIRMED
    assert signal.executable is True
    assert signal.entry_zone_low == signal.trigger_price
    assert signal.entry_zone_high == signal.close
    assert signal.stop_price is not None
    assert signal.stop_price < signal.entry_price
    assert signal.metrics["pullback_volume_ratio"] < 1
    assert signal.metrics["rebound_volume_ratio"] > 1


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


def test_pullback_without_volume_contraction_is_rejected() -> None:
    bars = _pullback_bars(SignalLevel.CONFIRMED)
    for index in range(65, len(bars) - 1):
        original = bars[index]
        bars[index] = Bar(
            date=original.date,
            open=original.open,
            high=original.high,
            low=original.low,
            close=original.close,
            volume=3_200_000,
            turnover=original.turnover,
        )
    assert pullback_resume_signal(bars) is None


def test_pullback_without_rebound_volume_expansion_is_rejected() -> None:
    bars = _pullback_bars(SignalLevel.CONFIRMED)
    original = bars[-1]
    bars[-1] = Bar(
        date=original.date,
        open=original.open,
        high=original.high,
        low=original.low,
        close=original.close,
        volume=2_300_000,
        turnover=original.turnover,
    )
    assert pullback_resume_signal(bars) is None


def test_consolidation_watch_uses_latest_confirmed_peak() -> None:
    signal = consolidation_signal(_breakout_bars(SignalLevel.WATCH))
    assert signal is not None
    assert signal.level == SignalLevel.WATCH
    assert signal.trigger_price == round(float(signal.metrics["latest_peak"]), 2)
    assert signal.executable is False
    assert signal.metrics["volume_contracting"] is True


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
    assert signal.metrics["consolidation_volume_ratio"] < 1
    assert signal.metrics["breakout_volume_ratio"] > 1.2


def test_consolidation_without_volume_contraction_is_rejected() -> None:
    bars = _breakout_bars(SignalLevel.CONFIRMED)
    for index in range(len(bars) - 21, len(bars) - 1):
        original = bars[index]
        bars[index] = Bar(
            date=original.date,
            open=original.open,
            high=original.high,
            low=original.low,
            close=original.close,
            volume=3_200_000,
            turnover=original.turnover,
        )
    assert consolidation_signal(bars) is None


def test_consolidation_without_breakout_volume_is_rejected() -> None:
    bars = _breakout_bars(SignalLevel.CONFIRMED)
    original = bars[-1]
    bars[-1] = Bar(
        date=original.date,
        open=original.open,
        high=original.high,
        low=original.low,
        close=original.close,
        volume=2_500_000,
        turnover=original.turnover,
    )
    assert consolidation_signal(bars) is None


def test_bottom_reversal_finds_low_volume_stop_signal() -> None:
    signal = bottom_reversal_signal(_bottom_reversal_watch_bars())
    assert signal is not None
    assert signal.strategy == "BOTTOM_REVERSAL"
    assert signal.level == SignalLevel.WATCH
    assert signal.executable is False
    assert signal.metrics["drawdown_percent"] >= 15
    assert signal.metrics["stop_volume_ratio"] >= 2
    assert signal.metrics["stop_candle_confirmed"] is True


def test_bottom_reversal_confirms_after_breaking_stop_candle_high() -> None:
    signal = bottom_reversal_signal(_bottom_reversal_confirmed_bars())
    assert signal is not None
    assert signal.level == SignalLevel.CONFIRMED
    assert signal.executable is True
    assert signal.trigger_price == 98
    assert signal.stop_price == 90
    assert signal.metrics["confirmed_buy"] is True


def test_bottom_reversal_rejects_without_double_volume() -> None:
    bars = _bottom_reversal_confirmed_bars()
    original = bars[-2]
    bars[-2] = Bar(
        date=original.date,
        open=original.open,
        high=original.high,
        low=original.low,
        close=original.close,
        volume=2_300_000,
        turnover=original.turnover,
    )
    assert bottom_reversal_signal(bars) is None


def test_lorentzian_ml_finds_positive_daily_classifier_signal() -> None:
    signal = lorentzian_ml_signal(_lorentzian_bars(), 0.8)
    assert signal is not None
    assert signal.strategy == "LORENTZIAN_ML"
    assert signal.level in {SignalLevel.WATCH, SignalLevel.TRIAL, SignalLevel.CONFIRMED}
    assert signal.metrics["ml_prediction"] > 0
    assert signal.metrics["kernel_bullish"] is True
    assert signal.metrics["latest_volume_lots"] >= 2000


def test_lorentzian_ml_rejects_low_liquidity() -> None:
    assert lorentzian_ml_signal(_lorentzian_bars(volume=1_900_000), 0.8) is None


def test_bollinger_squeeze_finds_narrow_band_watch_signal() -> None:
    signal = bollinger_squeeze_signal(_bollinger_squeeze_bars())
    assert signal is not None
    assert signal.strategy == "BOLLINGER_SQUEEZE"
    assert signal.level in {SignalLevel.WATCH, SignalLevel.TRIAL, SignalLevel.CONFIRMED}
    assert signal.metrics["bollinger_squeeze_confirmed"] is True
    assert signal.metrics["bollinger_width_percentile"] <= 0.2
    assert signal.metrics["latest_volume_lots"] >= 2000


def test_bollinger_squeeze_rejects_low_liquidity() -> None:
    assert bollinger_squeeze_signal(_bollinger_squeeze_bars(volume=1_900_000)) is None


def test_scan_keeps_direction_and_buy_point_signals() -> None:
    signals = scan_bars(_pullback_bars(SignalLevel.CONFIRMED))
    strategies = {signal.strategy for signal in signals}
    assert "TREND_CONFIRMATION" in strategies
    assert "PULLBACK_RESUME" in strategies


def test_scan_includes_bollinger_squeeze() -> None:
    strategies = {signal.strategy for signal in scan_bars(_bollinger_squeeze_bars())}
    assert "BOLLINGER_SQUEEZE" in strategies
