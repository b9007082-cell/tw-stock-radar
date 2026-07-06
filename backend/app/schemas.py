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
    stop_price: float | None
    risk_percent: float | None
    executable: bool
    validation_status: str
    reasons: list[str]
    metrics: dict[str, float | str | bool]


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
