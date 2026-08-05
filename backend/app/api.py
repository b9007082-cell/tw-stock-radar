import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import DailyPrice, Instrument, Signal
from app.schemas import (
    BacktestResponse,
    BarResponse,
    JobResponse,
    RecommendationsResponse,
    SignalResponse,
    SummaryResponse,
)
from app.services.backtest import backtest
from app.services.recommendations import (
    RECOMMENDATION_VERSION,
    build_recommendations,
)
from app.services.scanner import _load_bars
from app.services.demo_data import seed_demo
from app.services.market_data import OfficialSnapshotClient, upsert_market_rows
from app.services.scanner import run_scan

router = APIRouter(prefix="/api")


def _signal_response(signal: Signal, instrument: Instrument) -> SignalResponse:
    metrics = json.loads(signal.metrics_json)
    return SignalResponse(
        id=signal.id,
        symbol=instrument.symbol,
        name=instrument.name,
        market=instrument.market,
        signal_date=signal.signal_date,
        strategy=signal.strategy,
        strategy_version=signal.strategy_version,
        level=signal.level,
        score=signal.score,
        close=float(signal.close),
        entry_price=float(signal.entry_price) if signal.entry_price is not None else None,
        entry_zone_low=metrics.pop("_entry_zone_low", None),
        entry_zone_high=metrics.pop("_entry_zone_high", None),
        trigger_price=metrics.pop("_trigger_price", None),
        stop_price=float(signal.stop_price) if signal.stop_price is not None else None,
        risk_percent=(
            float(signal.risk_percent) if signal.risk_percent is not None else None
        ),
        timing_status=metrics.pop("_timing_status", None),
        timing_note=metrics.pop("_timing_note", None),
        overheated=bool(metrics.pop("_overheated", False)),
        executable=signal.executable,
        validation_status="APPROVED" if signal.executable else "RESEARCH",
        reasons=json.loads(signal.reasons_json),
        metrics=metrics,
    )


@router.get("/summary", response_model=SummaryResponse)
def summary(session: Session = Depends(get_db)) -> SummaryResponse:
    settings = get_settings()
    latest = session.scalar(select(func.max(Signal.signal_date)))
    counts = {"WATCH": 0, "TRIAL": 0, "CONFIRMED": 0}
    if latest:
        for level, count in session.execute(
            select(Signal.level, func.count(Signal.id))
            .where(Signal.signal_date == latest)
            .group_by(Signal.level)
        ):
            counts[level] = count
    return SummaryResponse(
        as_of=latest,
        total_signals=sum(counts.values()),
        watch=counts["WATCH"],
        trial=counts["TRIAL"],
        confirmed=counts["CONFIRMED"],
        instruments=session.scalar(select(func.count(Instrument.id))) or 0,
        strategy_version=settings.strategy_version,
        strategy_approved=settings.strategy_approved,
    )


@router.get("/signals", response_model=list[SignalResponse])
def signals(
    level: str | None = Query(default=None, pattern="^(WATCH|TRIAL|CONFIRMED)$"),
    strategy: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db),
) -> list[SignalResponse]:
    latest = session.scalar(select(func.max(Signal.signal_date)))
    if latest is None:
        return []
    query = (
        select(Signal, Instrument)
        .join(Instrument, Signal.instrument_id == Instrument.id)
        .where(Signal.signal_date == latest)
    )
    if level:
        query = query.where(Signal.level == level)
    if strategy:
        query = query.where(Signal.strategy == strategy)
    rows = session.execute(
        query.order_by(Signal.score.desc(), Instrument.symbol).limit(limit)
    ).all()
    return [_signal_response(signal, instrument) for signal, instrument in rows]


@router.get("/recommendations", response_model=RecommendationsResponse)
def recommendations(
    session: Session = Depends(get_db),
) -> RecommendationsResponse:
    latest = session.scalar(select(func.max(Signal.signal_date)))
    if latest is None:
        return RecommendationsResponse(
            as_of=None,
            ranking_version=RECOMMENDATION_VERSION,
            pullback_resume=[],
            consolidation_breakout=[],
            bottom_reversal=[],
            bollinger_squeeze=[],
            intraday_ma60_touch=[],
            low_price_high_yield=[],
            lorentzian_ml=[],
        )
    rows = session.execute(
        select(Signal, Instrument)
        .join(Instrument, Signal.instrument_id == Instrument.id)
        .where(
            Signal.signal_date == latest,
            Signal.strategy.in_(
                [
                    "PULLBACK_RESUME",
                    "CONSOLIDATION_BREAKOUT",
                    "BOTTOM_REVERSAL",
                    "BOLLINGER_SQUEEZE",
                    "INTRADAY_MA60_TOUCH",
                    "LOW_PRICE_HIGH_YIELD",
                    "LORENTZIAN_ML",
                ]
            ),
        )
    ).all()
    payload = [
        _signal_response(signal, instrument).model_dump(mode="json")
        for signal, instrument in rows
    ]
    ranked = build_recommendations(payload)
    return RecommendationsResponse(
        as_of=latest,
        ranking_version=RECOMMENDATION_VERSION,
        pullback_resume=ranked["pullback_resume"],
        consolidation_breakout=ranked["consolidation_breakout"],
        bottom_reversal=ranked["bottom_reversal"],
        bollinger_squeeze=ranked["bollinger_squeeze"],
        intraday_ma60_touch=ranked["intraday_ma60_touch"],
        low_price_high_yield=ranked["low_price_high_yield"],
        lorentzian_ml=ranked["lorentzian_ml"],
    )


@router.get("/instruments/{symbol}/bars", response_model=list[BarResponse])
def instrument_bars(
    symbol: str,
    limit: int = Query(default=180, ge=20, le=1000),
    session: Session = Depends(get_db),
) -> list[BarResponse]:
    instrument = session.scalar(
        select(Instrument).where(Instrument.symbol == symbol)
    )
    if instrument is None:
        raise HTTPException(status_code=404, detail="Instrument not found")
    rows = session.scalars(
        select(DailyPrice)
        .where(DailyPrice.instrument_id == instrument.id)
        .order_by(DailyPrice.trade_date.desc())
        .limit(limit)
    ).all()
    return [
        BarResponse(
            trade_date=row.trade_date,
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=row.volume,
            turnover=float(row.turnover),
        )
        for row in reversed(rows)
    ]


@router.get(
    "/instruments/{symbol}/backtest",
    response_model=BacktestResponse,
)
def instrument_backtest(
    symbol: str,
    strategy: str = Query(
        default="PULLBACK_RESUME",
        pattern=(
            "^(TREND_CONFIRMATION|PULLBACK_RESUME|"
            "CONSOLIDATION_BREAKOUT|BOTTOM_REVERSAL|BOLLINGER_SQUEEZE|"
            "INTRADAY_MA60_TOUCH|LOW_PRICE_HIGH_YIELD|LORENTZIAN_ML)$"
        ),
    ),
    session: Session = Depends(get_db),
) -> BacktestResponse:
    settings = get_settings()
    instrument = session.scalar(
        select(Instrument).where(Instrument.symbol == symbol)
    )
    if instrument is None:
        raise HTTPException(status_code=404, detail="Instrument not found")
    report = backtest(_load_bars(session, instrument.id), strategy=strategy)
    trades = int(report["trades"])
    profit_factor = float(report["profit_factor"])
    expectancy = float(report["expectancy"])
    max_drawdown = float(report["max_drawdown"])
    gate_reasons: list[str] = []
    if trades < 200:
        gate_reasons.append(f"交易樣本 {trades}/200")
    if profit_factor < 1.2:
        gate_reasons.append(f"Profit Factor {profit_factor:.2f} < 1.20")
    if expectancy <= 0:
        gate_reasons.append("扣除成本後期望值未大於 0")
    if max_drawdown < -0.25:
        gate_reasons.append(f"最大回撤 {max_drawdown:.1%} 超過 25%")
    return BacktestResponse(
        symbol=symbol,
        strategy=strategy,
        strategy_version=settings.strategy_version,
        trades=trades,
        win_rate=float(report["win_rate"]),
        profit_factor=None if profit_factor == float("inf") else profit_factor,
        expectancy=expectancy,
        total_return=float(report["total_return"]),
        max_drawdown=max_drawdown,
        sharpe_like=float(report["sharpe_like"]),
        gate_passed=not gate_reasons,
        gate_reasons=gate_reasons,
    )


@router.post("/jobs/fetch-latest", response_model=JobResponse)
def fetch_latest(session: Session = Depends(get_db)) -> JobResponse:
    rows = OfficialSnapshotClient().fetch_all()
    records = upsert_market_rows(session, rows)
    return JobResponse(
        job="fetch-latest",
        records=records,
        message="Official TWSE/TPEx snapshot imported",
    )


@router.post("/jobs/scan", response_model=JobResponse)
def scan(session: Session = Depends(get_db)) -> JobResponse:
    records = run_scan(session)
    return JobResponse(job="scan", records=records, message="Scan completed")


@router.post("/jobs/seed-demo", response_model=JobResponse)
def demo(session: Session = Depends(get_db)) -> JobResponse:
    imported = seed_demo(session)
    signals_count = run_scan(session)
    return JobResponse(
        job="seed-demo",
        records=imported,
        message=f"Demo data imported; {signals_count} signals generated",
    )
