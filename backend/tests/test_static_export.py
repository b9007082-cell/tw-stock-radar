import json
from datetime import date, timedelta
from decimal import Decimal

from app.services.history_store import write_snapshot
from app.services.market_data import MarketRow
from app.services.static_export import export_static_data


def test_static_export_produces_deterministic_contract(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    output_dir = tmp_path / "public" / "data"
    start = date(2026, 1, 1)
    trading_day = start
    written = 0
    while written < 70:
        if trading_day.weekday() < 5:
            rows = []
            for offset, (symbol, name, market) in enumerate(
                [
                    ("2330", "台積電", "TWSE"),
                    ("6488", "環球晶", "TPEX"),
                    ("3017", "奇鋐", "TWSE"),
                ]
            ):
                close = Decimal("100") + Decimal(written) + Decimal(offset)
                rows.append(
                    MarketRow(
                        symbol=symbol,
                        name=name,
                        market=market,
                        trade_date=trading_day,
                        open=close - Decimal("1"),
                        high=close + Decimal("1"),
                        low=close - Decimal("2"),
                        close=close,
                        volume=1_000_000,
                        turnover=Decimal("50000000"),
                        source="TEST",
                    )
                )
            write_snapshot(
                raw_dir,
                trading_day,
                rows,
                ingested_at="2026-04-30T12:00:00+00:00",
            )
            written += 1
        trading_day += timedelta(days=1)

    latest_date = trading_day - timedelta(days=1)
    while latest_date.weekday() >= 5:
        latest_date -= timedelta(days=1)
    first = export_static_data(
        raw_dir,
        output_dir,
        reference_date=latest_date,
        intraday_fetch=False,
        valuation_fetch=False,
    )
    first_manifest_bytes = (output_dir / "manifest.json").read_bytes()
    second = export_static_data(
        raw_dir,
        output_dir,
        reference_date=latest_date,
        intraday_fetch=False,
        valuation_fetch=False,
    )

    summary = json.loads((output_dir / "summary.json").read_text("utf-8"))
    signals = json.loads((output_dir / "signals.json").read_text("utf-8"))
    recommendations = json.loads(
        (output_dir / "recommendations.json").read_text("utf-8")
    )
    assert first == second
    assert (output_dir / "manifest.json").read_bytes() == first_manifest_bytes
    assert first["trading_days"] == 70
    assert summary["instruments"] == 3
    assert summary["intraday_scanned"] == 0
    assert summary["valuation_available"] == 0
    assert isinstance(signals, list)
    assert recommendations["as_of"] == latest_date.isoformat()
    assert recommendations["ranking_version"] == "2026.08.r10"
    assert "recommendations.json" in first["checksums"]
    assert isinstance(recommendations["pullback_resume"], list)
    assert isinstance(recommendations["consolidation_breakout"], list)
    assert isinstance(recommendations["bottom_reversal"], list)
    assert isinstance(recommendations["bollinger_squeeze"], list)
    assert isinstance(recommendations["intraday_ma60_touch"], list)
    assert isinstance(recommendations["low_price_high_yield"], list)
    assert isinstance(recommendations["lorentzian_ml"], list)
    for signal in signals:
        backtest_path = (
            output_dir
            / "backtests"
            / signal["symbol"]
            / f"{signal['strategy']}.json"
        )
        report = json.loads(backtest_path.read_text("utf-8"))
        assert report["strategy"] == signal["strategy"]
