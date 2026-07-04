from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    market: Mapped[str] = mapped_column(String(8), index=True)
    security_type: Mapped[str] = mapped_column(String(24), default="COMMON_STOCK")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    prices: Mapped[list["DailyPrice"]] = relationship(
        back_populates="instrument", cascade="all, delete-orphan"
    )
    signals: Mapped[list["Signal"]] = relationship(
        back_populates="instrument", cascade="all, delete-orphan"
    )


class DailyPrice(Base):
    __tablename__ = "daily_prices"
    __table_args__ = (
        UniqueConstraint("instrument_id", "trade_date", name="uq_price_instrument_date"),
        Index("ix_price_date_instrument", "trade_date", "instrument_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    high: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    low: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    close: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    volume: Mapped[int] = mapped_column(Integer)
    turnover: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=0)
    source: Mapped[str] = mapped_column(String(24))
    is_adjusted: Mapped[bool] = mapped_column(Boolean, default=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    instrument: Mapped[Instrument] = relationship(back_populates="prices")


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "signal_date",
            "strategy",
            "strategy_version",
            name="uq_signal_snapshot",
        ),
        Index("ix_signal_date_level", "signal_date", "level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    signal_date: Mapped[date] = mapped_column(Date, index=True)
    strategy: Mapped[str] = mapped_column(String(40))
    strategy_version: Mapped[str] = mapped_column(String(24))
    level: Mapped[str] = mapped_column(String(16), index=True)
    score: Mapped[int] = mapped_column(Integer)
    close: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    risk_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    executable: Mapped[bool] = mapped_column(Boolean, default=False)
    reasons_json: Mapped[str] = mapped_column(Text)
    metrics_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    instrument: Mapped[Instrument] = relationship(back_populates="signals")


class JobRun(Base):
    __tablename__ = "job_runs"
    __table_args__ = (
        UniqueConstraint("job_name", "run_date", name="uq_job_name_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(40))
    run_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16))
    records: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CorporateAction(Base):
    __tablename__ = "corporate_actions"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "effective_date", "action_type", name="uq_corporate_action"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    effective_date: Mapped[date] = mapped_column(Date, index=True)
    action_type: Mapped[str] = mapped_column(String(24))
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    source: Mapped[str] = mapped_column(String(40))
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MarketFlag(Base):
    __tablename__ = "market_flags"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "flag_date", "flag_type", name="uq_market_flag"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    flag_date: Mapped[date] = mapped_column(Date, index=True)
    flag_type: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(Text, default="")
