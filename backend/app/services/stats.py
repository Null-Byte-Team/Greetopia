"""Small, dependency-light statistics for the experiment reports (cross-checked against scipy in the tests)."""
from __future__ import annotations

import itertools
import math

import numpy as np

EXACT_MAX_N = 16


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def mann_whitney(x: list[float], y: list[float], min_n: int = 3) -> dict:
    """Two-sided Mann-Whitney U. Exact permutation p for n1+n2 <= 16, otherwise normal approximation with tie + continuity correction.
    Effect size: rank-biserial correlation (positive => x tends to be larger). Refuses to report a p-value below min_n per group."""
    n1, n2 = len(x), len(y)
    out = {"n1": n1, "n2": n2, "u": None, "p_value": None, "rank_biserial": None, "method": None}
    if n1 == 0 or n2 == 0:
        out["note"] = "an arm has no data"
        return out
    ranks = _ranks(list(x) + list(y))
    u1 = sum(ranks[:n1]) - n1 * (n1 + 1) / 2
    out["u"] = u1
    out["rank_biserial"] = round(2 * u1 / (n1 * n2) - 1, 3)
    if n1 < min_n or n2 < min_n:
        out["note"] = f"sample too small (n={n1} vs {n2}; need >= {min_n} per arm): no p-value is reported, differences are descriptive only"
        return out
    mean_u = n1 * n2 / 2
    if n1 + n2 <= EXACT_MAX_N:
        count = total = 0
        observed = abs(u1 - mean_u)
        for combo in itertools.combinations(range(n1 + n2), n1):
            u = sum(ranks[i] for i in combo) - n1 * (n1 + 1) / 2
            total += 1
            if abs(u - mean_u) >= observed - 1e-9:
                count += 1
        out.update(p_value=round(count / total, 4), method="exact permutation")
        return out
    n = n1 + n2
    _, counts = np.unique(ranks, return_counts=True)
    tie = float(np.sum(counts ** 3 - counts))
    var = n1 * n2 / 12 * ((n + 1) - tie / (n * (n - 1)))
    if var <= 0:
        out.update(p_value=1.0, method="normal approximation")
        return out
    z = (abs(u1 - mean_u) - 0.5) / math.sqrt(var)
    out.update(p_value=round(math.erfc(z / math.sqrt(2)), 4), method="normal approximation (tie + continuity corrected)")
    return out


def bootstrap_median_diff(x: list[float], y: list[float], seed: int, n_boot: int = 5000) -> dict:
    """95% percentile bootstrap CI for median(x) - median(y). With tiny samples the interval is honestly wide."""
    if not x or not y:
        return {"available": False}
    rng = np.random.default_rng(seed)
    xs, ys = np.array(x, float), np.array(y, float)
    diffs = [float(np.median(rng.choice(xs, len(xs))) - np.median(rng.choice(ys, len(ys)))) for _ in range(n_boot)]
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {"available": True, "median_diff": round(float(np.median(xs) - np.median(ys)), 4), "ci95": [round(float(lo), 4), round(float(hi), 4)], "n_boot": n_boot, "seed": seed}
