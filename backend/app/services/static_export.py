from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.domain import Bar
from app.domain import IntradayBar
from app.services.backtest import backtest
from app.services.history_store import DataQualityError, read_snapshot
from app.services.intraday_data import YahooIntradayClient
from app.services.recommendations import (
    RECOMMENDATION_VERSION,
    build_recommendations,
)
from app.services.strategies import intraday_ma60_touch_signal, scan_bars


def _json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_json(root: Path, relative: str, payload: Any) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    content = _json_bytes(payload)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _percentile_ranks(returns: dict[str, float]) -> dict[str, float]:
    ordered = sorted(returns.items(), key=lambda item: item[1])
    denominator = max(1, len(ordered) - 1)
    return {symbol: rank / denominator for rank, (symbol, _) in enumerate(ordered)}


def _serialize_backtest(
    symbol: str,
    strategy: str,
    bars: list[Bar],
    percentile: float,
) -> dict[str, Any]:
    report = backtest(bars, percentile, strategy=strategy)
    profit_factor = float(report["profit_factor"])
    trades = int(report["trades"])
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
    return {
        "symbol": symbol,
        "strategy": strategy,
        "strategy_version": get_settings().strategy_version,
        "trades": trades,
        "win_rate": float(report["win_rate"]),
        "profit_factor": None if profit_factor == float("inf") else profit_factor,
        "expectancy": expectancy,
        "total_return": float(report["total_return"]),
        "max_drawdown": max_drawdown,
        "sharpe_like": float(report["sharpe_like"]),
        "gate_passed": not gate_reasons,
        "gate_reasons": gate_reasons,
    }


def export_static_data(
    raw_dir: Path,
    output_dir: Path,
    *,
    reference_date: date | None = None,
    max_age_days: int = 14,
    intraday_fetch: bool = True,
    intraday_provider: Any | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    snapshots = sorted(raw_dir.glob("*.json.gz"))
    if len(snapshots) < 65:
        raise DataQualityError(
            f"At least 65 trading-day snapshots are required; found {len(snapshots)}"
        )

    universe: dict[str, list[Bar]] = defaultdict(list)
    instruments: dict[str, dict[str, str]] = {}
    latest_payload: dict[str, Any] | None = None
    for path in snapshots:
        payload, rows = read_snapshot(path)
        latest_payload = payload
        for row in rows:
            instruments[row.symbol] = {
                "symbol": row.symbol,
                "name": row.name,
                "market": row.market,
            }
            universe[row.symbol].append(
                Bar(
                    date=row.trade_date,
                    open=float(row.open),
                    high=float(row.high),
                    low=float(row.low),
                    close=float(row.close),
                    volume=row.volume,
                    turnover=float(row.turnover),
                )
            )
    if latest_payload is None:
        raise DataQualityError("No snapshots available")
    scan_date = date.fromisoformat(str(latest_payload["trade_date"]))
    reference_date = reference_date or datetime.now(
        ZoneInfo(settings.timezone)
    ).date()
    age_days = (reference_date - scan_date).days
    if age_days < 0 or age_days > max_age_days:
        raise DataQualityError(
            f"Latest snapshot is stale or in the future: "
            f"data={scan_date}, reference={reference_date}, age={age_days}"
        )
    eligible = {
        symbol: bars
        for symbol, bars in universe.items()
        if len(bars) >= 65
        and bars[-1].date == scan_date
        and median(bar.turnover for bar in bars[-20:]) >= 30_000_000
    }
    returns = {
        symbol: (bars[-1].close / bars[-61].close) - 1
        for symbol, bars in eligible.items()
    }
    ranks = _percentile_ranks(returns)

    signals: list[dict[str, Any]] = []
    candidate_symbols: set[str] = set()
    candidate_strategies: dict[str, set[str]] = defaultdict(set)

    def append_signal(symbol: str, result: Any) -> None:
        candidate_symbols.add(symbol)
        candidate_strategies[symbol].add(result.strategy)
        metrics = {
            **result.metrics,
            "risk_eligible": result.executable,
            "strategy_approved": settings.strategy_approved,
        }
        signals.append(
            {
                "id": 0,
                **instruments[symbol],
                "signal_date": result.signal_date.isoformat(),
                "strategy": result.strategy,
                "strategy_version": settings.strategy_version,
                "level": result.level.value,
                "score": result.score,
                "close": result.close,
                "entry_price": result.entry_price,
                "entry_zone_low": result.entry_zone_low,
                "entry_zone_high": result.entry_zone_high,
                "trigger_price": result.trigger_price,
                "stop_price": result.stop_price,
                "risk_percent": result.risk_percent,
                "timing_status": result.timing_status,
                "timing_note": result.timing_note,
                "overheated": result.overheated,
                "executable": result.executable and settings.strategy_approved,
                "validation_status": (
                    "APPROVED"
                    if result.executable and settings.strategy_approved
                    else "RESEARCH"
                ),
                "reasons": result.reasons,
                "metrics": metrics,
            }
        )

    for symbol, bars in eligible.items():
        for result in scan_bars(bars, ranks[symbol]):
            append_signal(symbol, result)

    intraday_attempted = 0
    intraday_available = 0
    intraday_errors = 0
    if intraday_fetch:
        provider = intraday_provider or YahooIntradayClient().fetch_60m
        intraday_symbols = sorted(
            eligible,
            key=lambda symbol: median(bar.turnover for bar in eligible[symbol][-20:]),
            reverse=True,
        )[: settings.intraday_scan_limit]
        for symbol in intraday_symbols:
            intraday_attempted += 1
            try:
                intraday_bars: list[IntradayBar] = provider(
                    symbol, instruments[symbol]["market"]
                )
            except Exception:
                intraday_errors += 1
                continue
            if not intraday_bars:
                continue
            intraday_available += 1
            result = intraday_ma60_touch_signal(eligible[symbol], intraday_bars)
            if result is not None:
                append_signal(symbol, result)
    signals.sort(key=lambda item: (-int(item["score"]), str(item["symbol"])))
    for index, signal in enumerate(signals, start=1):
        signal["id"] = index
    recommendations = {
        "as_of": scan_date.isoformat(),
        "ranking_version": RECOMMENDATION_VERSION,
        **build_recommendations(signals),
    }

    counts = {
        level: sum(signal["level"] == level for signal in signals)
        for level in ("WATCH", "TRIAL", "CONFIRMED")
    }
    summary = {
        "as_of": scan_date.isoformat(),
        "total_signals": len(signals),
        "watch": counts["WATCH"],
        "trial": counts["TRIAL"],
        "confirmed": counts["CONFIRMED"],
        "instruments": len(eligible),
        "strategy_version": settings.strategy_version,
        "strategy_approved": settings.strategy_approved,
        "intraday_scanned": intraday_attempted,
        "intraday_available": intraday_available,
        "intraday_errors": intraday_errors,
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".static-data-", dir=output_dir.parent))
    checksums: dict[str, str] = {}
    try:
        checksums["summary.json"] = _write_json(staging, "summary.json", summary)
        checksums["signals.json"] = _write_json(staging, "signals.json", signals)
        checksums["recommendations.json"] = _write_json(
            staging,
            "recommendations.json",
            recommendations,
        )
        for symbol in sorted(candidate_symbols):
            bars = eligible[symbol]
            bar_payload = [
                {
                    "trade_date": bar.date.isoformat(),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "turnover": bar.turnover,
                }
                for bar in bars
            ]
            relative_bar_path = f"bars/{symbol}.json"
            checksums[relative_bar_path] = _write_json(
                staging, relative_bar_path, bar_payload
            )
            for strategy in sorted(candidate_strategies[symbol]):
                backtest_payload = _serialize_backtest(
                    symbol,
                    strategy,
                    bars,
                    ranks[symbol],
                )
                relative_backtest_path = f"backtests/{symbol}/{strategy}.json"
                checksums[relative_backtest_path] = _write_json(
                    staging, relative_backtest_path, backtest_payload
                )
        manifest = {
            "schema_version": 1,
            "data_date": scan_date.isoformat(),
            "generated_at": latest_payload["ingested_at"],
            "strategy_version": settings.strategy_version,
            "strategy_approved": settings.strategy_approved,
            "trading_days": len(snapshots),
            "source_counts": latest_payload["counts"],
            "candidate_symbols": sorted(candidate_symbols),
            "checksums": checksums,
        }
        _write_json(staging, "manifest.json", manifest)
        backup = output_dir.with_name(f"{output_dir.name}.backup")
        if backup.exists():
            shutil.rmtree(backup)
        if output_dir.exists():
            output_dir.replace(backup)
        try:
            staging.replace(output_dir)
        except PermissionError:
            # Windows can reject replacing a directory even when the target no
            # longer exists. Copying the completed staging tree preserves the
            # validated payload while the backup remains available.
            shutil.copytree(staging, output_dir)
            shutil.rmtree(staging)
        if backup.exists():
            shutil.rmtree(backup)
        return manifest
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        backup = output_dir.with_name(f"{output_dir.name}.backup")
        if not output_dir.exists() and backup.exists():
            backup.replace(output_dir)
        raise
