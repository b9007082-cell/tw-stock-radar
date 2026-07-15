from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


RECOMMENDATION_LIMIT = 10
RECOMMENDATION_VERSION = "2026.07.r1"
MAX_STRUCTURE_RISK_PERCENT = 8.0
MIN_PULLBACK_REWARD_RISK = 1.5


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
    volume_score = 30 * _clamp((volume_ratio - 0.5) / 1.5)
    level = str(signal.get("level", ""))
    if level == "CONFIRMED":
        distance = max(0.0, (close - trigger) / trigger)
        proximity_score = 25 * _clamp(
            1.0 - max(0.0, distance - 0.03) / 0.05
        )
        distance_label = f"突破壓力 {distance * 100:.2f}%"
    else:
        distance = max(0.0, (trigger - close) / trigger)
        proximity_score = 25 * _clamp(1.0 - distance / 0.03)
        distance_label = f"距壓力 {distance * 100:.2f}%"
    score = (
        volume_score
        + proximity_score
        + _risk_score(risk_percent)
        + _slope_score(metrics)
    )
    reasons = [
        f"量比 {volume_ratio:.2f}倍",
        distance_label,
        f"結構風險 {risk_percent:.2f}%",
    ]
    latest_volume_lots = _number(metrics.get("latest_volume_lots"))
    if latest_volume_lots is not None:
        reasons.append(f"成交 {latest_volume_lots:.0f}張")
    consolidation_volume_ratio = _number(metrics.get("consolidation_volume_ratio"))
    if consolidation_volume_ratio is not None:
        reasons.append(f"整理量縮 {consolidation_volume_ratio:.2f}倍")
    if metrics.get("indicator_ideal") is True:
        reasons.append("KD/MACD同步")
    return round(score, 1), reasons


def build_recommendations(
    signals: Sequence[Mapping[str, Any]],
    *,
    limit: int = RECOMMENDATION_LIMIT,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {
        "pullback_resume": [],
        "consolidation_breakout": [],
    }
    for signal in signals:
        strategy = str(signal.get("strategy", ""))
        level = str(signal.get("level", ""))
        if strategy not in {"PULLBACK_RESUME", "CONSOLIDATION_BREAKOUT"}:
            continue
        if level not in {"TRIAL", "CONFIRMED"}:
            continue
        risk_percent = _structure_risk(signal)
        if (
            risk_percent is None
            or risk_percent <= 0
            or risk_percent > MAX_STRUCTURE_RISK_PERCENT
        ):
            continue
        raw_metrics = signal.get("metrics", {})
        metrics = raw_metrics if isinstance(raw_metrics, Mapping) else {}
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

    level_order = {"CONFIRMED": 0, "TRIAL": 1}
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
