"""Deterministic statistics helpers using only the Python standard library.

No numpy/scipy/pandas dependency, so the project virtual environment (which has
numpy but not scipy) can run every analysis and test without extra installs.
"""

from __future__ import annotations

import math
from statistics import NormalDist, mean, stdev
from typing import Iterable, Sequence

DEFAULT_CONFIDENCE = 0.95

# NIST/SEMATECH e-Handbook 1.3.6.7.2, 0.975 quantile for df 3 through 30.
_T_975_SMALL_SAMPLE = (
    3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179,
    2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074,
    2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042,
)


def t_ppf(p: float, df: float) -> float:
    """Use closed forms and standard small-sample critical values where available."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    if df == 1:
        return math.tan(math.pi * (p - 0.5))
    if df == 2:
        centered = 2.0 * p - 1.0
        return centered / math.sqrt(2.0 * p * (1.0 - p))
    if p in (0.025, 0.975) and 3 <= df <= 30 and df == int(df):
        return math.copysign(_T_975_SMALL_SAMPLE[int(df) - 3], p - 0.5)

    z = NormalDist().inv_cdf(p)
    if df <= 0:
        return z
    g1 = (z**3 + z) / (4.0 * df)
    g2 = (5.0 * z**5 + 16.0 * z**3 + 3.0 * z) / (96.0 * df * df)
    g3 = (3.0 * z**7 + 19.0 * z**5 + 17.0 * z**3 - 15.0 * z) / (384.0 * df**3)
    return z + g1 + g2 + g3


def finite(values: Iterable[float | None]) -> list[float]:
    out: list[float] = []
    for value in values:
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            out.append(number)
    return out


def describe(values: Iterable[float | None]) -> dict:
    data = finite(values)
    n = len(data)
    if n == 0:
        return {
            "count": 0,
            "mean": None,
            "std": None,
            "min": None,
            "max": None,
            "confidence_interval": None,
        }
    avg = mean(data)
    std = stdev(data) if n >= 2 else 0.0
    return {
        "count": n,
        "mean": avg,
        "std": std,
        "min": min(data),
        "max": max(data),
        "confidence_interval": confidence_interval(data, DEFAULT_CONFIDENCE) if n >= 2 else None,
    }


def confidence_interval(values: Sequence[float], confidence: float = DEFAULT_CONFIDENCE) -> dict | None:
    data = finite(values)
    n = len(data)
    if n < 2:
        return None
    avg = mean(data)
    sample_std = stdev(data)
    alpha = 1.0 - confidence
    t_crit = t_ppf(1.0 - alpha / 2.0, n - 1)
    margin = t_crit * sample_std / math.sqrt(n)
    if n <= 3:
        quantile_method = "closed-form t quantile"
    elif confidence == DEFAULT_CONFIDENCE and n <= 31:
        quantile_method = "NIST t critical value (rounded to 0.001)"
    else:
        quantile_method = "Cornish-Fisher approximation of the t quantile"
    return {
        "lower": avg - margin,
        "upper": avg + margin,
        "mean": avg,
        "std": sample_std,
        "count": n,
        "confidence": confidence,
        "t_critical": t_crit,
        "margin_of_error": margin,
        "method": (
            "t-interval: mean ± t(α/2, n-1) · (s/√n), sample standard deviation ddof=1; "
            f"{quantile_method}. "
            "Assumes approximately independent, identically distributed runs."
        ),
        "sufficient_sample": n >= 30,
        "note": (
            "样本量较小，置信区间宽度可能不稳定；不得据此声称统计显著。"
            if n < 30
            else "n≥30，区间估计相对稳定，但仍不构成因果显著性证明。"
        ),
    }


def safe_mean(values: Iterable[float | None]) -> float | None:
    data = finite(values)
    return mean(data) if data else None


def round_metric(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)
