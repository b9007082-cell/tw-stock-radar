from collections.abc import Sequence

from app.domain import Bar


def sma(values: Sequence[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if period <= 0:
        raise ValueError("period must be positive")
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        if index >= period - 1:
            result[index] = running / period
    return result


def atr(bars: Sequence[Bar], period: int = 14) -> list[float | None]:
    ranges: list[float] = []
    for index, bar in enumerate(bars):
        previous_close = bars[index - 1].close if index else bar.close
        ranges.append(
            max(
                bar.high - bar.low,
                abs(bar.high - previous_close),
                abs(bar.low - previous_close),
            )
        )
    return sma(ranges, period)


def percent_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return (current / previous) - 1.0


def confirmed_swings(
    bars: Sequence[Bar], radius: int = 2
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    peaks: list[tuple[int, float]] = []
    troughs: list[tuple[int, float]] = []
    for index in range(radius, len(bars) - radius):
        neighborhood = bars[index - radius : index + radius + 1]
        high = bars[index].high
        low = bars[index].low
        if high == max(item.high for item in neighborhood):
            peaks.append((index, high))
        if low == min(item.low for item in neighborhood):
            troughs.append((index, low))
    return peaks, troughs

