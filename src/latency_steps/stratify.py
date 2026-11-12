"""Stratify the windows before and after a step by chosen dimensions.

For each dimension the before/after windows are cut into cells (host values,
or numeric ranges like ``1-3,4-7,8+``). The cell table is the evidence; the
verdict is a heuristic read of it:

* ``localized``  - only one or a minority of cells got slower
* ``mix_shift``  - cells are flat (or a cell is brand new) so the overall change
                   comes from a different mix of traffic (Simpson's paradox)
* ``global``     - at least 80% of comparable cells got slower
* ``inconclusive`` - none of the above, or too few samples
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import duckdb

from .errors import LatencyStepsError
from .model import (
    GLOBAL, INCONCLUSIVE, LOCALIZED, MIX_SHIFT, NOT_STRATIFIED, VERDICT_PRIORITY,
    Cell, ChangePoint, DimVerdict, Finding,
)

MAX_CATEGORIES = 20
MIN_CELL_N = 30
GLOBAL_FRACTION = 0.8
SHARE_SHIFT = 0.10
OTHER = "(other)"
MISSING = "(missing)"


@dataclass
class DimSpec:
    """A dimension to stratify by: a field name plus optional numeric bins."""

    field: str
    index: int
    bins: list[tuple[str, float, float | None]] | None = None  # (label, low, high|None)

    @property
    def name(self) -> str:
        return self.field


_BIN = re.compile(r"^(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?)|(\+))$")


def parse_dim(spec: str, index: int) -> DimSpec:
    """Parse ``host`` or ``concurrency:1-3,4-7,8+`` into a ``DimSpec``."""
    field, sep, rest = spec.partition(":")
    field = field.strip()
    if not field or '"' in field or "'" in field:
        raise LatencyStepsError("bad_by", spec=spec)
    if not sep:
        return DimSpec(field, index)
    bins: list[tuple[str, float, float | None]] = []
    for part in rest.split(","):
        label = part.strip()
        m = _BIN.match(label)
        if not m:
            raise LatencyStepsError("bad_by", spec=spec)
        low = float(m.group(1))
        high = None if m.group(3) else float(m.group(2))
        if high is not None and high < low:
            raise LatencyStepsError("bad_by", spec=spec)
        bins.append((label, low, high))
    if not bins:
        raise LatencyStepsError("bad_by", spec=spec)
    return DimSpec(field, index, bins)


def _cell_expr(dim: DimSpec, top: list[str] | None) -> str:
    col = f"d{dim.index}"
    if dim.bins is not None:
        x = f"try_cast({col} AS DOUBLE)"
        whens = []
        for label, low, high in dim.bins:
            cond = f"{x} >= {low!r}" + (f" AND {x} <= {high!r}" if high is not None else "")
            whens.append(f"WHEN {cond} THEN '{label}'")
        return f"CASE {' '.join(whens)} ELSE '{OTHER}' END"
    base = f"coalesce(nullif({col}, ''), '{MISSING}')"
    if top is None:
        return base
    quoted = ", ".join("'" + t.replace("'", "''") + "'" for t in top)
    return f"CASE WHEN {base} IN ({quoted}) THEN {base} ELSE '{OTHER}' END"


def _ratio(after: float | None, before: float | None) -> float | None:
    if after is None or before is None or before <= 0:
        return None
    return after / before


def stratify_change(
    con: duckdb.DuckDBPyConnection,
    change: ChangePoint,
    dims: list[DimSpec],
    *,
    min_ratio: float,
) -> Finding:
    """Build the per-dimension cell tables and verdicts for one step."""
    finding = Finding(change=change)
    for dim in dims:
        finding.dims.append(_stratify_dim(con, change, dim, min_ratio))
    _fold(finding)
    return finding


def _window(change: ChangePoint) -> tuple[str, list]:
    """SQL condition and parameters selecting the before+after windows of a step."""
    if change.after_end is None:
        return "key = ? AND lts >= ?", [change.key, change.before_start]
    return "key = ? AND lts >= ? AND lts < ?", [change.key, change.before_start, change.after_end]


def _stratify_dim(
    con: duckdb.DuckDBPyConnection, change: ChangePoint, dim: DimSpec, min_ratio: float
) -> DimVerdict:
    where, window = _window(change)
    top: list[str] | None = None
    if dim.bins is None:
        counts = con.execute(
            f"""
            SELECT {_cell_expr(dim, None)} AS g, count(*) FROM events
            WHERE {where} GROUP BY g ORDER BY count(*) DESC, g LIMIT {MAX_CATEGORIES + 1}
            """,
            window,
        ).fetchall()
        if len(counts) > MAX_CATEGORIES:
            top = [g for g, _ in counts[:MAX_CATEGORIES]]
    rows = con.execute(
        f"""
        SELECT {_cell_expr(dim, top)} AS g,
               count(*) FILTER (WHERE lts < ?) AS nb, count(*) FILTER (WHERE lts >= ?) AS na,
               quantile_cont(ms, 0.5) FILTER (WHERE lts < ?) AS p50b,
               quantile_cont(ms, 0.5) FILTER (WHERE lts >= ?) AS p50a,
               quantile_cont(ms, 0.9) FILTER (WHERE lts < ?) AS p90b,
               quantile_cont(ms, 0.9) FILTER (WHERE lts >= ?) AS p90a
        FROM events WHERE {where} GROUP BY g
        """,
        [change.at] * 6 + window,
    ).fetchall()
    total_b = sum(r[1] for r in rows) or 1
    total_a = sum(r[2] for r in rows) or 1
    cells: list[Cell] = []
    metric = change.metric
    for g, nb, na, p50b, p50a, p90b, p90a in rows:
        before, after = (p50b, p50a) if metric == "p50" else (p90b, p90a)
        new = nb < MIN_CELL_N <= na
        thin = (nb < MIN_CELL_N or na < MIN_CELL_N) and not new
        ratio = None if (new or thin) else _ratio(after, before)
        cells.append(
            Cell(
                value=g, n_before=nb, n_after=na, p50_before=p50b, p50_after=p50a,
                p90_before=p90b, p90_after=p90a, share_before=nb / total_b,
                share_after=na / total_a, ratio=ratio, new=new, thin=thin,
            )
        )
    if dim.bins is not None:
        order = {label: i for i, (label, _, _) in enumerate(dim.bins)}
        cells.sort(key=lambda c: order.get(c.value, len(order)))
    else:
        cells.sort(key=lambda c: (c.value == OTHER, -c.n_after, c.value))
    verdict, reason, focus = _verdict(cells, min_ratio)
    return DimVerdict(dim=dim.name, verdict=verdict, reason=reason, cells=cells, focus=focus, metric=metric)


def _verdict(cells: list[Cell], min_ratio: float) -> tuple[str, str, list[str]]:
    eligible = [c for c in cells if c.ratio is not None]
    new = [c for c in cells if c.new]
    hot = [c for c in eligible if c.ratio >= min_ratio]  # type: ignore[operator]
    flat_limit = 1 + (min_ratio - 1) / 2
    if not eligible and not new:
        return INCONCLUSIVE, "too_few_samples", []
    if eligible and len(hot) / len(eligible) >= GLOBAL_FRACTION and len(eligible) >= 2:
        return GLOBAL, "most_cells", []
    if not hot and new:
        return MIX_SHIFT, "new_cell", [c.value for c in new]
    if not hot and eligible:
        shift = max(abs(c.share_after - c.share_before) for c in cells)
        if all(c.ratio < flat_limit for c in eligible) and shift >= SHARE_SHIFT:  # type: ignore[operator]
            return MIX_SHIFT, "composition", [c.value for c in cells if abs(c.share_after - c.share_before) >= SHARE_SHIFT]
    if hot and len(hot) <= max(1, (len(eligible) - 1) // 2) and len(hot) < len(eligible):
        return LOCALIZED, "few_cells", [c.value for c in hot]
    if len(eligible) == 1 and hot:
        return INCONCLUSIVE, "too_few_samples", []
    return INCONCLUSIVE, "no_pattern", []


def _fold(finding: Finding) -> None:
    """Fold per-dimension verdicts into one (localized > mix_shift > global > inconclusive)."""
    if not finding.dims:
        finding.verdict = NOT_STRATIFIED
        return
    for code in VERDICT_PRIORITY:
        match = next((d for d in finding.dims if d.verdict == code), None)
        if match:
            finding.verdict = code
            finding.verdict_dim = match.dim
            finding.focus = list(match.focus)
            return
