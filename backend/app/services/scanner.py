import json
from datetime import date
from decimal import Decimal
from statistics import median

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain import Bar
from app.models import DailyPrice, Instrument, Signal
from app.services.strategies import scan_bars


def _load_bars(session: Session, instrument_id: int) -> list[Bar]:
    rows = session.scalars(
        select(DailyPrice)
        .where(DailyPrice.instrument_id == instrument_id)
        .order_by(DailyPrice.trade_date)
    ).all()
    return [
        Bar(
            date=row.trade_date,
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=row.volume,
            turnover=float(row.turnover),
        )
        for row in rows
    ]


def _percentile_ranks(returns: dict[int, float]) -> dict[int, float]:
    ordered = sorted(returns.items(), key=lambda item: item[1])
    denominator = max(1, len(ordered) - 1)
    return {
        instrument_id: rank / denominator
        for rank, (instrument_id, _) in enumerate(ordered)
    }


def run_scan(session: Session, as_of: date | None = None) -> int:
    settings = get_settings()
    instruments = session.scalars(
        select(Instrument).where(Instrument.is_active.is_(True))
    ).all()
    bars_by_id = {}
    for instrument in instruments:
        bars = _load_bars(session, instrument.id)
        if as_of is not None:
            bars = [bar for bar in bars if bar.date <= as_of]
        bars_by_id[instrument.id] = bars
    bars_by_id = {
        instrument_id: bars
        for instrument_id, bars in bars_by_id.items()
        if len(bars) >= 65
        and median(bar.turnover for bar in bars[-20:]) >= 30_000_000
    }
    if not bars_by_id:
        return 0
    scan_date = as_of or max(bars[-1].date for bars in bars_by_id.values())
    bars_by_id = {
        instrument_id: bars
        for instrument_id, bars in bars_by_id.items()
        if bars[-1].date == scan_date
    }
    returns = {
        instrument_id: (bars[-1].close / bars[-61].close) - 1
        for instrument_id, bars in bars_by_id.items()
    }
    ranks = _percentile_ranks(returns)
    session.execute(
        delete(Signal).where(
            Signal.signal_date == scan_date,
            Signal.strategy_version == settings.strategy_version,
        )
    )
    count = 0
    for instrument_id, bars in bars_by_id.items():
        eligible = [bar for bar in bars if bar.date <= scan_date]
        for result in scan_bars(eligible, ranks[instrument_id]):
            session.add(
                Signal(
                    instrument_id=instrument_id,
                    signal_date=result.signal_date,
                    strategy=result.strategy,
                    strategy_version=settings.strategy_version,
                    level=result.level.value,
                    score=result.score,
                    close=Decimal(str(result.close)),
                    entry_price=(
                        Decimal(str(result.entry_price))
                        if result.entry_price is not None
                        else None
                    ),
                    stop_price=(
                        Decimal(str(result.stop_price))
                        if result.stop_price is not None
                        else None
                    ),
                    risk_percent=(
                        Decimal(str(result.risk_percent))
                        if result.risk_percent is not None
                        else None
                    ),
                    executable=result.executable and settings.strategy_approved,
                    reasons_json=json.dumps(result.reasons, ensure_ascii=False),
                    metrics_json=json.dumps(
                        {
                            **result.metrics,
                            "_entry_zone_low": result.entry_zone_low,
                            "_entry_zone_high": result.entry_zone_high,
                            "_trigger_price": result.trigger_price,
                            "_timing_status": result.timing_status,
                            "_timing_note": result.timing_note,
                            "_overheated": result.overheated,
                            "risk_eligible": result.executable,
                            "strategy_approved": settings.strategy_approved,
                        },
                        ensure_ascii=False,
                    ),
                )
            )
            count += 1
    session.commit()
    return count
