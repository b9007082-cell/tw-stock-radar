from collections.abc import Sequence

from app.domain import Bar, SignalLevel, StrategySignal
from app.services.indicators import confirmed_swings, percent_change, sma


MIN_BARS = 65


def _entry_timing(
    *,
    strategy: str,
    level: SignalLevel,
    latest: Bar,
    ma5: float,
    ma10: float,
    trigger_price: float,
    support_price: float,
) -> tuple[float, float, str, str, bool]:
    distance_ma5 = (latest.close / ma5) - 1 if ma5 else 1.0
    overheated = distance_ma5 > 0.08

    if level == SignalLevel.WATCH:
        if strategy == "CONSOLIDATION_BREAKOUT":
            zone_low = trigger_price
            zone_high = trigger_price * 1.01
            note = "等待收盤站上箱頂，且成交量達20日均量1.5倍。"
        else:
            zone_low = min(ma10, ma5)
            zone_high = max(ma10, ma5)
            note = "等待重新站回5日線並突破前一日高點，跌破20日線取消。"
        return (
            round(zone_low, 2),
            round(zone_high, 2),
            "WAIT_CONFIRMATION",
            note,
            overheated,
        )

    anchor = max(support_price, ma5)
    zone_low = min(anchor, latest.close)
    zone_high = min(latest.close, anchor * 1.03)
    zone_high = max(zone_low, zone_high)

    if overheated:
        status = "OVERHEATED"
        note = "現價高於5日線超過8%，暫不追價，等待量縮回測5至10日線。"
    elif distance_ma5 > 0.03:
        status = "WAIT_PULLBACK"
        note = "訊號成立但離5日線超過3%，等待回到進場區且支撐不破。"
    elif level == SignalLevel.TRIAL:
        status = "TRIAL_ENTRY"
        note = "位於試單區，可用0.5%帳戶風險分批，確認價失守則退出。"
    else:
        status = "READY"
        note = "量價與趨勢已確認，可在進場區分批，避免高於區間上緣追價。"

    return (
        round(zone_low, 2),
        round(zone_high, 2),
        status,
        note,
        overheated,
    )


def _risk(
    bars: Sequence[Bar], ma20: float, entry: float
) -> tuple[float, float, bool]:
    swing_low = min(bar.low for bar in bars[-10:])
    stop = max(swing_low, ma20 * 0.99)
    risk_percent = max(0.0, (entry - stop) / entry)
    return round(stop, 2), round(risk_percent * 100, 2), 0 < risk_percent <= 0.08


def _trend_structure(bars: Sequence[Bar]) -> tuple[bool, bool]:
    peaks, troughs = confirmed_swings(bars)
    higher_high = len(peaks) >= 2 and peaks[-1][1] > peaks[-2][1]
    higher_low = len(troughs) >= 2 and troughs[-1][1] > troughs[-2][1]
    return higher_high, higher_low


def _common_metrics(bars: Sequence[Bar]) -> dict[str, float | bool]:
    closes = [bar.close for bar in bars]
    volumes = [float(bar.volume) for bar in bars]
    ma5s = sma(closes, 5)
    ma10s = sma(closes, 10)
    ma20s = sma(closes, 20)
    ma60s = sma(closes, 60)
    vol5s = sma(volumes, 5)
    vol10s = sma(volumes, 10)
    vol20s = sma(volumes, 20)
    index = len(bars) - 1
    ma5 = float(ma5s[index] or 0)
    ma10 = float(ma10s[index] or 0)
    ma20 = float(ma20s[index] or 0)
    ma60 = float(ma60s[index] or 0)
    ma20_10 = float(ma20s[index - 10] or ma20)
    ma60_10 = float(ma60s[index - 10] or ma60)
    higher_high, higher_low = _trend_structure(bars)
    return {
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "ma60": ma60,
        "ma20_slope_10d": percent_change(ma20, ma20_10),
        "ma60_slope_10d": percent_change(ma60, ma60_10),
        "vol5": float(vol5s[index] or 0),
        "vol10": float(vol10s[index] or 0),
        "vol20": float(vol20s[index] or 0),
        "higher_high": higher_high,
        "higher_low": higher_low,
        "return60": percent_change(bars[-1].close, bars[-61].close),
    }


def consolidation_signal(bars: Sequence[Bar]) -> StrategySignal | None:
    if len(bars) < MIN_BARS:
        return None
    latest = bars[-1]
    metrics = _common_metrics(bars)
    base = bars[-41:-1]
    box_top = max(bar.high for bar in base)
    box_bottom = min(bar.low for bar in base)
    box_range = (box_top / box_bottom) - 1 if box_bottom else 1.0
    distance_to_top = (box_top - latest.close) / box_top
    volume_ratio = latest.volume / float(metrics["vol20"] or 1)
    vol_contract = float(metrics["vol5"]) / float(metrics["vol20"] or 1)
    ma20_slope = float(metrics["ma20_slope_10d"])
    distance_ma5 = (latest.close / float(metrics["ma5"])) - 1

    common_trend = (
        latest.close > float(metrics["ma20"])
        and float(metrics["ma20"]) > float(metrics["ma60"])
        and float(metrics["ma60_slope_10d"]) > 0
    )
    valid_base = (
        box_range <= 0.20
        and -0.03 <= distance_to_top <= 0.05
        and -0.01 <= ma20_slope <= 0.03
        and latest.close > box_bottom
    )
    watch = valid_base and vol_contract <= 0.80
    recent_10_high = max(bar.high for bar in bars[-11:-1])
    trial = valid_base and latest.close > recent_10_high and volume_ratio >= 1.2
    confirmed = (
        box_range <= 0.20
        and latest.close > box_top
        and volume_ratio >= 1.5
        and distance_ma5 <= 0.08
        and common_trend
    )

    if confirmed:
        level = SignalLevel.CONFIRMED
    elif trial and common_trend:
        level = SignalLevel.TRIAL
    elif watch:
        level = SignalLevel.WATCH
    else:
        return None

    entry_zone_low, entry_zone_high, timing_status, timing_note, overheated = (
        _entry_timing(
            strategy="CONSOLIDATION_BREAKOUT",
            level=level,
            latest=latest,
            ma5=float(metrics["ma5"]),
            ma10=float(metrics["ma10"]),
            trigger_price=box_top,
            support_price=box_top,
        )
    )
    entry = entry_zone_high
    stop, risk_percent, executable = _risk(
        bars, float(metrics["ma20"]), entry
    )
    reasons = [
        f"40日箱型振幅 {box_range:.1%}",
        f"距箱頂 {distance_to_top:.1%}",
        f"量比（當日/20日）{volume_ratio:.2f}",
    ]
    if bool(metrics["higher_high"]) and bool(metrics["higher_low"]):
        reasons.append("已形成頭頭高、底底高")
    if level == SignalLevel.CONFIRMED:
        reasons.append("收盤帶量突破40日箱頂")
    elif level == SignalLevel.TRIAL:
        reasons.append("收盤突破10日高點，進入試單區")
    else:
        reasons.append("量縮整理且接近箱頂")

    details = dict(metrics)
    details.update(
        box_top=box_top,
        box_bottom=box_bottom,
        box_range=box_range,
        distance_to_top=distance_to_top,
        volume_ratio=volume_ratio,
    )
    return StrategySignal(
        strategy="CONSOLIDATION_BREAKOUT",
        level=level,
        signal_date=latest.date,
        score={SignalLevel.WATCH: 60, SignalLevel.TRIAL: 78, SignalLevel.CONFIRMED: 92}[level],
        close=latest.close,
        entry_price=round(entry, 2),
        entry_zone_low=entry_zone_low,
        entry_zone_high=entry_zone_high,
        trigger_price=round(box_top, 2),
        stop_price=stop,
        risk_percent=risk_percent,
        timing_status=timing_status,
        timing_note=timing_note,
        overheated=overheated,
        executable=executable and level != SignalLevel.WATCH,
        reasons=reasons,
        metrics=details,
    )


def strong_pullback_signal(
    bars: Sequence[Bar], relative_strength_percentile: float
) -> StrategySignal | None:
    if len(bars) < MIN_BARS:
        return None
    latest = bars[-1]
    previous = bars[-2]
    metrics = _common_metrics(bars)
    closes = [bar.close for bar in bars]
    ma5s = sma(closes, 5)
    ma20 = float(metrics["ma20"])
    ma5 = float(metrics["ma5"])
    ma10 = float(metrics["ma10"])
    previous_ma5 = float(ma5s[-2] or 0)
    recent_60_high = max(bar.high for bar in bars[-60:])
    recent_20_high = max(bar.high for bar in bars[-20:])
    drawdown = (recent_20_high - latest.close) / recent_20_high
    volume_ratio = latest.volume / float(metrics["vol20"] or 1)
    recent_below_ma5 = any(
        bars[index].close < float(ma5s[index] or 0)
        for index in range(len(bars) - 4, len(bars) - 1)
    )
    below_days = 0
    for index in range(len(bars) - 1, max(-1, len(bars) - 5), -1):
        if bars[index].close < float(ma5s[index] or 0):
            below_days += 1
        else:
            break

    strong = (
        latest.close > ma20
        and ma20 > float(metrics["ma60"])
        and float(metrics["ma20_slope_10d"]) > 0
        and float(metrics["ma60_slope_10d"]) > 0
        and relative_strength_percentile >= 0.80
        and recent_20_high >= recent_60_high
    )
    watch = strong and 1 <= below_days <= 3 and drawdown <= 0.12
    trial = (
        strong
        and previous.close < previous_ma5
        and latest.close > ma5
        and latest.close > previous.high
        and volume_ratio >= 1.0
    )
    confirmed = (
        strong
        and recent_below_ma5
        and latest.close > max(bar.high for bar in bars[-6:-1])
        and latest.close > ma5
        and volume_ratio >= 1.2
    )

    if confirmed:
        level = SignalLevel.CONFIRMED
    elif trial:
        level = SignalLevel.TRIAL
    elif watch:
        level = SignalLevel.WATCH
    else:
        return None

    trigger_price = (
        max(bar.high for bar in bars[-6:-1])
        if level == SignalLevel.CONFIRMED
        else previous.high
    )
    entry_zone_low, entry_zone_high, timing_status, timing_note, overheated = (
        _entry_timing(
            strategy="STRONG_PULLBACK",
            level=level,
            latest=latest,
            ma5=ma5,
            ma10=ma10,
            trigger_price=trigger_price,
            support_price=ma10,
        )
    )
    entry = entry_zone_high
    stop, risk_percent, executable = _risk(bars, ma20, entry)
    reasons = [
        f"60日相對強度百分位 {relative_strength_percentile:.0%}",
        f"距20日高點回撤 {drawdown:.1%}",
        f"量比（當日/20日）{volume_ratio:.2f}",
    ]
    if level == SignalLevel.WATCH:
        reasons.append(f"跌破5日線 {below_days} 日，仍守在20日線之上")
    elif level == SignalLevel.TRIAL:
        reasons.append("收盤重新站回5日線並突破前一日高點")
    else:
        reasons.append("回檔後突破最近5日高點，確認轉強")

    details = dict(metrics)
    details.update(
        relative_strength_percentile=relative_strength_percentile,
        drawdown=drawdown,
        volume_ratio=volume_ratio,
        below_ma5_days=below_days,
    )
    return StrategySignal(
        strategy="STRONG_PULLBACK",
        level=level,
        signal_date=latest.date,
        score={SignalLevel.WATCH: 65, SignalLevel.TRIAL: 82, SignalLevel.CONFIRMED: 94}[level],
        close=latest.close,
        entry_price=round(entry, 2),
        entry_zone_low=entry_zone_low,
        entry_zone_high=entry_zone_high,
        trigger_price=round(trigger_price, 2),
        stop_price=stop,
        risk_percent=risk_percent,
        timing_status=timing_status,
        timing_note=timing_note,
        overheated=overheated,
        executable=executable and level != SignalLevel.WATCH,
        reasons=reasons,
        metrics=details,
    )


def scan_bars(
    bars: Sequence[Bar], relative_strength_percentile: float = 0.5
) -> list[StrategySignal]:
    signals = [
        consolidation_signal(bars),
        strong_pullback_signal(bars, relative_strength_percentile),
    ]
    return [signal for signal in signals if signal is not None]
