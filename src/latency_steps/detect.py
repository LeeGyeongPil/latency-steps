"""Step detection on percentile series. Standard library only.

The series is analysed on a log scale, so "2x slower" is the same size of
change at 50 ms and at 5 s. A robust binary segmentation looks for the split
whose medians differ most relative to the noise (median absolute deviation),
and recurses on both halves. Medians make a one-bucket spike harmless, which
is exactly how a *step* (sustained) is told apart from a *spike* (brief).

Instead of a penalty value, two numbers you can reason about decide what is
reported: ``min_run`` (how many buckets the new level must last) and
``min_ratio`` (how much slower it must be).
"""

from __future__ import annotations

import math
from .model import ChangePoint, KeySeries, Observation

DEFAULT_THRESHOLD = 6.0
SPIKE_Z = 5.0
NOISE_FLOOR = 0.03  # log units (~3%): never treat smaller wiggles as signal
COARSE_AFTER = 500  # series longer than this are scanned coarsely first
MAX_CHANGE_POINTS = 50


def _median(sorted_values: list[float]) -> float:
    n = len(sorted_values)
    mid = n // 2
    if n % 2:
        return sorted_values[mid]
    return 0.5 * (sorted_values[mid - 1] + sorted_values[mid])


def _med(values: list[float]) -> float:
    return _median(sorted(values))


def _mad(values: list[float], center: float) -> float:
    return _med([abs(v - center) for v in values]) * 1.4826


def _noise_floor(y: list[float]) -> float:
    """Robust noise scale of a whole series from successive differences."""
    if len(y) < 3:
        return NOISE_FLOOR
    diffs = [abs(b - a) for a, b in zip(y, y[1:])]
    return max(NOISE_FLOOR, 0.7 * _med(diffs) * 1.4826 / math.sqrt(2))


def _split_stat(y: list[float], k: int, floor: float) -> float:
    left, right = y[:k], y[k:]
    ml, mr = _med(left), _med(right)
    pooled = _med([abs(v - ml) for v in left] + [abs(v - mr) for v in right]) * 1.4826
    scale = max(pooled, floor)
    return (mr - ml) / scale * math.sqrt(len(left) * len(right) / len(y))


def _best_split(y: list[float], min_size: int, floor: float) -> tuple[float, int]:
    """Return (signed statistic, split index) of the strongest split, (0, -1) if none."""
    n = len(y)
    candidates = range(min_size, n - min_size + 1)
    if n > COARSE_AFTER:
        stride = max(1, n // 200)
        coarse = list(range(min_size, n - min_size + 1, stride))
        best = max(coarse, key=lambda k: abs(_split_stat(y, k, floor)))
        candidates = range(max(min_size, best - stride), min(n - min_size, best + stride) + 1)
    best_k, best_stat = -1, 0.0
    for k in candidates:
        stat = _split_stat(y, k, floor)
        if abs(stat) > abs(best_stat):
            best_k, best_stat = k, stat
    return best_stat, best_k


def _refine(y: list[float], k: int, min_size: int, radius: int = 3) -> int:
    """Move a split to the nearby index with the smallest total absolute deviation.

    The medians barely change when one boundary bucket moves across the split,
    so the strongest-statistic split can be a bucket or two off the real edge.
    """
    n = len(y)

    def cost(j: int) -> float:
        left, right = y[:j], y[j:]
        ml, mr = _med(left), _med(right)
        return sum(abs(v - ml) for v in left) + sum(abs(v - mr) for v in right)

    options = range(max(min_size, k - radius), min(n - min_size, k + radius) + 1)
    return min(options, key=cost)


def binary_segmentation(
    y: list[float], min_size: int, threshold: float = DEFAULT_THRESHOLD
) -> list[tuple[int, float]]:
    """Return sorted ``(split index, signed statistic)`` pairs for a series ``y``."""
    floor = _noise_floor(y)
    found: list[tuple[int, float]] = []
    stack = [(0, len(y))]
    while stack and len(found) < MAX_CHANGE_POINTS:
        lo, hi = stack.pop()
        if hi - lo < 2 * min_size:
            continue
        stat, k = _best_split(y[lo:hi], min_size, floor)
        if k < 0 or abs(stat) < threshold:
            continue
        k = _refine(y[lo:hi], k, min_size)
        found.append((lo + k, stat))
        stack.append((lo, lo + k))
        stack.append((lo + k, hi))
    return sorted(found)


def _merge(
    per_metric: dict[str, list[tuple[int, float]]], window: int
) -> list[tuple[int, float, str]]:
    """Merge change points of the p50 and p90 series that sit within ``window`` buckets."""
    flat = sorted(
        ((idx, stat, metric) for metric, cps in per_metric.items() for idx, stat in cps),
        key=lambda t: t[0],
    )
    groups: list[list[tuple[int, float, str]]] = []
    for item in flat:
        if groups and item[0] - groups[-1][-1][0] <= window and (item[1] > 0) == (groups[-1][-1][1] > 0):
            groups[-1].append(item)
        else:
            groups.append([item])
    # The strongest member represents the group.
    return [max(g, key=lambda t: abs(t[1])) for g in groups]


def _persistent(
    merged: list[tuple[int, float, str]], logs: dict[str, list[float]], n: int, min_run: int
) -> list[tuple[int, float, str]]:
    """Drop split points where either side has fewer than ``min_run`` buckets at its own level.

    A split next to a brief blip can look like a step because the segment must
    hold ``min_run`` points; this checks the points really sit at that level.
    """
    current = list(merged)
    while True:
        edges = [0, *[c[0] for c in current], n]
        bad = None
        for i, (idx, _, metric) in enumerate(current):
            y = logs[metric]
            before, after = y[edges[i]:idx], y[idx:edges[i + 2]]
            mb, ma = _med(before), _med(after)
            near_before = sum(abs(v - mb) < abs(v - ma) for v in before)
            near_after = sum(abs(v - ma) < abs(v - mb) for v in after)
            if min(near_before, near_after) < min_run:
                bad = i
                break
        if bad is None:
            return current
        del current[bad]


def _segments(boundaries: list[int], n: int) -> list[tuple[int, int]]:
    edges = [0, *boundaries, n]
    return list(zip(edges[:-1], edges[1:]))


def detect(
    series: KeySeries,
    *,
    min_run: int = 3,
    min_ratio: float = 1.2,
    metric: str = "both",
    threshold: float = DEFAULT_THRESHOLD,
) -> tuple[list[ChangePoint], list[Observation]]:
    """Find sustained steps and brief deviations in one key's series.

    Returns ``(steps, observations)``. A step is reported only when the new
    level lasts at least ``min_run`` buckets and p50 or p90 changed by at least
    ``min_ratio`` (up). Faster steps and brief or trailing deviations come back
    as observations.
    """
    pts = series.points
    n = len(pts)
    if n < 2 * min_run:
        return [], []
    metrics = ("p50", "p90") if metric == "both" else (metric,)
    logs = {m: [math.log(max(getattr(p, m), 1e-9)) for p in pts] for m in metrics}

    per_metric = {m: binary_segmentation(logs[m], min_run, threshold) for m in metrics}
    merged = _persistent(_merge(per_metric, min_run), logs, n, min_run)
    boundaries = [idx for idx, _, _ in merged]
    segs = _segments(boundaries, n)

    steps: list[ChangePoint] = []
    observations: list[Observation] = []
    for i, (idx, stat, _) in enumerate(merged):
        (b_lo, b_hi), (a_lo, a_hi) = segs[i], segs[i + 1]
        ratios: dict[str, float] = {}
        levels: dict[str, tuple[float, float]] = {}
        for m in ("p50", "p90"):
            ylog = [math.log(max(getattr(p, m), 1e-9)) for p in pts]
            before = math.exp(_med(ylog[b_lo:b_hi]))
            after = math.exp(_med(ylog[a_lo:a_hi]))
            levels[m] = (before, after)
            ratios[m] = after / before
        up = stat > 0
        pool = metrics if metric != "both" else ("p50", "p90")
        pick = max(pool, key=lambda m: ratios[m]) if up else min(pool, key=lambda m: ratios[m])
        ratio = ratios[pick]
        at = pts[idx].bucket
        if up and ratio >= min_ratio:
            steps.append(
                ChangePoint(
                    key=series.key, index=idx, at=at, direction="up", metric=pick,
                    score=round(abs(stat), 2),
                    p50_before=levels["p50"][0], p50_after=levels["p50"][1],
                    p90_before=levels["p90"][0], p90_after=levels["p90"][1],
                    ratio=ratio, run_buckets=a_hi - a_lo,
                    before_start=pts[b_lo].bucket,
                    after_end=pts[a_hi].bucket if a_hi < n else None,
                )
            )
        elif not up and ratio <= 1 / min_ratio:
            observations.append(
                Observation(series.key, "faster", at, at, pick, ratio)
            )

    observations.extend(_spikes(series, logs, segs, min_run, min_ratio))
    observations.sort(key=lambda o: (o.at, o.kind))
    return steps, observations


def _spikes(
    series: KeySeries,
    logs: dict[str, list[float]],
    segs: list[tuple[int, int]],
    min_run: int,
    min_ratio: float,
) -> list[Observation]:
    """Brief deviations (fewer than ``min_run`` buckets) from the level of their segment."""
    pts = series.points
    n = len(pts)
    floor = _noise_floor(next(iter(logs.values())))
    flagged: dict[int, tuple[str, float]] = {}
    for m, y in logs.items():
        for lo, hi in segs:
            if hi - lo < 5:
                continue
            seg = y[lo:hi]
            center = _med(seg)
            scale = max(_mad(seg, center), floor)
            for j in range(lo, hi):
                dev = y[j] - center
                if abs(dev) / scale > SPIKE_Z and abs(dev) >= math.log(min_ratio):
                    prev = flagged.get(j)
                    if prev is None or abs(dev) > abs(math.log(prev[1])):
                        flagged[j] = (m, math.exp(dev))
    out: list[Observation] = []
    j = 0
    order = sorted(flagged)
    while j < len(order):
        start = order[j]
        end = start
        sign = flagged[start][1] > 1
        while j + 1 < len(order) and order[j + 1] == end + 1 and (flagged[order[j + 1]][1] > 1) == sign:
            j += 1
            end = order[j]
        j += 1
        length = end - start + 1
        if not sign:
            continue  # brief speed-ups are not interesting
        if end == n - 1:
            kind = "tail"
        elif length < min_run:
            kind = "spike"
        else:
            continue
        top = max(range(start, end + 1), key=lambda t: flagged[t][1])
        out.append(Observation(series.key, kind, pts[start].bucket, pts[end].bucket, flagged[top][0], flagged[top][1]))
    return out


def detect_all(
    all_series: list[KeySeries], **kwargs: object
) -> tuple[list[ChangePoint], list[Observation]]:
    steps: list[ChangePoint] = []
    observations: list[Observation] = []
    for s in all_series:
        st, ob = detect(s, **kwargs)  # type: ignore[arg-type]
        steps.extend(st)
        observations.extend(ob)
    return steps, observations


__all__ = ["binary_segmentation", "detect", "detect_all"]
