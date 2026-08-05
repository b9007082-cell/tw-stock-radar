from datetime import date

from pydantic import BaseModel, ConfigDict


class SignalResponse(BaseModel):
    id: int
    symbol: str
    name: str
    market: str
    signal_date: date
    strategy: str
    strategy_version: str
    level: str
    score: int
    close: float
    entry_price: float | None
    entry_zone_low: float | None
    entry_zone_high: float | None
    trigger_price: float | None
    stop_price: float | None
    risk_percent: float | None
    timing_status: str | None
    timing_note: str | None
    overheated: bool
    executable: bool
    validation_status: str
    reasons: list[str]
    metrics: dict[str, float | str | bool]


class RecommendationItemResponse(SignalResponse):
    rank: int
    recommendation_score: float
    structure_risk_percent: float
    reward_risk_ratio: float | None
    ranking_reasons: list[str]


class RecommendationsResponse(BaseModel):
    as_of: date | None
    ranking_version: str
    pullback_resume: list[RecommendationItemResponse]
    consolidation_breakout: list[RecommendationItemResponse]
    bottom_reversal: list[RecommendationItemResponse]
    bollinger_squeeze: list[RecommendationItemResponse]
    intraday_ma60_touch: list[RecommendationItemResponse]
    low_price_high_yield: list[RecommendationItemResponse]
    lorentzian_ml: list[RecommendationItemResponse]


class BarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    turnover: float


class SummaryResponse(BaseModel):
    as_of: date | None
    total_signals: int
    watch: int
    trial: int
    confirmed: int
    instruments: int
    strategy_version: str
    strategy_approved: bool


class BacktestResponse(BaseModel):
    symbol: str
    strategy: str
    strategy_version: str
    trades: int
    win_rate: float
    profit_factor: float | None
    expectancy: float
    total_return: float
    max_drawdown: float
    sharpe_like: float
    gate_passed: bool
    gate_reasons: list[str]


class JobResponse(BaseModel):
    job: str
    records: int
    message: str
