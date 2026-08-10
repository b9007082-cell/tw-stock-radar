from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


RECOMMENDATION_LIMIT = 10
RECOMMENDATION_VERSION = "2026.08.r15"
MAX_STRUCTURE_RISK_PERCENT = 8.0
MAX_BOTTOM_LAUNCH_RISK_PERCENT = 30.0
MIN_PULLBACK_REWARD_RISK = 1.5
MAX_LORENTZIAN_RISK_PERCENT = 10.0


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _risk_score(risk_percent: float, weight: float = 25.0) -> float:
    if 3.0 <= risk_percent <= 5.0:
        return weight
    if risk_percent < 3.0:
        return weight * (0.6 + 0.4 * _clamp(risk_percent / 3.0))
    return weight * _clamp((8.0 - risk_percent) / 3.0)


def _slope_score(metrics: Mapping[str, Any], weight: float = 20.0) -> float:
    slope = _number(metrics.get("ma20_slope_5d")) or 0.0
    return weight * _clamp(slope / 0.03)


def _structure_risk(signal: Mapping[str, Any]) -> float | None:
    close = _number(signal.get("close"))
    stop = _number(signal.get("stop_price"))
    if close is None or stop is None or close <= 0 or stop >= close:
        return None
    return ((close - stop) / close) * 100


def _pullback_score(
    signal: Mapping[str, Any],
    metrics: Mapping[str, Any],
    risk_percent: float,
) -> tuple[float, float, list[str]] | None:
    close = _number(signal.get("close"))
    stop = _number(signal.get("stop_price"))
    peak = _number(metrics.get("latest_peak"))
    ma5 = _number(metrics.get("ma5"))
    if None in (close, stop, peak, ma5) or close <= stop or ma5 <= 0:
        return None
    reward_risk = (peak - close) / (close - stop)
    if reward_risk < MIN_PULLBACK_REWARD_RISK:
        return None
    reward_score = 35 * _clamp(
        (reward_risk - MIN_PULLBACK_REWARD_RISK) / 1.5
    )
    distance_above_ma5 = max(0.0, (close - ma5) / ma5)
    reclaim_score = 20 * _clamp(
        1.0 - max(0.0, distance_above_ma5 - 0.02) / 0.03
    )
    score = (
        reward_score
        + _risk_score(risk_percent)
        + reclaim_score
        + _slope_score(metrics)
    )
    reasons = [
        f"前高空間 {reward_risk:.2f}R",
        f"結構風險 {risk_percent:.2f}%",
        f"距5MA {distance_above_ma5 * 100:.2f}%",
    ]
    latest_volume_lots = _number(metrics.get("latest_volume_lots"))
    if latest_volume_lots is not None:
        reasons.append(f"成交 {latest_volume_lots:.0f}張")
    pullback_volume_ratio = _number(metrics.get("pullback_volume_ratio"))
    rebound_volume_ratio = _number(metrics.get("rebound_volume_ratio"))
    if pullback_volume_ratio is not None:
        reasons.append(f"回檔量縮 {pullback_volume_ratio:.2f}倍")
    if rebound_volume_ratio is not None:
        reasons.append(f"轉強量 {rebound_volume_ratio:.2f}倍")
    if metrics.get("indicator_ideal") is True:
        reasons.append("KD/MACD同步")
    return round(score, 1), round(reward_risk, 2), reasons


def _breakout_score(
    signal: Mapping[str, Any],
    metrics: Mapping[str, Any],
    risk_percent: float,
) -> tuple[float, list[str]] | None:
    close = _number(signal.get("close"))
    trigger = _number(signal.get("trigger_price"))
    volume_ratio = _number(metrics.get("volume_ratio")) or 0.0
    if close is None or trigger is None or trigger <= 0:
        return None
    distance_from_low = _number(metrics.get("distance_from_low_percent"))
    base_range = _number(metrics.get("base_range_percent"))
    base_volume_ratio = _number(metrics.get("base_volume_ratio"))
    if base_volume_ratio is None:
        base_volume_ratio = _number(metrics.get("consolidation_volume_ratio"))
    volume_score = 24 * _clamp((volume_ratio - 0.8) / 1.2)
    low_zone_score = (
        18 * _clamp((45.0 - distance_from_low) / 30.0)
        if distance_from_low is not None
        else 0.0
    )
    base_score = (
        14 * _clamp((30.0 - base_range) / 18.0)
        if base_range is not None
        else 0.0
    )
    contraction_score = (
        10 * _clamp((1.1 - base_volume_ratio) / 0.35)
        if base_volume_ratio is not None
        else 0.0
    )
    level = str(signal.get("level", ""))
    if level == "CONFIRMED":
        distance = max(0.0, (close - trigger) / trigger)
        proximity_score = 16 * _clamp(
            1.0 - max(0.0, distance - 0.03) / 0.05
        )
        distance_label = f"突破壓力 {distance * 100:.2f}%"
    else:
        distance = max(0.0, (trigger - close) / trigger)
        proximity_score = 16 * _clamp(1.0 - distance / 0.03)
        distance_label = f"距壓力 {distance * 100:.2f}%"
    score = (
        volume_score
        + proximity_score
        + _risk_score(risk_percent, weight=18.0)
        + _slope_score(metrics, weight=12.0)
        + low_zone_score
        + base_score
        + contraction_score
    )
    reasons = [
        f"量比 {volume_ratio:.2f}倍",
        distance_label,
        f"結構風險 {risk_percent:.2f}%",
    ]
    latest_volume_lots = _number(metrics.get("latest_volume_lots"))
    if latest_volume_lots is not None:
        reasons.append(f"成交 {latest_volume_lots:.0f}張")
    if distance_from_low is not None:
        reasons.append(f"距60日低點 {distance_from_low:.1f}%")
    if base_range is not None:
        reasons.append(f"20日區間 {base_range:.1f}%")
    if base_volume_ratio is not None:
        reasons.append(f"整理量縮 {base_volume_ratio:.2f}倍")
    if metrics.get("indicator_ideal") is True:
        reasons.append("KD/MACD同步")
    return round(score, 1), reasons


def _bottom_reversal_score(
    signal: Mapping[str, Any],
    metrics: Mapping[str, Any],
) -> tuple[float, list[str]] | None:
    drawdown = _number(metrics.get("drawdown_percent"))
    volume_ratio = _number(metrics.get("stop_volume_ratio"))
    stop_low = _number(metrics.get("previous_stop_low"))
    close = _number(signal.get("close"))
    if drawdown is None or volume_ratio is None or stop_low is None or close is None:
        return None
    risk_percent = ((close - stop_low) / close) * 100 if close > stop_low else 99.0
    if risk_percent <= 0 or risk_percent > MAX_STRUCTURE_RISK_PERCENT:
        return None
    drawdown_score = 30 * _clamp((drawdown - 15.0) / 15.0)
    volume_score = 30 * _clamp((volume_ratio - 2.0) / 2.0)
    risk_component = _risk_score(risk_percent, weight=25.0)
    confirmation_score = 15 if metrics.get("confirmed_buy") is True else 6
    score = drawdown_score + volume_score + risk_component + confirmation_score
    reasons = [
        f"跌幅 {drawdown:.1f}%",
        f"爆量 {volume_ratio:.2f}倍",
        f"止跌K風險 {risk_percent:.2f}%",
        "突破止跌K高點" if metrics.get("confirmed_buy") is True else "等待突破止跌K高點",
    ]
    latest_volume_lots = _number(metrics.get("latest_volume_lots"))
    stop_volume_lots = _number(metrics.get("stop_volume_lots"))
    if latest_volume_lots is not None:
        reasons.append(f"成交 {latest_volume_lots:.0f}張")
    if stop_volume_lots is not None:
        reasons.append(f"止跌K {stop_volume_lots:.0f}張")
    return round(score, 1), reasons


def _disposition_reversal_score(
    signal: Mapping[str, Any],
    metrics: Mapping[str, Any],
) -> tuple[float, float, list[str]] | None:
    close = _number(signal.get("close"))
    stop_low = _number(metrics.get("previous_stop_low"))
    drawdown = _number(metrics.get("drawdown_percent"))
    similarity = _number(metrics.get("disposition_similarity_score"))
    volume_ratio = _number(metrics.get("stop_volume_ratio"))
    limit_like_days = _number(metrics.get("limit_like_drop_days")) or 0.0
    deviation = _number(metrics.get("deviation_rate_percent")) or 0.0
    if (
        close is None
        or stop_low is None
        or drawdown is None
        or similarity is None
        or volume_ratio is None
        or close <= stop_low
    ):
        return None
    risk_percent = ((close - stop_low) / close) * 100
    if risk_percent <= 0:
        return None
    similarity_score = 32 * _clamp(similarity / 100.0)
    drawdown_score = 22 * _clamp((drawdown - 25.0) / 25.0)
    disposition_score = 16 * _clamp(limit_like_days / 4.0)
    volume_score = 16 * _clamp((volume_ratio - 2.0) / 2.0)
    deviation_score = 8 * _clamp(abs(min(0.0, deviation)) / 30.0)
    confirmation_score = 6 if metrics.get("confirmed_buy") is True else 2
    risk_penalty = 8 * _clamp(max(0.0, risk_percent - 12.0) / 18.0)
    score = (
        similarity_score
        + drawdown_score
        + disposition_score
        + volume_score
        + deviation_score
        + confirmation_score
        - risk_penalty
    )
    reasons = [
        f"相似度 {similarity:.0f}分",
        f"跌幅 {drawdown:.1f}%",
        f"急跌日 {limit_like_days:.0f}天",
        f"爆量 {volume_ratio:.2f}倍",
        f"止跌K風險 {risk_percent:.2f}%",
        "突破止跌K高點" if metrics.get("confirmed_buy") is True else "等待突破止跌K高點",
    ]
    status = metrics.get("inferred_disposition_status")
    if isinstance(status, str):
        reasons.append(status)
    latest_volume_lots = _number(metrics.get("latest_volume_lots"))
    if latest_volume_lots is not None:
        reasons.append(f"成交 {latest_volume_lots:.0f}張")
    return round(score, 1), round(risk_percent, 2), reasons


def _lorentzian_score(
    signal: Mapping[str, Any],
    metrics: Mapping[str, Any],
) -> tuple[float, float, list[str]] | None:
    prediction = _number(metrics.get("ml_prediction"))
    neighbors = _number(metrics.get("ml_neighbors")) or 8.0
    confidence = _number(metrics.get("ml_confidence"))
    kernel_slope = _number(metrics.get("kernel_slope_percent")) or 0.0
    rs_percentile = _number(metrics.get("relative_strength_percentile")) or 0.0
    risk_percent = _number(metrics.get("structure_risk_percent"))
    if (
        prediction is None
        or confidence is None
        or risk_percent is None
        or prediction <= 0
        or risk_percent <= 0
        or risk_percent > MAX_LORENTZIAN_RISK_PERCENT
    ):
        return None
    prediction_score = 25 * _clamp(prediction / neighbors)
    confidence_score = 30 * _clamp(confidence)
    kernel_score = 20 * _clamp((kernel_slope + 0.5) / 2.0)
    relative_strength_score = 15 * _clamp((rs_percentile - 0.45) / 0.35)
    risk_component = _risk_score(min(risk_percent, 8.0), weight=10.0)
    score = (
        prediction_score
        + confidence_score
        + kernel_score
        + relative_strength_score
        + risk_component
    )
    reasons = [
        f"ML投票 {prediction:+.0f}/{neighbors:.0f}",
        f"信心 {confidence * 100:.0f}%",
        f"Kernel斜率 {kernel_slope:.2f}%",
        f"相對強度 {rs_percentile * 100:.0f}%",
        f"結構風險 {risk_percent:.2f}%",
    ]
    latest_volume_lots = _number(metrics.get("latest_volume_lots"))
    if latest_volume_lots is not None:
        reasons.append(f"成交 {latest_volume_lots:.0f}張")
    return round(score, 1), round(risk_percent, 2), reasons


def _bollinger_squeeze_score(
    signal: Mapping[str, Any],
    metrics: Mapping[str, Any],
) -> tuple[float, float, list[str]] | None:
    close = _number(signal.get("close"))
    upper = _number(metrics.get("bollinger_upper"))
    lower = _number(metrics.get("bollinger_lower"))
    width_percent = _number(metrics.get("bollinger_width_percent"))
    width_percentile = _number(metrics.get("bollinger_width_percentile"))
    previous_width_percentile = _number(metrics.get("previous_bollinger_width_percentile"))
    volume_ratio = _number(metrics.get("volume_ratio")) or 0.0
    close_position_percent = _number(metrics.get("close_position_percent")) or 0.0
    if (
        close is None
        or upper is None
        or lower is None
        or width_percent is None
        or width_percentile is None
        or previous_width_percentile is None
        or upper <= lower
    ):
        return None
    if not (
        metrics.get("bollinger_first_breakout_upper") is True
        and metrics.get("main_force_buying") is True
    ):
        return None
    breakout_distance_percent = ((close - upper) / upper) * 100
    observation_risk_percent = 0.0
    squeeze_score = 30 * _clamp((0.25 - previous_width_percentile) / 0.25)
    breakout_score = 25 * _clamp(breakout_distance_percent / 3.0)
    volume_score = 25 * _clamp((volume_ratio - 1.2) / 1.3)
    close_position_score = 10 * _clamp((close_position_percent - 70.0) / 25.0)
    score = (
        squeeze_score
        + breakout_score
        + volume_score
        + close_position_score
        + _risk_score(observation_risk_percent, weight=10.0)
    )
    reasons = [
        f"布林寬度 {width_percent:.2f}%",
        f"前一日寬度分位 {previous_width_percentile * 100:.0f}%",
        f"突破上軌 {breakout_distance_percent:+.2f}%",
        "第一根突破上軌",
        "主力攻擊量",
    ]
    latest_volume_lots = _number(metrics.get("latest_volume_lots"))
    if latest_volume_lots is not None:
        reasons.append(f"成交 {latest_volume_lots:.0f}張")
    if volume_ratio:
        reasons.append(f"量比 {volume_ratio:.2f}倍")
    return round(score, 1), round(observation_risk_percent, 2), reasons


def _intraday_ma60_score(
    signal: Mapping[str, Any],
    metrics: Mapping[str, Any],
) -> tuple[float, float, list[str]] | None:
    distance = _number(metrics.get("intraday_abs_distance_to_ma60_percent"))
    signed_distance = _number(metrics.get("intraday_distance_to_ma60_percent"))
    slope = _number(metrics.get("intraday_ma60_slope_percent")) or 0.0
    ma60 = _number(metrics.get("intraday_ma60"))
    close = _number(metrics.get("intraday_close")) or _number(signal.get("close"))
    volume_lots = _number(metrics.get("daily_volume_lots"))
    intraday_volume_ratio = _number(metrics.get("intraday_volume_ratio")) or 0.0
    ma60_turning_up = metrics.get("intraday_ma60_turning_up") is True
    volume_breakout = metrics.get("intraday_volume_breakout") is True
    reclaimed = metrics.get("reclaimed_intraday_ma60") is True
    pullback_hold = metrics.get("pulled_back_without_breaking_intraday_ma60") is True
    if distance is None or signed_distance is None or ma60 is None or close is None:
        return None
    if not ma60_turning_up:
        return None
    distance_score = 34 * _clamp((1.5 - distance) / 1.5)
    slope_score = 24 * _clamp(slope / 0.8)
    setup_score = 20 if reclaimed else 16 if pullback_hold else 10 if signed_distance >= 0 else 4
    volume_score = (
        14 * _clamp((intraday_volume_ratio - 1.0) / 1.0)
        if intraday_volume_ratio > 0
        else 8 * _clamp(((volume_lots or 0.0) - 2000) / 8000)
    )
    confirmation_score = 8 if volume_breakout else 0
    score = (
        distance_score
        + slope_score
        + setup_score
        + volume_score
        + confirmation_score
    )
    reasons = [
        f"距60分MA60 {signed_distance:+.2f}%",
        f"60MA上彎 {slope:+.2f}%",
        "放量突破60MA"
        if reclaimed and volume_breakout
        else "回踩60MA不破"
        if pullback_hold
        else "站上60MA"
        if signed_distance >= 0
        else "等待站回60MA",
    ]
    if intraday_volume_ratio > 0:
        reasons.append(f"60分量比 {intraday_volume_ratio:.2f}倍")
    if volume_lots is not None:
        reasons.append(f"日成交 {volume_lots:.0f}張")
    return round(score, 1), round(distance, 2), reasons


def _low_price_high_yield_score(
    signal: Mapping[str, Any],
    metrics: Mapping[str, Any],
) -> tuple[float, float, list[str]] | None:
    dividend_yield = _number(metrics.get("dividend_yield"))
    drawdown = _number(metrics.get("drawdown_from_high_percent"))
    distance_from_low = _number(metrics.get("distance_from_low_percent"))
    pb_ratio = _number(metrics.get("pb_ratio"))
    pe_ratio = _number(metrics.get("pe_ratio"))
    volume_lots = _number(metrics.get("latest_volume_lots"))
    if dividend_yield is None or drawdown is None or distance_from_low is None:
        return None
    yield_score = 36 * _clamp((dividend_yield - 5.0) / 4.0)
    low_score = 26 * _clamp((20.0 - distance_from_low) / 20.0)
    drawdown_score = 18 * _clamp((drawdown - 12.0) / 18.0)
    pb_score = 12 * _clamp((1.8 - (pb_ratio or 1.8)) / 1.0)
    volume_score = 8 * _clamp(((volume_lots or 0.0) - 2000) / 8000)
    score = yield_score + low_score + drawdown_score + pb_score + volume_score
    reasons = [
        f"殖利率 {dividend_yield:.2f}%",
        f"高點回落 {drawdown:.1f}%",
        f"距低點 {distance_from_low:.1f}%",
    ]
    if pb_ratio is not None:
        reasons.append(f"P/B {pb_ratio:.2f}")
    if pe_ratio is not None and pe_ratio > 0:
        reasons.append(f"本益比 {pe_ratio:.2f}")
    if volume_lots is not None:
        reasons.append(f"成交 {volume_lots:.0f}張")
    return round(score, 1), round(distance_from_low, 2), reasons


def build_recommendations(
    signals: Sequence[Mapping[str, Any]],
    *,
    limit: int = RECOMMENDATION_LIMIT,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {
        "pullback_resume": [],
        "consolidation_breakout": [],
        "disposition_reversal": [],
        "bottom_reversal": [],
        "bollinger_squeeze": [],
        "intraday_ma60_touch": [],
        "low_price_high_yield": [],
        "lorentzian_ml": [],
    }
    for signal in signals:
        strategy = str(signal.get("strategy", ""))
        level = str(signal.get("level", ""))
        raw_metrics = signal.get("metrics", {})
        metrics = raw_metrics if isinstance(raw_metrics, Mapping) else {}
        if strategy == "BOTTOM_REVERSAL":
            if level not in {"WATCH", "CONFIRMED"}:
                continue
            result = _bottom_reversal_score(signal, metrics)
            if result is None:
                continue
            score, reasons = result
            grouped["bottom_reversal"].append(
                {
                    **signal,
                    "rank": 0,
                    "recommendation_score": score,
                    "structure_risk_percent": round(
                        ((float(signal["close"]) - float(metrics["previous_stop_low"]))
                         / float(signal["close"])) * 100,
                        2,
                    ),
                    "reward_risk_ratio": None,
                    "ranking_reasons": reasons,
                }
            )
            continue
        if strategy == "LORENTZIAN_ML":
            if level not in {"WATCH", "TRIAL", "CONFIRMED"}:
                continue
            result = _lorentzian_score(signal, metrics)
            if result is None:
                continue
            score, risk_percent, reasons = result
            grouped["lorentzian_ml"].append(
                {
                    **signal,
                    "rank": 0,
                    "recommendation_score": score,
                    "structure_risk_percent": risk_percent,
                    "reward_risk_ratio": None,
                    "ranking_reasons": reasons,
                }
            )
            continue
        if strategy == "BOLLINGER_SQUEEZE":
            if level not in {"WATCH", "TRIAL", "CONFIRMED"}:
                continue
            result = _bollinger_squeeze_score(signal, metrics)
            if result is None:
                continue
            score, observation_risk_percent, reasons = result
            grouped["bollinger_squeeze"].append(
                {
                    **signal,
                    "rank": 0,
                    "recommendation_score": score,
                    "structure_risk_percent": observation_risk_percent,
                    "reward_risk_ratio": None,
                    "ranking_reasons": reasons,
                }
            )
            continue
        if strategy == "INTRADAY_MA60_TOUCH":
            if level not in {"WATCH", "TRIAL", "CONFIRMED"}:
                continue
            result = _intraday_ma60_score(signal, metrics)
            if result is None:
                continue
            score, distance_percent, reasons = result
            grouped["intraday_ma60_touch"].append(
                {
                    **signal,
                    "rank": 0,
                    "recommendation_score": score,
                    "structure_risk_percent": distance_percent,
                    "reward_risk_ratio": None,
                    "ranking_reasons": reasons,
                }
            )
            continue
        if strategy == "DISPOSITION_REVERSAL":
            if level not in {"WATCH", "CONFIRMED"}:
                continue
            result = _disposition_reversal_score(signal, metrics)
            if result is None:
                continue
            score, risk_percent, reasons = result
            grouped["disposition_reversal"].append(
                {
                    **signal,
                    "rank": 0,
                    "recommendation_score": score,
                    "structure_risk_percent": risk_percent,
                    "reward_risk_ratio": None,
                    "ranking_reasons": reasons,
                }
            )
            continue
        if strategy == "LOW_PRICE_HIGH_YIELD":
            if level not in {"WATCH", "TRIAL", "CONFIRMED"}:
                continue
            result = _low_price_high_yield_score(signal, metrics)
            if result is None:
                continue
            score, distance_percent, reasons = result
            grouped["low_price_high_yield"].append(
                {
                    **signal,
                    "rank": 0,
                    "recommendation_score": score,
                    "structure_risk_percent": distance_percent,
                    "reward_risk_ratio": None,
                    "ranking_reasons": reasons,
                }
            )
            continue
        if strategy not in {"PULLBACK_RESUME", "CONSOLIDATION_BREAKOUT"}:
            continue
        allowed_levels = (
            {"WATCH", "TRIAL", "CONFIRMED"}
            if strategy == "CONSOLIDATION_BREAKOUT"
            else {"TRIAL", "CONFIRMED"}
        )
        if level not in allowed_levels:
            continue
        risk_percent = _structure_risk(signal)
        max_risk_percent = (
            MAX_BOTTOM_LAUNCH_RISK_PERCENT
            if strategy == "CONSOLIDATION_BREAKOUT"
            else MAX_STRUCTURE_RISK_PERCENT
        )
        if (
            risk_percent is None
            or risk_percent <= 0
            or risk_percent > max_risk_percent
        ):
            continue
        reward_risk_ratio: float | None = None
        if strategy == "PULLBACK_RESUME":
            result = _pullback_score(signal, metrics, risk_percent)
            if result is None:
                continue
            score, reward_risk_ratio, reasons = result
            key = "pullback_resume"
        else:
            result = _breakout_score(signal, metrics, risk_percent)
            if result is None:
                continue
            score, reasons = result
            key = "consolidation_breakout"
        grouped[key].append(
            {
                **signal,
                "rank": 0,
                "recommendation_score": score,
                "structure_risk_percent": round(risk_percent, 2),
                "reward_risk_ratio": reward_risk_ratio,
                "ranking_reasons": reasons,
            }
        )

    level_order = {"CONFIRMED": 0, "TRIAL": 1, "WATCH": 2}
    for items in grouped.values():
        items.sort(
            key=lambda item: (
                level_order[str(item["level"])],
                -float(item["recommendation_score"]),
                str(item["symbol"]),
            )
        )
        del items[limit:]
        for rank, item in enumerate(items, start=1):
            item["rank"] = rank
    return grouped
