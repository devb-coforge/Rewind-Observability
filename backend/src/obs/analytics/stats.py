from statistics import median


def median_or_none(values: list[float]) -> float | None:
    return float(median(values)) if values else None
