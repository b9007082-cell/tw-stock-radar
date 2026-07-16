from collections.abc import Sequence
from dataclasses import dataclass

from app.domain import Bar, SignalLevel, StrategySignal
from app.services.indicators import confirmed_swings, percent_change, sma


MIN_BARS = 65
BREAKOUT_VOLUME_MULTIPLE = 1.2
MAX_VOLUME_CONTRACTION_RATIO = 1.0
MIN_TRADE_VOLUME_SHARES = 1_500_000
MIN_TRADE_VOLUME_LOTS = MIN_TRADE_VOLUME_SHARES / 1000
MA_CONSOLIDATION_DAYS = 40
MAX_MA_CONVERGENCE_PERCENT = 5.0
MAX_TWO_MONTH_RANGE_PERCENT = 18.0
MAX_QUIET_VOLUME_RATIO = 0.8


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
            "多頭方向已確認；等待回後買上漲或盤整突破，"
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
    if not pullback_volume_contracting:
        return None

    confirmation_metrics = _buy_confirmation_metrics(bars, context)
    if not bool(confirmation_metrics["liquidity_ok"]):
        return None

    back_above_ma5 = latest.close > context.ma5
    broke_previous_high = latest.close > previous.high
    if back_above_ma5 and broke_previous_high:
        if not rebound_volume_expanding:
            return None
        if not bool(confirmation_metrics["photo_conditions_confirmed"]):
            return None
        level = SignalLevel.CONFIRMED
        timing_status = "READY"
        timing_note = (
            "回檔守住20日線後，收盤站回5日線並突破前一日高點，"
            "且轉強量大於回檔均量，回後買上漲買點成立。"
        )
        score = 92
    elif back_above_ma5:
        if not rebound_volume_expanding:
            return None
        level = SignalLevel.TRIAL
        timing_status = "TRIAL_ENTRY"
        timing_note = (
            "已站回5日線且轉強量大於回檔均量，"
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
            **confirmation_metrics,
        },
    )


def consolidation_signal(
    bars: Sequence[Bar],
) -> StrategySignal | None:
    context = _trend_context(bars)
    if (
        context is None
        or not context.confirmed
        or context.latest_trough_index <= context.latest_peak_index
    ):
        return None
    latest = bars[-1]
    previous = bars[-2]
    confirmation_metrics = _buy_confirmation_metrics(bars, context)
    if not bool(confirmation_metrics["liquidity_ok"]):
        return None
    trigger = context.latest_peak
    prior_consolidation_volumes = [float(bar.volume) for bar in bars[-21:-1]]
    previous_volumes = [float(bar.volume) for bar in bars[-41:-21]]
    consolidation_volume_avg = _average(prior_consolidation_volumes)
    previous_volume_avg = _average(previous_volumes)
    consolidation_volume_ratio = (
        consolidation_volume_avg / previous_volume_avg
        if previous_volume_avg
        else 0.0
    )
    volume_contracting = (
        len(prior_consolidation_volumes) == 20
        and len(previous_volumes) == 20
        and 0 < consolidation_volume_ratio < MAX_VOLUME_CONTRACTION_RATIO
    )
    breakout_volume_ratio = (
        float(latest.volume) / consolidation_volume_avg
        if consolidation_volume_avg
        else 0.0
    )
    volume_confirmed = (
        volume_contracting and breakout_volume_ratio > BREAKOUT_VOLUME_MULTIPLE
    )
    if not volume_contracting:
        return None
    if latest.close > trigger and volume_confirmed:
        if not bool(confirmation_metrics["photo_conditions_confirmed"]):
            return None
        level = SignalLevel.CONFIRMED
        timing_status = "READY"
        timing_note = (
            "整理期間量縮後，收盤突破最近確認壓力，"
            "且成交量高於整理均量1.2倍，"
            "盤整突破買點成立。"
        )
        score = 94
    elif latest.high > trigger and latest.close <= trigger:
        level = SignalLevel.TRIAL
        timing_status = "TRIAL_ENTRY"
        timing_note = "盤中突破但收盤未站穩最近壓力，只視為測試壓力。"
        score = 82
    elif context.ma20 < latest.close <= trigger:
        level = SignalLevel.WATCH
        timing_status = "WAIT_CONFIRMATION"
        timing_note = "多頭整理守在20日線之上，等待收盤突破最近確認壓力。"
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
            "多頭確認：頭頭高、底底高",
            (
                f"成交張數 {confirmation_metrics['latest_volume_lots']:.0f} 張，"
                f"大於{MIN_TRADE_VOLUME_LOTS:.0f}張"
            ),
            "最近確認波谷晚於最近確認波峰，整理結構完整",
            "紅K收盤突破上頸線與前一日高點",
            f"整理均量為前段均量的 {consolidation_volume_ratio:.2f} 倍",
            (
                "收盤突破最近確認壓力且成交量高於整理均量1.2倍"
                if level == SignalLevel.CONFIRMED
                else "等待收盤站穩最近確認壓力"
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
            "consolidation_volume_avg": consolidation_volume_avg,
            "previous_volume_avg": previous_volume_avg,
            "consolidation_volume_ratio": consolidation_volume_ratio,
            "volume_contracting": volume_contracting,
            "breakout_volume_ratio": breakout_volume_ratio,
            **confirmation_metrics,
        },
    )


def ma_consolidation_signal(
    bars: Sequence[Bar],
) -> StrategySignal | None:
    if len(bars) < MIN_BARS:
        return None
    latest = bars[-1]
    closes = [bar.close for bar in bars]
    volumes = [float(bar.volume) for bar in bars]
    ma5 = float(sma(closes, 5)[-1] or 0)
    ma10 = float(sma(closes, 10)[-1] or 0)
    ma20 = float(sma(closes, 20)[-1] or 0)
    ma60 = float(sma(closes, 60)[-1] or 0)
    if min(ma5, ma10, ma20, ma60, latest.close) <= 0:
        return None

    consolidation_window = bars[-MA_CONSOLIDATION_DAYS:]
    if len(consolidation_window) < MA_CONSOLIDATION_DAYS:
        return None
    range_high = max(bar.high for bar in consolidation_window)
    range_low = min(bar.low for bar in consolidation_window)
    range_high_index = len(bars) - MA_CONSOLIDATION_DAYS + max(
        range(len(consolidation_window)),
        key=lambda index: consolidation_window[index].high,
    )
    range_low_index = len(bars) - MA_CONSOLIDATION_DAYS + min(
        range(len(consolidation_window)),
        key=lambda index: consolidation_window[index].low,
    )
    range_percent = ((range_high - range_low) / latest.close) * 100
    ma_values = [ma5, ma10, ma20, ma60]
    ma_spread_percent = ((max(ma_values) - min(ma_values)) / latest.close) * 100

    recent_volume_avg = _average(volumes[-20:])
    previous_volume_avg = _average(volumes[-60:-20])
    quiet_volume_ratio = (
        recent_volume_avg / previous_volume_avg if previous_volume_avg else 0.0
    )
    latest_volume_lots = latest.volume / 1000
    recent_volume_lots = recent_volume_avg / 1000
    breakout_distance_percent = (
        ((range_high - latest.close) / latest.close) * 100
        if latest.close > 0
        else 0.0
    )

    ma_converged = ma_spread_percent <= MAX_MA_CONVERGENCE_PERCENT
    two_month_consolidation = range_percent <= MAX_TWO_MONTH_RANGE_PERCENT
    quiet_volume = (
        0 < quiet_volume_ratio <= MAX_QUIET_VOLUME_RATIO
        and latest.volume <= recent_volume_avg * 1.2
    )
    if not (ma_converged and two_month_consolidation and quiet_volume):
        return None

    context = _range_context(
        bars,
        range_high=range_high,
        range_low=range_low,
        range_high_index=range_high_index,
        range_low_index=range_low_index,
    )
    if context is None:
        return None

    tightness_bonus = max(0.0, MAX_MA_CONVERGENCE_PERCENT - ma_spread_percent) * 3
    range_bonus = max(0.0, MAX_TWO_MONTH_RANGE_PERCENT - range_percent) * 0.8
    volume_bonus = max(0.0, MAX_QUIET_VOLUME_RATIO - quiet_volume_ratio) * 18
    proximity_bonus = max(0.0, 6.0 - max(0.0, breakout_distance_percent)) * 1.2
    score = round(
        min(92.0, 72.0 + tightness_bonus + range_bonus + volume_bonus + proximity_bonus)
    )

    return _signal(
        strategy="MA_CONSOLIDATION",
        level=SignalLevel.WATCH,
        bars=bars,
        context=context,
        score=score,
        trigger_price=range_high,
        timing_status="WAIT_CONFIRMATION",
        timing_note=(
            "均線糾結且兩個月以上低量盤整，先列入提前觀察；"
            "等待放量紅K收盤突破箱頂後，才視為可能起漲確認。"
        ),
        reasons=[
            f"近{MA_CONSOLIDATION_DAYS}個交易日盤整，箱型震幅 {range_percent:.1f}%",
            f"5/10/20/60日均線糾結，最大乖離 {ma_spread_percent:.1f}%",
            f"近20日均量為前40日均量的 {quiet_volume_ratio:.2f} 倍",
            f"成交張數 {latest_volume_lots:.0f} 張，近20日均量 {recent_volume_lots:.0f} 張",
            "目前屬低量潛伏觀察，不是直接買點；等放量紅K突破箱頂再確認",
        ],
        extra_metrics={
            "ma60": ma60,
            "ma_spread_percent": ma_spread_percent,
            "consolidation_days": float(MA_CONSOLIDATION_DAYS),
            "range_high": range_high,
            "range_low": range_low,
            "range_percent": range_percent,
            "quiet_volume_ratio": quiet_volume_ratio,
            "recent_volume_avg": recent_volume_avg,
            "previous_volume_avg": previous_volume_avg,
            "latest_volume_lots": latest_volume_lots,
            "recent_volume_lots": recent_volume_lots,
            "breakout_distance_percent": breakout_distance_percent,
            "ma_converged": ma_converged,
            "two_month_consolidation": two_month_consolidation,
            "quiet_volume": quiet_volume,
        },
    )


def scan_bars(
    bars: Sequence[Bar], relative_strength_percentile: float = 0.5
) -> list[StrategySignal]:
    _ = relative_strength_percentile
    signals = [
        trend_confirmation_signal(bars),
        pullback_resume_signal(bars),
        consolidation_signal(bars),
        ma_consolidation_signal(bars),
    ]
    return [signal for signal in signals if signal is not None]
