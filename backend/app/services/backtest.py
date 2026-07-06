from dataclasses import dataclass
from statistics import mean, pstdev

from app.domain import Bar, SignalLevel
from app.services.indicators import sma
from app.services.strategies import scan_bars


@dataclass(frozen=True)
class BacktestConfig:
    commission_rate: float = 0.001425
    sell_tax_rate: float = 0.003
    slippage_rate: float = 0.001
    max_holding_days: int = 20


def backtest(
    bars: list[Bar],
    relative_strength_percentile: float = 0.9,
    config: BacktestConfig | None = None,
    strategy: str | None = None,
) -> dict[str, float | int]:
    config = config or BacktestConfig()
    trades: list[float] = []
    equity = 1.0
    equity_curve = [equity]
    position: dict[str, float | int] | None = None
    closes = [bar.close for bar in bars]
    ma20s = sma(closes, 20)

    for index in range(65, len(bars) - 1):
        current = bars[index]
        if position is None:
            candidates = scan_bars(
                bars[: index + 1], relative_strength_percentile
            )
            if strategy is not None:
                candidates = [
                    item for item in candidates if item.strategy == strategy
                ]
            actionable = [
                item
                for item in candidates
                if item.level in {SignalLevel.TRIAL, SignalLevel.CONFIRMED}
                and item.executable
            ]
            if actionable:
                selected = max(actionable, key=lambda item: item.score)
                next_open = bars[index + 1].open
                entry = next_open * (1 + config.slippage_rate)
                position = {
                    "entry": entry,
                    "stop": float(selected.stop_price or 0),
                    "entry_index": index + 1,
                }
        else:
            entry = float(position["entry"])
            stop = float(position["stop"])
            entry_index = int(position["entry_index"])
            holding_days = index - entry_index
            ma20 = float(ma20s[index] or 0)
            exit_price: float | None = None
            if current.low <= stop:
                exit_price = stop * (1 - config.slippage_rate)
            elif current.close < ma20 or holding_days >= config.max_holding_days:
                exit_price = bars[index + 1].open * (1 - config.slippage_rate)
            if exit_price is not None:
                gross = (exit_price / entry) - 1
                costs = (
                    config.commission_rate * 2
                    + config.sell_tax_rate
                )
                net = gross - costs
                trades.append(net)
                equity *= 1 + net
                equity_curve.append(equity)
                position = None

    if not trades:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "sharpe_like": 0.0,
        }
    gains = sum(item for item in trades if item > 0)
    losses = abs(sum(item for item in trades if item < 0))
    peaks: list[float] = []
    running_peak = 0.0
    drawdowns: list[float] = []
    for value in equity_curve:
        running_peak = max(running_peak, value)
        peaks.append(running_peak)
        drawdowns.append((value / running_peak) - 1 if running_peak else 0)
    deviation = pstdev(trades) if len(trades) > 1 else 0.0
    return {
        "trades": len(trades),
        "win_rate": sum(item > 0 for item in trades) / len(trades),
        "profit_factor": gains / losses if losses else float("inf"),
        "expectancy": mean(trades),
        "total_return": equity - 1,
        "max_drawdown": min(drawdowns),
        "sharpe_like": mean(trades) / deviation if deviation else 0.0,
    }
