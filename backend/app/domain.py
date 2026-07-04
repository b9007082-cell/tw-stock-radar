from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class SignalLevel(StrEnum):
    WATCH = "WATCH"
    TRIAL = "TRIAL"
    CONFIRMED = "CONFIRMED"


@dataclass(frozen=True)
class Bar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    turnover: float = 0.0


@dataclass(frozen=True)
class StrategySignal:
    strategy: str
    level: SignalLevel
    signal_date: date
    score: int
    close: float
    entry_price: float | None
    entry_zone_low: float | None
    entry_zone_high: float | None
    trigger_price: float | None
    stop_price: float | None
    risk_percent: float | None
    timing_status: str
    timing_note: str
    overheated: bool
    executable: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, float | str | bool] = field(default_factory=dict)
