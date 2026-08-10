from collections.abc import Sequence
from dataclasses import dataclass
import math

from app.domain import Bar, IntradayBar, SignalLevel, StrategySignal, ValuationMetrics
from app.services.indicators import confirmed_swings, percent_change, sma


MIN_BARS = 65
BREAKOUT_VOLUME_MULTIPLE = 1.2
MAX_VOLUME_CONTRACTION_RATIO = 1.0
PULLBACK_REBOUND_WATCH_VOLUME_RATIO = 0.85
MIN_TRADE_VOLUME_SHARES = 2_000_000
MIN_TRADE_VOLUME_LOTS = MIN_TRADE_VOLUME_SHARES / 1000
BOTTOM_LAUNCH_LOOKBACK_DAYS = 60
BOTTOM_LAUNCH_BASE_DAYS = 20
BOTTOM_LAUNCH_MAX_DISTANCE_FROM_LOW_PERCENT = 45.0
BOTTOM_LAUNCH_MAX_BASE_RANGE_PERCENT = 30.0
BOTTOM_LAUNCH_MAX_BASE_VOLUME_RATIO = 1.05
BOTTOM_LAUNCH_MAX_MA20_DECLINE = -0.005
BOTTOM_LAUNCH_MAX_MA60_DECLINE = -0.03
BOTTOM_LAUNCH_BREAKOUT_VOLUME_MULTIPLE = 1.2
BOTTOM_LAUNCH_WATCH_VOLUME_MULTIPLE = 1.0
BOTTOM_LAUNCH_CONFIRMATION_DISTANCE_PERCENT = 3.0
REVERSAL_LOOKBACK_DAYS = 20
REVERSAL_MIN_DRAWDOWN_PERCENT = 15.0
REVERSAL_SHARP_DROP_DAYS = 5
REVERSAL_SHARP_DROP_PERCENT = 8.0
REVERSAL_MIN_CONSECUTIVE_DOWN_DAYS = 3
REVERSAL_VOLUME_MULTIPLE = 2.0
DISPOSITION_LOOKBACK_DAYS = 30
DISPOSITION_REVERSAL_LOOKBACK_DAYS = 20
DISPOSITION_REVERSAL_MIN_DRAWDOWN_PERCENT = 25.0
DISPOSITION_REVERSAL_MIN_5D_DROP_PERCENT = 18.0
DISPOSITION_REVERSAL_MIN_10D_DROP_PERCENT = 28.0
DISPOSITION_REVERSAL_LIMIT_LIKE_DROP_PERCENT = 8.5
DISPOSITION_REVERSAL_VOLUME_MULTIPLE = 2.0
LORENTZIAN_SOURCE = "close"
LORENTZIAN_NEIGHBORS = 8
LORENTZIAN_LOOKBACK_BARS = 2000
LORENTZIAN_FEATURE_COUNT = 5
LORENTZIAN_MIN_BARS = 80
LORENTZIAN_MAX_RISK_PERCENT = 10.0
LORENTZIAN_REGIME_THRESHOLD = -0.1
LORENTZIAN_ADX_THRESHOLD = 20
LORENTZIAN_KERNEL_LOOKBACK = 8
LORENTZIAN_KERNEL_RELATIVE_WEIGHTING = 8.0
LORENTZIAN_KERNEL_START = 25
BOLLINGER_PERIOD = 20
BOLLINGER_MULTIPLIER = 2.0
BOLLINGER_LOOKBACK = 80
BOLLINGER_MAX_WIDTH_PERCENTILE = 0.2
BOLLINGER_BREAKOUT_VOLUME_MULTIPLE = 1.2
BOLLINGER_MAIN_FORCE_VOLUME_MULTIPLE = 1.5
BOLLINGER_BREAKOUT_LOOKBACK = 5
INTRADAY_MA_PERIOD = 60
INTRADAY_MA_MAX_DISTANCE_PERCENT = 1.5
INTRADAY_MA_READY_DISTANCE_PERCENT = 0.6
INTRADAY_MA_MIN_SLOPE_PERCENT = 0.0
INTRADAY_MA_VOLUME_MULTIPLE = 1.2
HIGH_YIELD_LOOKBACK = 100
HIGH_YIELD_MIN_DIVIDEND_YIELD = 5.0
HIGH_YIELD_MIN_DRAWDOWN_PERCENT = 8.0
HIGH_YIELD_MAX_DISTANCE_FROM_LOW_PERCENT = 35.0
HIGH_YIELD_MAX_PB_RATIO = 2.5


@dataclass(frozen=True)
class TrendContext:
    ma5: float
    ma10: float
    ma20: float
    ma20_slope_5d: float
    vol20: float
    higher_high: bool
    higher_low: bool
    latest_peak_index: int
    latest_peak: float
    latest_trough_index: int
    latest_trough: float
    confirmed: bool


def _trend_context(bars: Sequence[Bar]) -> TrendContext | None:
    if len(bars) < MIN_BARS:
        return None
    closes = [bar.close for bar in bars]
    volumes = [float(bar.volume) for bar in bars]
    ma5s = sma(closes, 5)
    ma10s = sma(closes, 10)
    ma20s = sma(closes, 20)
    vol20s = sma(volumes, 20)
    index = len(bars) - 1
    ma5 = float(ma5s[index] or 0)
    ma10 = float(ma10s[index] or 0)
    ma20 = float(ma20s[index] or 0)
    ma20_5 = float(ma20s[index - 5] or ma20)
    peaks, troughs = confirmed_swings(bars)
    if len(peaks) < 2 or len(troughs) < 2 or min(ma5, ma10, ma20) <= 0:
        return None
    higher_high = peaks[-1][1] > peaks[-2][1]
    higher_low = troughs[-1][1] > troughs[-2][1]
    confirmed = (
        higher_high
        and higher_low
        and bars[-1].close > ma20
        and ma5 > ma10 > ma20
        and ma20 > ma20_5
    )
    return TrendContext(
        ma5=ma5,
        ma10=ma10,
        ma20=ma20,
        ma20_slope_5d=percent_change(ma20, ma20_5),
        vol20=float(vol20s[index] or 0),
        higher_high=higher_high,
        higher_low=higher_low,
        latest_peak_index=peaks[-1][0],
        latest_peak=float(peaks[-1][1]),
        latest_trough_index=troughs[-1][0],
        latest_trough=float(troughs[-1][1]),
        confirmed=confirmed,
    )


def _average(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stddev(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    mean = _average(values)
    return math.sqrt(_average([(value - mean) ** 2 for value in values]))


def _ema(values: Sequence[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    result = [float(values[0])]
    for value in values[1:]:
        result.append((float(value) - result[-1]) * multiplier + result[-1])
    return result


def _macd_metrics(closes: Sequence[float]) -> dict[str, float | bool]:
    if len(closes) < 35:
        return {
            "macd_line": 0.0,
            "macd_signal": 0.0,
            "macd_histogram": 0.0,
            "macd_positive": False,
        }
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = [fast - slow for fast, slow in zip(ema12, ema26, strict=True)]
    signal_line = _ema(macd_line, 9)
    histogram = [line - signal for line, signal in zip(macd_line, signal_line, strict=True)]
    macd_positive = macd_line[-1] > 0
    return {
        "macd_line": macd_line[-1],
        "macd_signal": signal_line[-1],
        "macd_histogram": histogram[-1],
        "macd_positive": macd_positive,
    }


def _kd_metrics(bars: Sequence[Bar], period: int = 9) -> dict[str, float | bool]:
    if len(bars) < period + 3:
        return {
            "kd_k": 0.0,
            "kd_d": 0.0,
            "kd_low_golden_up": False,
        }
    k_values: list[float] = []
    d_values: list[float] = []
    k = 50.0
    d = 50.0
    for index in range(len(bars)):
        if index < period - 1:
            k_values.append(k)
            d_values.append(d)
            continue
        window = bars[index - period + 1 : index + 1]
        low = min(bar.low for bar in window)
        high = max(bar.high for bar in window)
        rsv = 50.0 if high == low else ((bars[index].close - low) / (high - low)) * 100
        k = (2 / 3) * k + (1 / 3) * rsv
        d = (2 / 3) * d + (1 / 3) * k
        k_values.append(k)
        d_values.append(d)
    recent_low = min(k_values[-5:] + d_values[-5:])
    kd_low_golden_up = (
        k_values[-1] > d_values[-1]
        and k_values[-1] > k_values[-2]
        and recent_low < 55
    )
    return {
        "kd_k": k_values[-1],
        "kd_d": d_values[-1],
        "kd_low_golden_up": kd_low_golden_up,
    }


def _buy_confirmation_metrics(
    bars: Sequence[Bar],
    context: TrendContext,
) -> dict[str, float | bool]:
    latest = bars[-1]
    previous = bars[-2]
    latest_volume_lots = latest.volume / 1000
    red_candle = latest.close > latest.open
    closed_above_ma5 = latest.close > context.ma5
    broke_previous_high = latest.close > previous.high
    price_volume_aligned = latest.close > previous.close and latest.volume > previous.volume
    metrics: dict[str, float | bool] = {
        "latest_volume_lots": latest_volume_lots,
        "minimum_volume_lots": MIN_TRADE_VOLUME_LOTS,
        "liquidity_ok": latest.volume >= MIN_TRADE_VOLUME_SHARES,
        "red_candle": red_candle,
        "closed_above_ma5": closed_above_ma5,
        "broke_previous_high": broke_previous_high,
        "price_volume_aligned": price_volume_aligned,
    }
    metrics.update(_kd_metrics(bars))
    metrics.update(_macd_metrics([bar.close for bar in bars]))
    metrics["indicator_ideal"] = bool(metrics["kd_low_golden_up"]) and bool(
        metrics["macd_positive"]
    )
    metrics["photo_conditions_confirmed"] = all(
        bool(metrics[key])
        for key in (
            "liquidity_ok",
            "red_candle",
            "closed_above_ma5",
            "broke_previous_high",
            "price_volume_aligned",
        )
    )
    return metrics


def _metrics(context: TrendContext) -> dict[str, float | bool]:
    return {
        "ma5": context.ma5,
        "ma10": context.ma10,
        "ma20": context.ma20,
        "ma20_slope_5d": context.ma20_slope_5d,
        "vol20": context.vol20,
        "higher_high": context.higher_high,
        "higher_low": context.higher_low,
        "latest_peak_index": float(context.latest_peak_index),
        "latest_peak": context.latest_peak,
        "latest_trough_index": float(context.latest_trough_index),
        "latest_trough": context.latest_trough,
        "trend_confirmed": context.confirmed,
    }


def _range_context(
    bars: Sequence[Bar],
    *,
    range_high: float,
    range_low: float,
    range_high_index: int,
    range_low_index: int,
) -> TrendContext | None:
    if len(bars) < MIN_BARS:
        return None
    closes = [bar.close for bar in bars]
    volumes = [float(bar.volume) for bar in bars]
    ma5s = sma(closes, 5)
    ma10s = sma(closes, 10)
    ma20s = sma(closes, 20)
    vol20s = sma(volumes, 20)
    index = len(bars) - 1
    ma5 = float(ma5s[index] or 0)
    ma10 = float(ma10s[index] or 0)
    ma20 = float(ma20s[index] or 0)
    ma20_5 = float(ma20s[index - 5] or ma20)
    if min(ma5, ma10, ma20, range_high, range_low) <= 0:
        return None
    return TrendContext(
        ma5=ma5,
        ma10=ma10,
        ma20=ma20,
        ma20_slope_5d=percent_change(ma20, ma20_5),
        vol20=float(vol20s[index] or 0),
        higher_high=False,
        higher_low=False,
        latest_peak_index=range_high_index,
        latest_peak=float(range_high),
        latest_trough_index=range_low_index,
        latest_trough=float(range_low),
        confirmed=False,
    )


def _risk(entry: float, stop: float) -> tuple[float, bool]:
    risk_percent = (entry - stop) / entry if entry > 0 else 0
    return round(max(0.0, risk_percent) * 100, 2), 0 < risk_percent < 1


def _signal(
    *,
    strategy: str,
    level: SignalLevel,
    bars: Sequence[Bar],
    context: TrendContext,
    score: int,
    trigger_price: float | None,
    timing_status: str,
    timing_note: str,
    reasons: list[str],
    extra_metrics: dict[str, float | bool] | None = None,
) -> StrategySignal:
    latest = bars[-1]
    confirmed = level == SignalLevel.CONFIRMED and trigger_price is not None
    entry_zone_low = min(trigger_price, latest.close) if confirmed else None
    entry_zone_high = max(trigger_price, latest.close) if confirmed else None
    entry_price = entry_zone_high if confirmed else None
    risk_percent, risk_valid = (
        _risk(entry_price, context.latest_trough)
        if entry_price is not None
        else (0.0, False)
    )
    metrics = _metrics(context)
    if extra_metrics:
        metrics.update(extra_metrics)
    return StrategySignal(
        strategy=strategy,
        level=level,
        signal_date=latest.date,
        score=score,
        close=latest.close,
        entry_price=round(entry_price, 2) if entry_price is not None else None,
        entry_zone_low=(
            round(entry_zone_low, 2) if entry_zone_low is not None else None
        ),
        entry_zone_high=(
            round(entry_zone_high, 2) if entry_zone_high is not None else None
        ),
        trigger_price=(
            round(trigger_price, 2) if trigger_price is not None else None
        ),
        stop_price=round(context.latest_trough, 2),
        risk_percent=risk_percent if confirmed else None,
        timing_status=timing_status,
        timing_note=timing_note,
        overheated=False,
        executable=confirmed and risk_valid,
        reasons=reasons,
        metrics=metrics,
    )


def trend_confirmation_signal(
    bars: Sequence[Bar],
) -> StrategySignal | None:
    context = _trend_context(bars)
    if (
        context is None
        or not context.confirmed
        or bars[-1].volume < MIN_TRADE_VOLUME_SHARES
    ):
        return None
    return _signal(
        strategy="TREND_CONFIRMATION",
        level=SignalLevel.WATCH,
        bars=bars,
        context=context,
        score=65,
        trigger_price=context.latest_peak,
        timing_status="WAIT_CONFIRMATION",
        timing_note=(
            "多頭方向已確認；等待回後買上漲或底部起漲，"
            "方向成立本身不是買點。"
        ),
        reasons=[
            "最近兩個確認波峰呈頭頭高",
            "最近兩個確認波谷呈底底高",
            "收盤站上20日線，且5、10、20日線多頭排列",
            "20日線較5個交易日前上彎",
        ],
    )


def pullback_resume_signal(
    bars: Sequence[Bar],
) -> StrategySignal | None:
    context = _trend_context(bars)
    if context is None or not context.confirmed:
        return None
    closes = [bar.close for bar in bars]
    ma5s = sma(closes, 5)
    ma20s = sma(closes, 20)
    start = context.latest_peak_index + 1
    if start >= len(bars):
        return None
    pullback_indexes = range(start, len(bars))
    had_pullback = any(
        bars[index].close < float(ma5s[index] or 0)
        for index in pullback_indexes
    )
    held_ma20 = all(
        bars[index].close >= float(ma20s[index] or 0)
        for index in pullback_indexes
    )
    if not had_pullback or not held_ma20:
        return None

    latest = bars[-1]
    previous = bars[-2]
    pullback_volume_indexes = list(range(start, max(start, len(bars) - 1)))
    if not pullback_volume_indexes:
        return None
    previous_volume_start = max(0, start - len(pullback_volume_indexes))
    previous_volume_indexes = list(range(previous_volume_start, start))
    if len(previous_volume_indexes) != len(pullback_volume_indexes):
        return None
    pullback_volume_avg = _average(
        [float(bars[index].volume) for index in pullback_volume_indexes]
    )
    previous_volume_avg = _average(
        [float(bars[index].volume) for index in previous_volume_indexes]
    )
    pullback_volume_ratio = (
        pullback_volume_avg / previous_volume_avg if previous_volume_avg else 0.0
    )
    pullback_volume_contracting = (
        0 < pullback_volume_ratio < MAX_VOLUME_CONTRACTION_RATIO
    )
    rebound_volume_ratio = (
        float(latest.volume) / pullback_volume_avg if pullback_volume_avg else 0.0
    )
    rebound_volume_expanding = rebound_volume_ratio > 1.0
    rebound_volume_watch_ok = (
        rebound_volume_ratio >= PULLBACK_REBOUND_WATCH_VOLUME_RATIO
    )
    if not pullback_volume_contracting:
        return None

    confirmation_metrics = _buy_confirmation_metrics(bars, context)
    if not bool(confirmation_metrics["liquidity_ok"]):
        return None

    back_above_ma5 = latest.close > context.ma5
    broke_previous_high = latest.close > previous.high
    if back_above_ma5 and broke_previous_high:
        if rebound_volume_expanding:
            if not bool(confirmation_metrics["photo_conditions_confirmed"]):
                return None
            level = SignalLevel.CONFIRMED
            timing_status = "READY"
            timing_note = (
                "回檔守住20日線後，收盤站回5日線並突破前一日高點，"
                "且轉強量大於回檔均量，回後買上漲買點成立。"
            )
            score = 92
        elif rebound_volume_watch_ok:
            level = SignalLevel.TRIAL
            timing_status = "TRIAL_ENTRY"
            timing_note = (
                "價格已站回5日線並突破前一日高點，但轉強量只有回檔均量的"
                f"{rebound_volume_ratio:.2f}倍，先列觀察，不視為確認買點。"
            )
            score = 78
        else:
            return None
    elif back_above_ma5:
        if not rebound_volume_watch_ok:
            return None
        level = SignalLevel.TRIAL
        timing_status = "TRIAL_ENTRY"
        timing_note = (
            "已站回5日線且轉強量接近或大於回檔均量，"
            "但尚未突破前一日高點，只視為轉強中。"
        )
        score = 80
    else:
        level = SignalLevel.WATCH
        timing_status = "WAIT_PULLBACK"
        timing_note = (
            "多頭回檔仍守20日線且回檔量縮，"
            "等待站回5日線並突破前一日高點。"
        )
        score = 70

    return _signal(
        strategy="PULLBACK_RESUME",
        level=level,
        bars=bars,
        context=context,
        score=score,
        trigger_price=previous.high,
        timing_status=timing_status,
        timing_note=timing_note,
        reasons=[
            "多頭確認：頭頭高、底底高",
            (
                f"成交張數 {confirmation_metrics['latest_volume_lots']:.0f} 張，"
                f"大於{MIN_TRADE_VOLUME_LOTS:.0f}張"
            ),
            "回檔期間收盤守在20日線之上",
            f"回檔均量為前段均量的 {pullback_volume_ratio:.2f} 倍",
            (
                "紅K收盤站回5日線、突破前一日高點，且轉強量大於回檔均量"
                if level == SignalLevel.CONFIRMED
                else "價格轉強但轉強量尚未完全確認，先列觀察"
                if back_above_ma5 and broke_previous_high
                else "等待回檔後重新轉強"
            ),
            (
                "KD低檔黃金交叉向上，MACD維持0軸之上"
                if bool(confirmation_metrics["indicator_ideal"])
                else "KD/MACD指標尚未完全同步，需留意追蹤"
            ),
        ],
        extra_metrics={
            "pullback_start_index": float(start),
            "previous_high": previous.high,
            "held_ma20": held_ma20,
            "back_above_ma5": back_above_ma5,
            "broke_previous_high": broke_previous_high,
            "pullback_volume_avg": pullback_volume_avg,
            "previous_advance_volume_avg": previous_volume_avg,
            "pullback_volume_ratio": pullback_volume_ratio,
            "pullback_volume_contracting": pullback_volume_contracting,
            "rebound_volume_ratio": rebound_volume_ratio,
            "rebound_volume_expanding": rebound_volume_expanding,
            "rebound_volume_watch_ok": rebound_volume_watch_ok,
            "rebound_volume_watch_threshold": PULLBACK_REBOUND_WATCH_VOLUME_RATIO,
            **confirmation_metrics,
        },
    )


def consolidation_signal(
    bars: Sequence[Bar],
) -> StrategySignal | None:
    if len(bars) < BOTTOM_LAUNCH_LOOKBACK_DAYS + BOTTOM_LAUNCH_BASE_DAYS:
        return None
    latest = bars[-1]
    previous = bars[-2]
    if latest.volume < MIN_TRADE_VOLUME_SHARES:
        return None

    closes = [bar.close for bar in bars]
    volumes = [float(bar.volume) for bar in bars]
    ma20s = sma(closes, 20)
    ma60s = sma(closes, 60)
    index = len(bars) - 1
    ma20 = float(ma20s[index] or 0)
    ma20_5 = float(ma20s[index - 5] or ma20)
    ma60 = float(ma60s[index] or 0)
    ma60_5 = float(ma60s[index - 5] or ma60)
    if min(ma20, ma60, latest.close) <= 0:
        return None

    lookback_window = bars[-BOTTOM_LAUNCH_LOOKBACK_DAYS:]
    base_window = bars[-BOTTOM_LAUNCH_BASE_DAYS - 1 : -1]
    previous_volume_window = bars[
        -BOTTOM_LAUNCH_BASE_DAYS * 2 - 1 : -BOTTOM_LAUNCH_BASE_DAYS - 1
    ]
    if len(base_window) != BOTTOM_LAUNCH_BASE_DAYS or len(previous_volume_window) != BOTTOM_LAUNCH_BASE_DAYS:
        return None

    lookback_low = min(bar.low for bar in lookback_window)
    lookback_high = max(bar.high for bar in lookback_window)
    lookback_low_index = len(bars) - BOTTOM_LAUNCH_LOOKBACK_DAYS + min(
        range(len(lookback_window)),
        key=lambda item: lookback_window[item].low,
    )
    base_low = min(bar.low for bar in base_window)
    base_high = max(bar.high for bar in base_window)
    base_high_index = len(bars) - BOTTOM_LAUNCH_BASE_DAYS - 1 + max(
        range(len(base_window)),
        key=lambda item: base_window[item].high,
    )
    stop_price = min(base_low, lookback_low)
    if min(lookback_low, base_low, base_high, stop_price) <= 0:
        return None

    distance_from_low_percent = ((latest.close / lookback_low) - 1.0) * 100
    drawdown_from_high_percent = ((lookback_high - latest.close) / lookback_high) * 100
    base_range_percent = ((base_high / base_low) - 1.0) * 100
    ma20_slope_5d = percent_change(ma20, ma20_5)
    ma60_slope_5d = percent_change(ma60, ma60_5)
    base_volume_avg = _average([float(bar.volume) for bar in base_window])
    previous_volume_avg = _average(
        [float(bar.volume) for bar in previous_volume_window]
    )
    base_volume_ratio = base_volume_avg / previous_volume_avg if previous_volume_avg else 0.0
    breakout_volume_ratio = latest.volume / base_volume_avg if base_volume_avg else 0.0

    bottom_zone = (
        0 <= distance_from_low_percent <= BOTTOM_LAUNCH_MAX_DISTANCE_FROM_LOW_PERCENT
    )
    base_compact = base_range_percent <= BOTTOM_LAUNCH_MAX_BASE_RANGE_PERCENT
    base_volume_contracting = 0 < base_volume_ratio <= BOTTOM_LAUNCH_MAX_BASE_VOLUME_RATIO
    ma20_turning = latest.close > ma20 and ma20_slope_5d >= BOTTOM_LAUNCH_MAX_MA20_DECLINE
    ma60_not_collapsing = ma60_slope_5d >= BOTTOM_LAUNCH_MAX_MA60_DECLINE
    setup_ready = (
        bottom_zone
        and base_compact
        and base_volume_contracting
        and ma20_turning
        and ma60_not_collapsing
    )
    if not setup_ready:
        return None

    context = _range_context(
        bars,
        range_high=base_high,
        range_low=stop_price,
        range_high_index=base_high_index,
        range_low_index=lookback_low_index,
    )
    if context is None:
        return None
    confirmation_metrics = _buy_confirmation_metrics(bars, context)
    trigger = base_high
    prior10_high = max(bar.high for bar in bars[-11:-1])
    close_breaks_20d_high = latest.close > base_high
    close_breaks_10d_high = latest.close > prior10_high
    volume_confirmed = (
        breakout_volume_ratio >= BOTTOM_LAUNCH_BREAKOUT_VOLUME_MULTIPLE
    )
    volume_watch_ok = breakout_volume_ratio >= BOTTOM_LAUNCH_WATCH_VOLUME_MULTIPLE
    price_volume_aligned = bool(confirmation_metrics["price_volume_aligned"])

    if close_breaks_20d_high and volume_confirmed:
        if not (
            bool(confirmation_metrics["red_candle"])
            and bool(confirmation_metrics["broke_previous_high"])
            and price_volume_aligned
        ):
            return None
        level = SignalLevel.CONFIRMED
        timing_status = "READY"
        timing_note = (
            "低位整理量縮後，今日放量收盤突破近20日整理壓力，"
            "底部起漲確認買點成立。"
        )
        score = 94
    elif close_breaks_10d_high and volume_watch_ok:
        level = SignalLevel.TRIAL
        timing_status = "TRIAL_ENTRY"
        timing_note = (
            "低位整理後已突破近10日短壓且量能轉強，先列轉強；"
            "等待收盤突破近20日整理壓力才升級確認。"
        )
        score = 82
    elif (
        latest.close <= trigger
        and latest.close > ma20
        and ((trigger - latest.close) / trigger) * 100
        <= BOTTOM_LAUNCH_CONFIRMATION_DISTANCE_PERCENT
    ):
        level = SignalLevel.WATCH
        timing_status = "WAIT_CONFIRMATION"
        timing_note = (
            "低位整理區已站回20日線，距近20日壓力不遠；"
            "等待放量突破壓力。"
        )
        score = 72
    else:
        return None

    return _signal(
        strategy="CONSOLIDATION_BREAKOUT",
        level=level,
        bars=bars,
        context=context,
        score=score,
        trigger_price=trigger,
        timing_status=timing_status,
        timing_note=timing_note,
        reasons=[
            (
                f"成交張數 {confirmation_metrics['latest_volume_lots']:.0f} 張，"
                f"大於{MIN_TRADE_VOLUME_LOTS:.0f}張"
            ),
            f"距近{BOTTOM_LAUNCH_LOOKBACK_DAYS}日低點 {distance_from_low_percent:.1f}%，符合低位起漲範圍",
            f"近{BOTTOM_LAUNCH_BASE_DAYS}日整理區間 {base_range_percent:.1f}%",
            f"整理均量為前段均量的 {base_volume_ratio:.2f} 倍，量能未失控放大",
            f"20MA斜率 {ma20_slope_5d * 100:+.2f}%，60MA斜率 {ma60_slope_5d * 100:+.2f}%",
            (
                "收盤突破近20日整理壓力且成交量高於整理均量1.2倍"
                if level == SignalLevel.CONFIRMED
                else "等待收盤站穩近20日整理壓力"
            ),
            (
                "KD低檔黃金交叉向上，MACD維持0軸之上"
                if bool(confirmation_metrics["indicator_ideal"])
                else "KD/MACD指標尚未完全同步，需留意追蹤"
            ),
        ],
        extra_metrics={
            "previous_high": previous.high,
            "volume_ratio": breakout_volume_ratio,
            "volume_confirmed": volume_confirmed,
            "base_volume_avg": base_volume_avg,
            "previous_volume_avg": previous_volume_avg,
            "base_volume_ratio": base_volume_ratio,
            "consolidation_volume_avg": base_volume_avg,
            "consolidation_volume_ratio": base_volume_ratio,
            "volume_contracting": base_volume_contracting,
            "breakout_volume_ratio": breakout_volume_ratio,
            "volume_watch_ok": volume_watch_ok,
            "lookback_low": lookback_low,
            "lookback_high": lookback_high,
            "base_low": base_low,
            "base_high": base_high,
            "prior10_high": prior10_high,
            "distance_from_low_percent": distance_from_low_percent,
            "drawdown_from_high_percent": drawdown_from_high_percent,
            "base_range_percent": base_range_percent,
            "bottom_zone": bottom_zone,
            "base_compact": base_compact,
            "ma20": ma20,
            "ma60": ma60,
            "ma60_slope_5d": ma60_slope_5d,
            "ma20_turning": ma20_turning,
            "ma60_not_collapsing": ma60_not_collapsing,
            "close_breaks_10d_high": close_breaks_10d_high,
            "close_breaks_20d_high": close_breaks_20d_high,
            **confirmation_metrics,
        },
    )


def _consecutive_down_days(bars: Sequence[Bar]) -> int:
    count = 0
    for index in range(len(bars) - 1, 0, -1):
        if bars[index].close < bars[index - 1].close:
            count += 1
        else:
            break
    return count


def _is_stopping_candle(bar: Bar) -> bool:
    candle_range = max(0.0, bar.high - bar.low)
    if candle_range <= 0:
        return False
    body = abs(bar.close - bar.open)
    lower_shadow = min(bar.open, bar.close) - bar.low
    close_location = (bar.close - bar.low) / candle_range
    long_lower_shadow = lower_shadow >= max(body * 1.2, candle_range * 0.35)
    doji = body <= candle_range * 0.2 and close_location >= 0.45
    bullish_reversal = bar.close > bar.open and close_location >= 0.55
    return long_lower_shadow or doji or bullish_reversal


def _limit_like_drop_days(bars: Sequence[Bar]) -> int:
    count = 0
    for index in range(1, len(bars)):
        previous = bars[index - 1]
        current = bars[index]
        if previous.close <= 0:
            continue
        close_drop = ((previous.close - current.close) / previous.close) * 100
        intraday_drop = ((previous.close - current.low) / previous.close) * 100
        if (
            close_drop >= DISPOSITION_REVERSAL_LIMIT_LIKE_DROP_PERCENT
            or intraday_drop >= DISPOSITION_REVERSAL_LIMIT_LIKE_DROP_PERCENT
        ):
            count += 1
    return count


def _disposition_similarity_score(
    *,
    drawdown_percent: float,
    five_day_drop_percent: float,
    ten_day_drop_percent: float,
    consecutive_down_days: int,
    limit_like_drop_days: int,
    stop_volume_ratio: float,
    stop_bar: Bar,
    confirmed_buy: bool,
) -> float:
    candle_range = max(0.0, stop_bar.high - stop_bar.low)
    lower_shadow_ratio = (
        (min(stop_bar.open, stop_bar.close) - stop_bar.low) / candle_range
        if candle_range > 0
        else 0.0
    )
    score = 0.0
    score += 22 * min(1.0, max(0.0, (drawdown_percent - 25.0) / 20.0))
    score += 18 * min(1.0, max(five_day_drop_percent, ten_day_drop_percent) / 35.0)
    score += 16 * min(1.0, consecutive_down_days / 4)
    score += 14 * min(1.0, limit_like_drop_days / 3)
    score += 16 * min(1.0, (stop_volume_ratio - 2.0) / 2.0)
    score += 8 * min(1.0, max(0.0, lower_shadow_ratio) / 0.45)
    score += 6 if confirmed_buy else 0
    return round(min(100.0, score), 1)


def disposition_reversal_signal(
    bars: Sequence[Bar],
) -> StrategySignal | None:
    """Find disposal-stock style panic-to-rebound setups from daily OHLCV.

    This is a price/volume proxy. Official TPEx/TWSE disposition公告 is not part
    of the daily OHLCV snapshots yet, so metrics are labelled as inferred.
    """
    if len(bars) < MIN_BARS:
        return None
    latest = bars[-1]
    previous = bars[-2]
    pre_stop = bars[-3]
    if min(latest.close, previous.high, previous.low, pre_stop.volume) <= 0:
        return None

    latest_confirms_previous = latest.close > previous.high and latest.close > latest.open
    stop_bar = previous if latest_confirms_previous else latest
    before_stop_bar = pre_stop if latest_confirms_previous else previous

    lookback_window = bars[-DISPOSITION_REVERSAL_LOOKBACK_DAYS:]
    if len(lookback_window) < DISPOSITION_REVERSAL_LOOKBACK_DAYS:
        return None
    recent_high = max(bar.high for bar in lookback_window)
    recent_low = min(bar.low for bar in lookback_window)
    recent_high_index = len(bars) - DISPOSITION_REVERSAL_LOOKBACK_DAYS + max(
        range(len(lookback_window)),
        key=lambda index: lookback_window[index].high,
    )
    recent_low_index = len(bars) - DISPOSITION_REVERSAL_LOOKBACK_DAYS + min(
        range(len(lookback_window)),
        key=lambda index: lookback_window[index].low,
    )
    if recent_high <= 0 or stop_bar.low <= 0:
        return None

    drawdown_percent = ((recent_high - stop_bar.low) / recent_high) * 100
    five_day_start = bars[-6]
    ten_day_start = bars[-11] if len(bars) >= 11 else bars[0]
    five_day_drop_percent = (
        ((five_day_start.close - stop_bar.low) / five_day_start.close) * 100
        if five_day_start.close > 0
        else 0.0
    )
    ten_day_drop_percent = (
        ((ten_day_start.close - stop_bar.low) / ten_day_start.close) * 100
        if ten_day_start.close > 0
        else 0.0
    )
    decline_bars = bars[:-1] if latest_confirms_previous else bars
    consecutive_down_days = _consecutive_down_days(decline_bars)
    recent_disposition_window = decline_bars[-DISPOSITION_LOOKBACK_DAYS:]
    limit_like_drop_days = _limit_like_drop_days(recent_disposition_window)
    suspected_disposition_rhythm = (
        consecutive_down_days >= REVERSAL_MIN_CONSECUTIVE_DOWN_DAYS
        or limit_like_drop_days >= 2
        or five_day_drop_percent >= DISPOSITION_REVERSAL_MIN_5D_DROP_PERCENT
        or ten_day_drop_percent >= DISPOSITION_REVERSAL_MIN_10D_DROP_PERCENT
    )
    severe_decline = (
        drawdown_percent >= DISPOSITION_REVERSAL_MIN_DRAWDOWN_PERCENT
        and suspected_disposition_rhythm
    )

    stop_volume_ratio = float(stop_bar.volume) / float(before_stop_bar.volume)
    stop_volume_confirmed = stop_volume_ratio >= DISPOSITION_REVERSAL_VOLUME_MULTIPLE
    stop_candle_confirmed = _is_stopping_candle(stop_bar)
    low_zone = stop_bar.low <= recent_low * 1.03
    stop_signal_confirmed = (
        severe_decline
        and low_zone
        and stop_volume_confirmed
        and stop_candle_confirmed
        and stop_bar.volume >= MIN_TRADE_VOLUME_SHARES
    )
    if not stop_signal_confirmed:
        return None

    context = _range_context(
        bars,
        range_high=recent_high,
        range_low=stop_bar.low,
        range_high_index=recent_high_index,
        range_low_index=recent_low_index,
    )
    if context is None:
        return None

    confirmed_buy = (
        latest_confirms_previous
        and latest.close > latest.open
        and latest.volume >= MIN_TRADE_VOLUME_SHARES
    )
    ma20_value = float(sma([bar.close for bar in bars], 20)[-1] or 0.0)
    deviation_rate = ((stop_bar.close - ma20_value) / ma20_value) * 100 if ma20_value > 0 else 0.0
    similarity_score = _disposition_similarity_score(
        drawdown_percent=drawdown_percent,
        five_day_drop_percent=five_day_drop_percent,
        ten_day_drop_percent=ten_day_drop_percent,
        consecutive_down_days=consecutive_down_days,
        limit_like_drop_days=limit_like_drop_days,
        stop_volume_ratio=stop_volume_ratio,
        stop_bar=stop_bar,
        confirmed_buy=confirmed_buy,
    )
    inferred_days_to_release = max(0, 10 - min(10, limit_like_drop_days + 2))
    inferred_disposition_status = (
        "疑似處置急跌後止跌"
        if limit_like_drop_days >= 2
        else "急跌止跌觀察"
    )

    if confirmed_buy:
        level = SignalLevel.CONFIRMED
        timing_status = "READY"
        timing_note = (
            "疑似處置股急跌後出現爆量止跌K，今日上漲收盤突破止跌K高點；"
            "屬高波動反彈確認點，跌破止跌K低點需出場。"
        )
        trigger_price = stop_bar.high
        score = int(min(96, 80 + similarity_score * 0.16))
    else:
        level = SignalLevel.WATCH
        timing_status = "WAIT_CONFIRMATION"
        timing_note = (
            "疑似處置股急跌後已出現爆量止跌K；先觀察，等下一根上漲收盤突破"
            "止跌K高點才確認，不提前追高。"
        )
        trigger_price = stop_bar.high
        score = int(min(84, 66 + similarity_score * 0.18))

    risk_percent, risk_valid = _risk(latest.close, stop_bar.low)
    signal = _signal(
        strategy="DISPOSITION_REVERSAL",
        level=level,
        bars=bars,
        context=context,
        score=score,
        trigger_price=trigger_price,
        timing_status=timing_status,
        timing_note=timing_note,
        reasons=[
            f"近{DISPOSITION_REVERSAL_LOOKBACK_DAYS}日高點回落 {drawdown_percent:.1f}%，符合處置股急跌後型態",
            f"近5日跌幅 {five_day_drop_percent:.1f}%、近10日跌幅 {ten_day_drop_percent:.1f}%",
            f"近{DISPOSITION_LOOKBACK_DAYS}日疑似跌停/急跌日 {limit_like_drop_days} 天",
            f"止跌K成交量為前一日 {stop_volume_ratio:.2f} 倍，成交 {stop_bar.volume / 1000:.0f} 張",
            f"中探針型態相似度 {similarity_score:.0f} 分，偏離20MA {deviation_rate:.1f}%",
            (
                "上漲收盤突破止跌K高點，處置反彈確認"
                if confirmed_buy
                else "等待上漲收盤突破止跌K高點"
            ),
            "此分類為價量推估版，正式處置天數仍需以證交所/櫃買公告為準",
        ],
        extra_metrics={
            "latest_volume_lots": latest.volume / 1000,
            "stop_volume_lots": stop_bar.volume / 1000,
            "minimum_volume_lots": MIN_TRADE_VOLUME_LOTS,
            "drawdown_percent": drawdown_percent,
            "five_day_drop_percent": five_day_drop_percent,
            "ten_day_drop_percent": ten_day_drop_percent,
            "consecutive_down_days": float(consecutive_down_days),
            "limit_like_drop_days": float(limit_like_drop_days),
            "suspected_disposition_rhythm": suspected_disposition_rhythm,
            "inferred_disposition_status": inferred_disposition_status,
            "inferred_days_to_release": float(inferred_days_to_release),
            "stop_volume_ratio": stop_volume_ratio,
            "stop_volume_confirmed": stop_volume_confirmed,
            "stop_candle_confirmed": stop_candle_confirmed,
            "low_zone": low_zone,
            "previous_stop_high": stop_bar.high,
            "previous_stop_low": stop_bar.low,
            "confirmed_buy": confirmed_buy,
            "disposition_similarity_score": similarity_score,
            "deviation_rate_percent": deviation_rate,
            "ma20": ma20_value,
            "official_disposition_data_available": False,
            "structure_risk_percent": risk_percent,
            "structure_risk_valid": risk_valid,
        },
    )
    return StrategySignal(
        **{
            **signal.__dict__,
            "stop_price": round(stop_bar.low, 2),
            "risk_percent": risk_percent if confirmed_buy else None,
            "executable": confirmed_buy and risk_valid,
        }
    )


def bottom_reversal_signal(
    bars: Sequence[Bar],
) -> StrategySignal | None:
    if len(bars) < MIN_BARS:
        return None
    latest = bars[-1]
    previous = bars[-2]
    pre_stop = bars[-3]
    if min(latest.close, previous.high, previous.low, pre_stop.volume) <= 0:
        return None
    latest_confirms_previous = latest.close > previous.high and latest.close > latest.open
    stop_bar = previous if latest_confirms_previous else latest
    before_stop_bar = pre_stop if latest_confirms_previous else previous

    lookback_window = bars[-REVERSAL_LOOKBACK_DAYS:]
    if len(lookback_window) < REVERSAL_LOOKBACK_DAYS:
        return None
    recent_high = max(bar.high for bar in lookback_window)
    recent_low = min(bar.low for bar in lookback_window)
    recent_high_index = len(bars) - REVERSAL_LOOKBACK_DAYS + max(
        range(len(lookback_window)),
        key=lambda index: lookback_window[index].high,
    )
    recent_low_index = len(bars) - REVERSAL_LOOKBACK_DAYS + min(
        range(len(lookback_window)),
        key=lambda index: lookback_window[index].low,
    )

    drawdown_percent = (
        ((recent_high - stop_bar.low) / recent_high) * 100
        if recent_high > 0
        else 0.0
    )
    sharp_start = bars[-REVERSAL_SHARP_DROP_DAYS - 1]
    sharp_drop_percent = (
        ((sharp_start.close - stop_bar.low) / sharp_start.close) * 100
        if sharp_start.close > 0
        else 0.0
    )
    decline_bars = bars[:-1] if latest_confirms_previous else bars
    consecutive_down_days = _consecutive_down_days(decline_bars)
    severe_decline = (
        drawdown_percent >= REVERSAL_MIN_DRAWDOWN_PERCENT
        and (
            consecutive_down_days >= REVERSAL_MIN_CONSECUTIVE_DOWN_DAYS
            or sharp_drop_percent >= REVERSAL_SHARP_DROP_PERCENT
        )
    )

    stop_volume_ratio = float(stop_bar.volume) / float(before_stop_bar.volume)
    stop_volume_confirmed = stop_volume_ratio >= REVERSAL_VOLUME_MULTIPLE
    stop_candle_confirmed = _is_stopping_candle(stop_bar)
    low_zone = stop_bar.low <= recent_low * 1.03
    stop_signal_confirmed = (
        severe_decline
        and low_zone
        and stop_volume_confirmed
        and stop_candle_confirmed
        and stop_bar.volume >= MIN_TRADE_VOLUME_SHARES
    )
    if not stop_signal_confirmed:
        return None

    context = _range_context(
        bars,
        range_high=recent_high,
        range_low=stop_bar.low,
        range_high_index=recent_high_index,
        range_low_index=recent_low_index,
    )
    if context is None:
        return None

    confirmed_buy = (
        latest_confirms_previous
        and latest.close > latest.open
        and latest.volume >= MIN_TRADE_VOLUME_SHARES
    )
    if confirmed_buy:
        level = SignalLevel.CONFIRMED
        timing_status = "READY"
        timing_note = (
            "急跌超過15%後出現低檔爆量止跌K，今日上漲收盤突破"
            "前一日止跌K最高點，搶反彈確認買點成立；若跌破前一日K最低點出場。"
        )
        trigger_price = stop_bar.high
        score = 88
    else:
        level = SignalLevel.WATCH
        timing_status = "WAIT_CONFIRMATION"
        timing_note = (
            "急跌後已出現低檔爆量止跌K，先列觀察；等待隔日上漲收盤突破"
            "止跌K最高點才確認，未確認前不追。"
        )
        trigger_price = stop_bar.high
        score = 74

    return _signal(
        strategy="BOTTOM_REVERSAL",
        level=level,
        bars=bars,
        context=context,
        score=score,
        trigger_price=trigger_price,
        timing_status=timing_status,
        timing_note=timing_note,
        reasons=[
            f"近{REVERSAL_LOOKBACK_DAYS}日高點回落 {drawdown_percent:.1f}%，超過15%",
            f"止跌K成交量為前一日 {stop_volume_ratio:.2f} 倍，符合低檔爆大量",
            "止跌K型態符合長下影線、十字線或實體紅K棒",
            (
                "上漲收盤突破前一日止跌K最高點，確認買點成立"
                if confirmed_buy
                else "等待上漲收盤突破前一日止跌K最高點"
            ),
            "跌破前一日K線最低點視為搶反彈失敗，必須出場",
        ],
        extra_metrics={
            "latest_volume_lots": latest.volume / 1000,
            "stop_volume_lots": stop_bar.volume / 1000,
            "minimum_volume_lots": MIN_TRADE_VOLUME_LOTS,
            "drawdown_percent": drawdown_percent,
            "sharp_drop_percent": sharp_drop_percent,
            "consecutive_down_days": float(consecutive_down_days),
            "stop_volume_ratio": stop_volume_ratio,
            "stop_volume_confirmed": stop_volume_confirmed,
            "stop_candle_confirmed": stop_candle_confirmed,
            "low_zone": low_zone,
            "previous_stop_high": stop_bar.high,
            "previous_stop_low": stop_bar.low,
            "confirmed_buy": confirmed_buy,
        },
    )


def _bollinger_series(
    closes: Sequence[float],
    period: int = BOLLINGER_PERIOD,
    multiplier: float = BOLLINGER_MULTIPLIER,
) -> list[tuple[float, float, float, float] | None]:
    result: list[tuple[float, float, float, float] | None] = [None] * len(closes)
    for index in range(period - 1, len(closes)):
        window = closes[index - period + 1 : index + 1]
        middle = _average(window)
        deviation = _stddev(window)
        upper = middle + deviation * multiplier
        lower = middle - deviation * multiplier
        width_percent = ((upper - lower) / middle) * 100 if middle > 0 else 0.0
        result[index] = (upper, middle, lower, width_percent)
    return result


def bollinger_squeeze_signal(
    bars: Sequence[Bar],
) -> StrategySignal | None:
    if len(bars) < BOLLINGER_LOOKBACK + BOLLINGER_PERIOD:
        return None
    latest = bars[-1]
    previous = bars[-2]
    if latest.volume < MIN_TRADE_VOLUME_SHARES:
        return None
    closes = [bar.close for bar in bars]
    bands = _bollinger_series(closes)
    latest_band = bands[-1]
    previous_band = bands[-2]
    if latest_band is None or previous_band is None:
        return None
    upper, middle, lower, width_percent = latest_band
    previous_upper, _previous_middle, _previous_lower, previous_width_percent = previous_band
    if middle <= 0 or lower <= 0:
        return None

    previous_widths = [
        band[3]
        for band in bands[-BOLLINGER_LOOKBACK - 1 : -1]
        if band is not None and band[3] > 0
    ]
    if len(previous_widths) < BOLLINGER_LOOKBACK // 2:
        return None
    previous_narrower_count = sum(
        1 for width in previous_widths if width <= previous_width_percent
    )
    previous_width_percentile = previous_narrower_count / len(previous_widths)
    latest_narrower_count = sum(1 for width in previous_widths if width <= width_percent)
    width_percentile = latest_narrower_count / len(previous_widths)
    squeeze_confirmed = previous_width_percentile <= BOLLINGER_MAX_WIDTH_PERCENTILE
    if not squeeze_confirmed:
        return None

    recent_window = bars[-BOLLINGER_LOOKBACK:]
    range_high = max(bar.high for bar in recent_window)
    range_low = min(bar.low for bar in recent_window)
    range_high_index = len(bars) - BOLLINGER_LOOKBACK + max(
        range(len(recent_window)),
        key=lambda index: recent_window[index].high,
    )
    range_low_index = len(bars) - BOLLINGER_LOOKBACK + min(
        range(len(recent_window)),
        key=lambda index: recent_window[index].low,
    )
    context = _range_context(
        bars,
        range_high=range_high,
        range_low=range_low,
        range_high_index=range_high_index,
        range_low_index=range_low_index,
    )
    if context is None:
        return None

    volume20 = _average([float(bar.volume) for bar in bars[-21:-1]])
    volume_ratio = float(latest.volume) / volume20 if volume20 else 0.0
    prior_breakout_start = max(BOLLINGER_PERIOD - 1, len(bars) - BOLLINGER_BREAKOUT_LOOKBACK - 1)
    prior_upper_breakouts = [
        bars[index].close > band[0]
        for index, band in enumerate(bands[prior_breakout_start:-1], start=prior_breakout_start)
        if band is not None
    ]
    first_breakout_upper = (
        latest.close > upper
        and latest.close > previous.high
        and previous.close <= previous_upper
        and not any(prior_upper_breakouts)
    )
    volume_confirmed = volume_ratio >= BOLLINGER_BREAKOUT_VOLUME_MULTIPLE
    main_force_volume_confirmed = volume_ratio >= BOLLINGER_MAIN_FORCE_VOLUME_MULTIPLE
    candle_range = latest.high - latest.low
    close_position = (latest.close - latest.low) / candle_range if candle_range > 0 else 0.0
    bullish_body = latest.close > latest.open
    body_percent = percent_change(latest.close, latest.open)
    main_force_buying = (
        main_force_volume_confirmed
        and bullish_body
        and close_position >= 0.7
        and latest.close > previous.close
    )
    if not (first_breakout_upper and main_force_buying):
        return None

    level = SignalLevel.CONFIRMED
    timing_status = "READY"
    timing_note = (
        "布林通道收斂後出現第一根收盤突破上通道的紅K，"
        "且成交量明顯放大、收盤靠近高點，具主力攻擊買盤跡象。"
    )
    trigger_price = max(upper, previous.high)
    score = 92

    return _signal(
        strategy="BOLLINGER_SQUEEZE",
        level=level,
        bars=bars,
        context=context,
        score=score,
        trigger_price=trigger_price,
        timing_status=timing_status,
        timing_note=timing_note,
        reasons=[
            "前一日20日布林通道上軌與下軌靠近，波動進入低檔收斂",
            f"前一日布林寬度 {previous_width_percent:.2f}%，位於近{BOLLINGER_LOOKBACK}日低分位 {previous_width_percentile * 100:.0f}%",
            f"成交張數 {latest.volume / 1000:.0f} 張，大於{MIN_TRADE_VOLUME_LOTS:.0f}張",
            f"第一根收盤突破上通道，量比 {volume_ratio:.2f}倍",
            f"紅K收盤位置 {close_position * 100:.0f}%，具主力攻擊買盤跡象",
        ],
        extra_metrics={
            "latest_volume_lots": latest.volume / 1000,
            "minimum_volume_lots": MIN_TRADE_VOLUME_LOTS,
            "bollinger_period": float(BOLLINGER_PERIOD),
            "bollinger_multiplier": BOLLINGER_MULTIPLIER,
            "bollinger_upper": upper,
            "bollinger_middle": middle,
            "bollinger_lower": lower,
            "bollinger_width_percent": width_percent,
            "bollinger_width_percentile": width_percentile,
            "previous_bollinger_upper": previous_upper,
            "previous_bollinger_width_percent": previous_width_percent,
            "previous_bollinger_width_percentile": previous_width_percentile,
            "bollinger_width_threshold_percentile": BOLLINGER_MAX_WIDTH_PERCENTILE,
            "bollinger_squeeze_confirmed": squeeze_confirmed,
            "bollinger_first_breakout_upper": first_breakout_upper,
            "bollinger_breakout_upper": first_breakout_upper,
            "main_force_buying": main_force_buying,
            "main_force_volume_confirmed": main_force_volume_confirmed,
            "close_position_percent": close_position * 100,
            "bullish_body": bullish_body,
            "body_percent": body_percent,
            "volume20": volume20,
            "volume_ratio": volume_ratio,
            "volume_confirmed": volume_confirmed,
            "main_force_volume_multiple": BOLLINGER_MAIN_FORCE_VOLUME_MULTIPLE,
            "previous_high": previous.high,
        },
    )


def _rsi_series(closes: Sequence[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return result
    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, period + 1):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = _average(gains)
    avg_loss = _average(losses)
    result[period] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    for index in range(period + 1, len(closes)):
        change = closes[index] - closes[index - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        result[index] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    return result


def _cci_series(bars: Sequence[Bar], period: int) -> list[float | None]:
    typical_prices = [(bar.high + bar.low + bar.close) / 3 for bar in bars]
    result: list[float | None] = [None] * len(bars)
    for index in range(period - 1, len(bars)):
        window = typical_prices[index - period + 1 : index + 1]
        mean = _average(window)
        mean_deviation = _average([abs(value - mean) for value in window])
        if mean_deviation > 0:
            result[index] = (typical_prices[index] - mean) / (0.015 * mean_deviation)
    return result


def _adx_series(bars: Sequence[Bar], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(bars)
    if len(bars) < period * 2 + 1:
        return result
    true_ranges: list[float] = [0.0]
    plus_dm: list[float] = [0.0]
    minus_dm: list[float] = [0.0]
    for index in range(1, len(bars)):
        current = bars[index]
        previous = bars[index - 1]
        up_move = current.high - previous.high
        down_move = previous.low - current.low
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)

    smoothed_tr = sum(true_ranges[1 : period + 1])
    smoothed_plus = sum(plus_dm[1 : period + 1])
    smoothed_minus = sum(minus_dm[1 : period + 1])
    dx_values: list[float | None] = [None] * len(bars)
    for index in range(period, len(bars)):
        if index > period:
            smoothed_tr = smoothed_tr - (smoothed_tr / period) + true_ranges[index]
            smoothed_plus = smoothed_plus - (smoothed_plus / period) + plus_dm[index]
            smoothed_minus = smoothed_minus - (smoothed_minus / period) + minus_dm[index]
        plus_di = 100 * smoothed_plus / smoothed_tr if smoothed_tr else 0.0
        minus_di = 100 * smoothed_minus / smoothed_tr if smoothed_tr else 0.0
        denominator = plus_di + minus_di
        dx_values[index] = (
            100 * abs(plus_di - minus_di) / denominator if denominator else 0.0
        )

    first_adx_index = period * 2 - 1
    first_window = [
        value for value in dx_values[period:first_adx_index + 1] if value is not None
    ]
    if len(first_window) != period:
        return result
    adx = _average(first_window)
    result[first_adx_index] = adx
    for index in range(first_adx_index + 1, len(bars)):
        dx = dx_values[index]
        if dx is not None:
            adx = ((adx * (period - 1)) + dx) / period
            result[index] = adx
    return result


def _wavetrend_series(
    bars: Sequence[Bar],
    channel_length: int = 10,
    average_length: int = 11,
) -> list[float | None]:
    hlc3 = [(bar.high + bar.low + bar.close) / 3 for bar in bars]
    esa = _ema(hlc3, channel_length)
    absolute_deviation = [abs(price - avg) for price, avg in zip(hlc3, esa, strict=True)]
    de = _ema(absolute_deviation, channel_length)
    ci = [
        0.0 if deviation == 0 else (price - avg) / (0.015 * deviation)
        for price, avg, deviation in zip(hlc3, esa, de, strict=True)
    ]
    wt1 = _ema(ci, average_length)
    wt2 = sma(wt1, 4)
    result: list[float | None] = [None] * len(bars)
    warmup = channel_length + average_length
    for index, (fast, slow) in enumerate(zip(wt1, wt2, strict=True)):
        if index >= warmup and slow is not None:
            result[index] = fast - slow
    return result


def _bounded(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _normalize_running(
    values: Sequence[float | None],
    out_min: float = 0.0,
    out_max: float = 1.0,
) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    historic_min = 1e11
    historic_max = -1e11
    for index, value in enumerate(values):
        if value is None:
            continue
        historic_min = min(historic_min, value)
        historic_max = max(historic_max, value)
        result[index] = out_min + (out_max - out_min) * (
            value - historic_min
        ) / max(historic_max - historic_min, 1e-9)
    return result


def _cci_from_values(values: Sequence[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        mean = _average(window)
        mean_deviation = _average([abs(value - mean) for value in window])
        if mean_deviation > 0:
            result[index] = (values[index] - mean) / (0.015 * mean_deviation)
    return result


def _ema_optional(values: Sequence[float | None], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if period <= 0:
        return result
    alpha = 2.0 / (period + 1)
    for index, value in enumerate(values):
        if value is None:
            continue
        previous = result[index - 1] if index > 0 else None
        if previous is not None:
            result[index] = alpha * value + (1.0 - alpha) * previous
            continue
        if index >= period - 1:
            window = values[index - period + 1 : index + 1]
            if all(item is not None for item in window):
                result[index] = _average([float(item) for item in window])
    return result


def _rma_optional(values: Sequence[float | None], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if period <= 0:
        return result
    alpha = 1.0 / period
    for index, value in enumerate(values):
        if value is None:
            continue
        previous = result[index - 1] if index > 0 else None
        if previous is not None:
            result[index] = alpha * value + (1.0 - alpha) * previous
            continue
        if index >= period - 1:
            window = values[index - period + 1 : index + 1]
            if all(item is not None for item in window):
                result[index] = _average([float(item) for item in window])
    return result


def _true_range_series(bars: Sequence[Bar]) -> list[float]:
    result: list[float] = []
    for index, bar in enumerate(bars):
        previous_close = bars[index - 1].close if index > 0 else 0.0
        result.append(
            max(
                bar.high - bar.low,
                abs(bar.high - previous_close),
                abs(bar.low - previous_close),
            )
        )
    return result


def _atr_series(bars: Sequence[Bar], period: int) -> list[float | None]:
    return _rma_optional(_true_range_series(bars), period)


def _regime_filter_series(
    bars: Sequence[Bar],
) -> tuple[list[float], list[float]]:
    size = len(bars)
    abs_slope = [0.0] * size
    ema_abs = [0.0] * size
    if not bars:
        return abs_slope, ema_abs
    ohlc4 = [
        (bar.open + bar.high + bar.low + bar.close) / 4.0
        for bar in bars
    ]
    value1 = [0.0] * size
    value2 = [0.0] * size
    klmf = [0.0] * size
    value2[0] = bars[0].high - bars[0].low
    klmf[0] = ohlc4[0]
    alpha_ema = 2.0 / 201.0
    for index in range(1, size):
        value1[index] = (
            0.2 * (ohlc4[index] - ohlc4[index - 1])
            + 0.8 * value1[index - 1]
        )
        value2[index] = (
            0.1 * (bars[index].high - bars[index].low)
            + 0.8 * value2[index - 1]
        )
        omega = abs(value1[index] / value2[index]) if value2[index] else 0.0
        alpha = (-(omega**2) + math.sqrt(omega**4 + 16.0 * omega**2)) / 8.0
        klmf[index] = alpha * ohlc4[index] + (1.0 - alpha) * klmf[index - 1]
        abs_slope[index] = abs(klmf[index] - klmf[index - 1])
        previous_ema = ema_abs[index - 1]
        if previous_ema == 0 and index < 200:
            ema_abs[index] = abs_slope[index]
        else:
            ema_abs[index] = alpha_ema * abs_slope[index] + (
                1.0 - alpha_ema
            ) * previous_ema
    return abs_slope, ema_abs


def _hlc3(bar: Bar) -> float:
    return (bar.high + bar.low + bar.close) / 3


def _source_values(bars: Sequence[Bar], source: str = LORENTZIAN_SOURCE) -> list[float]:
    if source == "hlc3":
        return [_hlc3(bar) for bar in bars]
    return [bar.close for bar in bars]


def _lorentzian_features(
    bars: Sequence[Bar],
) -> list[tuple[float, float, float, float, float] | None]:
    closes = [bar.close for bar in bars]
    rsi14 = _ema_optional(_rsi_series(closes, 14), 1)
    wt = _normalize_running(_wavetrend_series(bars))
    cci20 = _normalize_running(_ema_optional(_cci_from_values(closes, 20), 1))
    adx20 = _adx_series(bars, 20)
    rsi9 = _ema_optional(_rsi_series(closes, 9), 1)
    features: list[tuple[float, float, float, float, float] | None] = []
    for values in zip(rsi14, wt, cci20, adx20, rsi9, strict=True):
        rsi_value, wt_value, cci_value, adx_value, rsi_fast = values
        if None in values:
            features.append(None)
            continue
        features.append(
            (
                _bounded(float(rsi_value) / 100.0, 0.0, 1.0),
                _bounded(float(wt_value), 0.0, 1.0),
                _bounded(float(cci_value), 0.0, 1.0),
                _bounded(float(adx_value) / 100.0, 0.0, 1.0),
                _bounded(float(rsi_fast) / 100.0, 0.0, 1.0),
            )
        )
    return features


def _lorentzian_predictions(
    features: Sequence[tuple[float, float, float, float, float] | None],
    source_values: Sequence[float],
) -> list[tuple[int, int, float] | None]:
    """Forward-indexed ANN port matching the AI Edge parity-tested implementation."""

    labels: list[int] = []
    distances: list[float] = []
    predictions: list[int] = []
    results: list[tuple[int, int, float] | None] = []
    last_bar_index = len(features) - 1
    max_bars_back_index = (
        last_bar_index - LORENTZIAN_LOOKBACK_BARS
        if last_bar_index >= LORENTZIAN_LOOKBACK_BARS
        else 0
    )
    for index, current in enumerate(features):
        train_label = 0
        if index >= 4:
            train_label = (
                -1
                if source_values[index - 4] < source_values[index]
                else 1
                if source_values[index - 4] > source_values[index]
                else 0
            )
        labels.append(train_label)
        if current is None or index < max_bars_back_index:
            results.append(None)
            continue

        size_loop = min(LORENTZIAN_LOOKBACK_BARS - 1, len(labels) - 1)
        start_index = max_bars_back_index
        last_distance = -1.0
        for candidate_index in range(start_index, size_loop + 1):
            historical = features[candidate_index]
            if historical is None or candidate_index % 4 == 0:
                continue
            distance = sum(
                math.log1p(abs(current_value - historical_value))
                for current_value, historical_value in zip(
                    current, historical, strict=True
                )
            )
            if distance >= last_distance:
                last_distance = distance
                distances.append(distance)
                predictions.append(round(labels[candidate_index]))
                if len(predictions) > LORENTZIAN_NEIGHBORS:
                    threshold_index = round(LORENTZIAN_NEIGHBORS * 3.0 / 4.0)
                    last_distance = distances[threshold_index]
                    distances.pop(0)
                    predictions.pop(0)
        prediction = int(sum(predictions))
        confidence = abs(prediction) / LORENTZIAN_NEIGHBORS
        results.append((prediction, len(predictions), confidence))
    return results


def _rational_quadratic_estimate(
    values: Sequence[float],
    index: int,
    lookback: int = 8,
    relative_weighting: float = 8.0,
    start_at_bar: int = LORENTZIAN_KERNEL_START,
) -> float | None:
    if index < 0 or index >= len(values):
        return None
    weighted_sum = 0.0
    weight_total = 0.0
    denominator = max(float(lookback**2) * 2.0 * relative_weighting, 1e-10)
    for distance in range(min(1 + start_at_bar, index) + 1):
        weight = (
            1.0
            + ((distance * distance) / denominator)
        ) ** (-relative_weighting)
        sample_index = index - distance
        weighted_sum += values[sample_index] * weight
        weight_total += weight
    return weighted_sum / weight_total if weight_total else None


def lorentzian_ml_signal(
    bars: Sequence[Bar],
    relative_strength_percentile: float = 0.5,
) -> StrategySignal | None:
    """Daily stock-scanner adaptation of jdehorty's MPL-2.0 Lorentzian classifier.

    Original concept: "Machine Learning: Lorentzian Classification v2.0"
    by jdehorty, licensed under Mozilla Public License 2.0.
    """
    if len(bars) < LORENTZIAN_MIN_BARS:
        return None
    latest = bars[-1]
    previous = bars[-2]
    if latest.volume < MIN_TRADE_VOLUME_SHARES:
        return None

    closes = [bar.close for bar in bars]
    source_values = _source_values(bars)
    features = _lorentzian_features(bars)
    predictions = _lorentzian_predictions(features, source_values)
    current = predictions[-1]
    previous_prediction = predictions[-2] if len(predictions) >= 2 else None
    if current is None:
        return None
    prediction, neighbors, confidence = current
    prior_prediction = previous_prediction[0] if previous_prediction is not None else 0
    if prediction <= 0:
        return None

    kernel_now = _rational_quadratic_estimate(
        source_values,
        len(bars) - 1,
        lookback=LORENTZIAN_KERNEL_LOOKBACK,
        relative_weighting=LORENTZIAN_KERNEL_RELATIVE_WEIGHTING,
    )
    kernel_previous = _rational_quadratic_estimate(
        source_values,
        len(bars) - 2,
        lookback=LORENTZIAN_KERNEL_LOOKBACK,
        relative_weighting=LORENTZIAN_KERNEL_RELATIVE_WEIGHTING,
    )
    if kernel_now is None or kernel_previous is None or kernel_previous <= 0:
        return None
    kernel_slope_percent = percent_change(kernel_now, kernel_previous) * 100
    kernel_bullish = kernel_now >= kernel_previous
    ma20_value = float(sma(closes, 20)[-1] or 0)
    ma50_value = float(sma(closes, 50)[-1] or 0)
    adx_value = (_adx_series(bars, 20)[-1] or 0.0)
    rsi_value = (_rsi_series(closes, 14)[-1] or 0.0)
    atr1 = _atr_series(bars, 1)[-1]
    atr10 = _atr_series(bars, 10)[-1]
    atr_percent = ((atr1 or 0.0) / latest.close) * 100 if latest.close > 0 else 0.0
    volatility_filter_ok = (
        True if atr1 is None or atr10 is None else atr1 > atr10
    )
    regime_abs_slope, regime_ema_abs_slope = _regime_filter_series(bars)
    regime_denominator = regime_ema_abs_slope[-1]
    regime_score = (
        (regime_abs_slope[-1] - regime_denominator) / regime_denominator
        if regime_denominator
        else 0.0
    )
    regime_filter_ok = regime_score >= LORENTZIAN_REGIME_THRESHOLD
    adx_filter_enabled = False
    adx_filter_ok = (
        True
        if not adx_filter_enabled
        else adx_value >= LORENTZIAN_ADX_THRESHOLD
    )
    relative_strength_ok = relative_strength_percentile >= 0.45
    trend_filter_ok = (
        volatility_filter_ok
        and regime_filter_ok
        and adx_filter_ok
        and kernel_bullish
        and latest.close > ma20_value
    )
    if not trend_filter_ok or not relative_strength_ok:
        return None

    recent_lows = [bar.low for bar in bars[-20:]]
    recent_highs = [bar.high for bar in bars[-20:]]
    range_low = min(recent_lows)
    range_high = max(recent_highs)
    range_low_index = len(bars) - 20 + min(
        range(len(recent_lows)), key=lambda index: recent_lows[index]
    )
    range_high_index = len(bars) - 20 + max(
        range(len(recent_highs)), key=lambda index: recent_highs[index]
    )
    context = _range_context(
        bars,
        range_high=range_high,
        range_low=range_low,
        range_high_index=range_high_index,
        range_low_index=range_low_index,
    )
    if context is None:
        return None

    broke_previous_high = latest.close > previous.high
    new_positive_turn = prior_prediction <= 0 and prediction > 0
    confirmed_buy = broke_previous_high and kernel_bullish and confidence >= 0.5
    if confirmed_buy:
        level = SignalLevel.CONFIRMED
        timing_status = "READY"
        timing_note = (
            "Lorentzian依TradingView預設參數投票轉多，Kernel估計線向上，且收盤突破前一日高點；"
            "此為機器學習輔助確認訊號，仍需搭配停損。"
        )
        trigger_price = previous.high
        score = int(min(96, 78 + confidence * 18 + max(0.0, kernel_slope_percent) * 2))
    elif new_positive_turn:
        level = SignalLevel.TRIAL
        timing_status = "TRIAL_ENTRY"
        timing_note = (
            "Lorentzian依TradingView預設參數投票剛轉多，Kernel方向向上，但尚未收盤突破前一日高點。"
        )
        trigger_price = previous.high
        score = int(min(88, 70 + confidence * 16))
    else:
        level = SignalLevel.WATCH
        timing_status = "WAIT_CONFIRMATION"
        timing_note = (
            "Lorentzian依TradingView預設參數投票偏多，等待突破前一日高點或更明確的量價確認。"
        )
        trigger_price = previous.high
        score = int(min(82, 64 + confidence * 14))

    risk_percent, risk_valid = _risk(latest.close, context.latest_trough)
    if risk_percent > LORENTZIAN_MAX_RISK_PERCENT:
        return None

    return _signal(
        strategy="LORENTZIAN_ML",
        level=level,
        bars=bars,
        context=context,
        score=score,
        trigger_price=trigger_price,
        timing_status=timing_status,
        timing_note=timing_note,
        reasons=[
            "AI Edge預設：close / 8近鄰 / 5特徵 / Kernel 8",
            f"Lorentzian近鄰投票 {prediction:+d}/{neighbors}",
            f"信心 {confidence * 100:.0f}%，Kernel斜率 {kernel_slope_percent:.2f}%",
            f"Volatility/Regime濾網通過，ATR1 {atr_percent:.2f}%",
            f"成交張數 {latest.volume / 1000:.0f} 張，大於{MIN_TRADE_VOLUME_LOTS:.0f}張",
            f"相對強度分位 {relative_strength_percentile * 100:.0f}%",
            (
                "收盤突破前一日高點，ML輔助買點確認"
                if confirmed_buy
                else "尚未突破前一日高點，先列觀察或轉強"
            ),
        ],
        extra_metrics={
            "latest_volume_lots": latest.volume / 1000,
            "minimum_volume_lots": MIN_TRADE_VOLUME_LOTS,
            "tv_source_close": True,
            "tv_neighbors_default": float(LORENTZIAN_NEIGHBORS),
            "tv_max_bars_back_default": float(LORENTZIAN_LOOKBACK_BARS),
            "tv_feature_count_default": float(LORENTZIAN_FEATURE_COUNT),
            "tv_kernel_lookback_default": float(LORENTZIAN_KERNEL_LOOKBACK),
            "available_training_bars": float(
                min(len(bars), LORENTZIAN_LOOKBACK_BARS)
            ),
            "ml_prediction": float(prediction),
            "ml_prior_prediction": float(prior_prediction),
            "ml_neighbors": float(neighbors),
            "ml_confidence": confidence,
            "kernel_estimate": kernel_now,
            "kernel_slope_percent": kernel_slope_percent,
            "kernel_bullish": kernel_bullish,
            "volatility_filter_enabled": True,
            "atr1_percent": atr_percent,
            "atr1": float(atr1 or 0.0),
            "atr10": float(atr10 or 0.0),
            "volatility_filter_ok": volatility_filter_ok,
            "regime_filter_enabled": True,
            "regime_score": regime_score,
            "regime_threshold": LORENTZIAN_REGIME_THRESHOLD,
            "regime_filter_ok": regime_filter_ok,
            "adx_filter_enabled": adx_filter_enabled,
            "adx_threshold": float(LORENTZIAN_ADX_THRESHOLD),
            "adx_filter_ok": adx_filter_ok,
            "broke_previous_high": broke_previous_high,
            "relative_strength_percentile": relative_strength_percentile,
            "rsi14": float(rsi_value),
            "adx20": float(adx_value),
            "ma20": ma20_value,
            "ma50": ma50_value,
            "structure_risk_percent": risk_percent,
            "structure_risk_valid": risk_valid,
            "source_license_mpl_2_0": True,
        },
    )


def intraday_ma60_touch_signal(
    daily_bars: Sequence[Bar],
    intraday_bars: Sequence[IntradayBar],
) -> StrategySignal | None:
    if len(daily_bars) < MIN_BARS or len(intraday_bars) < INTRADAY_MA_PERIOD:
        return None
    latest_daily = daily_bars[-1]
    if latest_daily.volume < MIN_TRADE_VOLUME_SHARES:
        return None

    closes = [bar.close for bar in intraday_bars]
    ma60s = sma(closes, INTRADAY_MA_PERIOD)
    latest_ma60 = float(ma60s[-1] or 0.0)
    previous_ma60 = float(ma60s[-6] or latest_ma60) if len(ma60s) >= 6 else latest_ma60
    if latest_ma60 <= 0:
        return None

    latest = intraday_bars[-1]
    previous = intraday_bars[-2]
    distance_percent = ((latest.close - latest_ma60) / latest_ma60) * 100
    abs_distance_percent = abs(distance_percent)
    if abs_distance_percent > INTRADAY_MA_MAX_DISTANCE_PERCENT:
        return None

    ma60_slope_percent = percent_change(latest_ma60, previous_ma60)
    intraday_ma60_turning_up = ma60_slope_percent > INTRADAY_MA_MIN_SLOPE_PERCENT
    if not intraday_ma60_turning_up:
        return None

    recent_volumes = [float(bar.volume) for bar in intraday_bars[-21:-1] if bar.volume > 0]
    intraday_avg_volume = _average(recent_volumes)
    intraday_volume_ratio = (
        latest.volume / intraday_avg_volume
        if latest.volume > 0 and intraday_avg_volume > 0
        else 0.0
    )
    has_intraday_volume_data = intraday_volume_ratio > 0
    intraday_volume_breakout = (
        intraday_volume_ratio >= INTRADAY_MA_VOLUME_MULTIPLE
        if has_intraday_volume_data
        else True
    )
    recent_window = intraday_bars[-INTRADAY_MA_PERIOD:]
    recent_low = min(bar.low for bar in recent_window)
    recent_high = max(bar.high for bar in recent_window)
    range_high_index = len(daily_bars) - 1
    range_low_index = len(daily_bars) - 1
    context = _range_context(
        daily_bars,
        range_high=max(recent_high, latest_daily.high),
        range_low=min(recent_low, latest_daily.low),
        range_high_index=range_high_index,
        range_low_index=range_low_index,
    )
    if context is None:
        return None

    reclaimed_ma60 = previous.close < latest_ma60 <= latest.close
    above_ma60 = latest.close >= latest_ma60
    pulled_back_without_breaking = (
        previous.close >= latest_ma60
        and latest.low <= latest_ma60 * 1.005
        and latest.close >= latest_ma60
    )
    price_confirmed = reclaimed_ma60 or pulled_back_without_breaking
    ready = (
        (above_ma60 or price_confirmed)
        and abs_distance_percent <= INTRADAY_MA_READY_DISTANCE_PERCENT
        and latest.close >= previous.close
        and intraday_volume_breakout
    )
    if ready:
        level = SignalLevel.CONFIRMED
        timing_status = "READY"
        timing_note = (
            "60分K貼近並站上60MA，且60MA向上；"
            "屬於短線回測均線後的確認觀察點。"
        )
        score = 88
    elif above_ma60 or reclaimed_ma60 or pulled_back_without_breaking:
        level = SignalLevel.TRIAL
        timing_status = "TRIAL_ENTRY"
        timing_note = (
            "60分K已靠近或剛站上60MA，且60MA向上；"
            "但距離、量能或短線K棒尚未完全確認。"
        )
        score = 78
    else:
        level = SignalLevel.WATCH
        timing_status = "WAIT_CONFIRMATION"
        timing_note = (
            "60分K接近60MA下方，且60MA向上；等待站回60MA並出現轉強K棒。"
        )
        score = 68

    risk_percent, risk_valid = _risk(latest.close, min(recent_low, latest_ma60 * 0.98))
    stop_price = min(recent_low, latest_ma60 * 0.98)
    signal = _signal(
        strategy="INTRADAY_MA60_TOUCH",
        level=level,
        bars=daily_bars,
        context=context,
        score=score,
        trigger_price=latest_ma60,
        timing_status=timing_status,
        timing_note=timing_note,
        reasons=[
            f"60分K收盤 {latest.close:.2f}，距60MA {distance_percent:+.2f}%",
            f"60分60MA {latest_ma60:.2f}，近5根斜率 {ma60_slope_percent:+.2f}%",
            (
                f"60分量比 {intraday_volume_ratio:.2f}倍"
                if has_intraday_volume_data
                else "60分量資料不足，退回日成交張數檢查"
            ),
            f"日成交張數 {latest_daily.volume / 1000:.0f} 張，大於{MIN_TRADE_VOLUME_LOTS:.0f}張",
            (
                "放量突破60MA"
                if reclaimed_ma60 and intraday_volume_breakout
                else "回踩60MA不破"
                if pulled_back_without_breaking
                else "接近60MA，等待突破確認"
            ),
        ],
        extra_metrics={
            "timeframe": "60m",
            "strategy_rule": "6060",
            "intraday_ma_period": float(INTRADAY_MA_PERIOD),
            "intraday_close": latest.close,
            "intraday_previous_close": previous.close,
            "intraday_ma60": latest_ma60,
            "intraday_ma60_slope_percent": ma60_slope_percent,
            "intraday_ma60_turning_up": intraday_ma60_turning_up,
            "intraday_distance_to_ma60_percent": distance_percent,
            "intraday_abs_distance_to_ma60_percent": abs_distance_percent,
            "intraday_max_distance_percent": INTRADAY_MA_MAX_DISTANCE_PERCENT,
            "intraday_bar_time": latest.timestamp.isoformat(),
            "intraday_volume_lots": latest.volume / 1000,
            "intraday_avg_volume_lots": intraday_avg_volume / 1000,
            "intraday_volume_ratio": intraday_volume_ratio,
            "intraday_volume_breakout": intraday_volume_breakout,
            "intraday_volume_data_available": has_intraday_volume_data,
            "daily_volume_lots": latest_daily.volume / 1000,
            "reclaimed_intraday_ma60": reclaimed_ma60,
            "above_intraday_ma60": above_ma60,
            "pulled_back_without_breaking_intraday_ma60": pulled_back_without_breaking,
            "structure_risk_percent": risk_percent,
            "structure_risk_valid": risk_valid,
        },
    )
    return StrategySignal(
        **{
            **signal.__dict__,
            "signal_date": latest.timestamp.date(),
            "close": latest.close,
            "entry_price": latest.close if ready else None,
            "entry_zone_low": min(latest.close, latest_ma60) if ready else None,
            "entry_zone_high": max(latest.close, latest_ma60) if ready else None,
            "trigger_price": round(latest_ma60, 2),
            "stop_price": round(stop_price, 2),
            "risk_percent": risk_percent if ready else None,
            "executable": ready and risk_valid,
        }
    )


def low_price_high_yield_signal(
    bars: Sequence[Bar],
    valuation: ValuationMetrics,
) -> StrategySignal | None:
    if len(bars) < HIGH_YIELD_LOOKBACK:
        return None
    latest = bars[-1]
    if latest.volume < MIN_TRADE_VOLUME_SHARES:
        return None
    if valuation.dividend_yield < HIGH_YIELD_MIN_DIVIDEND_YIELD:
        return None
    if (
        valuation.pb_ratio is not None
        and valuation.pb_ratio > HIGH_YIELD_MAX_PB_RATIO
    ):
        return None

    window = bars[-HIGH_YIELD_LOOKBACK:]
    range_high = max(bar.high for bar in window)
    range_low = min(bar.low for bar in window)
    if range_high <= 0 or range_low <= 0:
        return None

    drawdown_percent = ((range_high - latest.close) / range_high) * 100
    distance_from_low_percent = ((latest.close - range_low) / range_low) * 100
    if drawdown_percent < HIGH_YIELD_MIN_DRAWDOWN_PERCENT:
        return None
    if distance_from_low_percent > HIGH_YIELD_MAX_DISTANCE_FROM_LOW_PERCENT:
        return None

    closes = [bar.close for bar in bars]
    ma20s = sma(closes, 20)
    ma60s = sma(closes, 60)
    ma20 = float(ma20s[-1] or 0.0)
    ma60 = float(ma60s[-1] or 0.0)
    ma20_5 = float(ma20s[-6] or ma20) if len(ma20s) >= 6 else ma20
    if min(ma20, ma60) <= 0:
        return None

    recent_low = min(bar.low for bar in bars[-20:])
    previous = bars[-2]
    stable_above_recent_low = latest.low >= recent_low * 1.01
    reclaim_ma20 = latest.close > ma20 and previous.close <= float(ma20s[-2] or ma20)
    above_ma20 = latest.close > ma20
    ma20_flattening = ma20 >= ma20_5 * 0.995
    pe_reasonable = valuation.pe_ratio is None or valuation.pe_ratio <= 20
    pb_reasonable = valuation.pb_ratio is None or valuation.pb_ratio <= 1.2

    if reclaim_ma20 and ma20_flattening:
        level = SignalLevel.CONFIRMED
        timing_status = "READY"
        timing_note = "低檔高殖利率且收盤轉強站回20日線；可小部位觀察，不追高。"
        score = 74
        trigger_price = max(latest.high, ma20)
        entry_price = latest.close
    elif above_ma20 or stable_above_recent_low:
        level = SignalLevel.TRIAL
        timing_status = "TRIAL_ENTRY"
        timing_note = "低檔高殖利率已止穩；等待站回20日線或紅K續強確認。"
        score = 66
        trigger_price = max(ma20, previous.high)
        entry_price = None
    else:
        level = SignalLevel.WATCH
        timing_status = "WAIT_CONFIRMATION"
        timing_note = "低檔與殖利率條件成立；尚未出現明確轉強K線。"
        score = 58
        trigger_price = max(ma20, previous.high)
        entry_price = None

    stop_price = round(recent_low * 0.99, 2)
    risk_percent, risk_valid = (
        _risk(entry_price, stop_price) if entry_price is not None else (0.0, False)
    )
    dividend_per_share = (
        latest.close * valuation.dividend_yield / 100
        if valuation.dividend_per_share is None
        else valuation.dividend_per_share
    )
    reasons = [
        f"殖利率 {valuation.dividend_yield:.2f}% ≥ {HIGH_YIELD_MIN_DIVIDEND_YIELD:.0f}%",
        f"近{HIGH_YIELD_LOOKBACK}日高點回落 {drawdown_percent:.1f}%",
        f"距近{HIGH_YIELD_LOOKBACK}日低點 {distance_from_low_percent:.1f}%",
        f"P/B {valuation.pb_ratio:.2f}" if valuation.pb_ratio is not None else "P/B 無資料",
        f"成交 {latest.volume / 1000:.0f}張",
    ]
    if pe_reasonable:
        reasons.append(
            f"本益比 {valuation.pe_ratio:.2f}"
            if valuation.pe_ratio is not None
            else "本益比無資料"
        )
    if pb_reasonable:
        reasons.append("淨值比相對低")

    return StrategySignal(
        strategy="LOW_PRICE_HIGH_YIELD",
        level=level,
        signal_date=latest.date,
        score=score,
        close=latest.close,
        entry_price=round(entry_price, 2) if entry_price is not None else None,
        entry_zone_low=(
            round(min(latest.close, trigger_price), 2)
            if level == SignalLevel.CONFIRMED
            else None
        ),
        entry_zone_high=(
            round(max(latest.close, trigger_price), 2)
            if level == SignalLevel.CONFIRMED
            else None
        ),
        trigger_price=round(trigger_price, 2),
        stop_price=stop_price,
        risk_percent=risk_percent if level == SignalLevel.CONFIRMED else None,
        timing_status=timing_status,
        timing_note=timing_note,
        overheated=False,
        executable=level == SignalLevel.CONFIRMED and risk_valid,
        reasons=reasons,
        metrics={
            "latest_volume_lots": latest.volume / 1000,
            "minimum_volume_lots": MIN_TRADE_VOLUME_LOTS,
            "liquidity_ok": latest.volume >= MIN_TRADE_VOLUME_SHARES,
            "dividend_yield": valuation.dividend_yield,
            "dividend_per_share": dividend_per_share,
            "pe_ratio": valuation.pe_ratio or 0.0,
            "pb_ratio": valuation.pb_ratio or 0.0,
            "valuation_date": valuation.trade_date.isoformat(),
            "low_price_lookback": float(HIGH_YIELD_LOOKBACK),
            "range_high": range_high,
            "range_low": range_low,
            "drawdown_from_high_percent": drawdown_percent,
            "distance_from_low_percent": distance_from_low_percent,
            "ma20": ma20,
            "ma60": ma60,
            "ma20_slope_5d": percent_change(ma20, ma20_5),
            "stable_above_recent_low": stable_above_recent_low,
            "reclaim_ma20": reclaim_ma20,
            "above_ma20": above_ma20,
            "pe_reasonable": pe_reasonable,
            "pb_reasonable": pb_reasonable,
            "structure_risk_percent": risk_percent,
            "structure_risk_valid": risk_valid,
        },
    )


def scan_bars(
    bars: Sequence[Bar], relative_strength_percentile: float = 0.5
) -> list[StrategySignal]:
    signals = [
        trend_confirmation_signal(bars),
        pullback_resume_signal(bars),
        consolidation_signal(bars),
        disposition_reversal_signal(bars),
        bottom_reversal_signal(bars),
        bollinger_squeeze_signal(bars),
        lorentzian_ml_signal(bars, relative_strength_percentile),
    ]
    return [signal for signal in signals if signal is not None]
