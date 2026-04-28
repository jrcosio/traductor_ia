from __future__ import annotations


def percentile(values: list[float] | tuple[float, ...], percent: float) -> float | None:
    if not values:
        return None
    if percent < 0 or percent > 100:
        raise ValueError("percent debe estar entre 0 y 100")

    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (len(ordered) - 1) * (percent / 100)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * weight)


def latency_summary(values: list[float] | tuple[float, ...]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "p50_ms": percentile(values, 50),
        "p95_ms": percentile(values, 95),
        "p99_ms": percentile(values, 99),
    }
