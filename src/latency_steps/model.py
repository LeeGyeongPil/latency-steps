"""Plain data containers shared by the pipeline stages and the renderers.

Everything here is language neutral: human-readable text is produced only at
render time from codes and parameters (see ``i18n``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Verdict codes (stable, English, used in JSON).
LOCALIZED = "localized"
MIX_SHIFT = "mix_shift"
GLOBAL = "global"
INCONCLUSIVE = "inconclusive"
NOT_STRATIFIED = "not_stratified"

# Priority used to fold per-dimension verdicts into one (first match wins).
VERDICT_PRIORITY = (LOCALIZED, MIX_SHIFT, GLOBAL, INCONCLUSIVE)


@dataclass
class IngestStats:
    """How many input rows were read, kept and dropped (and why)."""

    rows_read: int = 0
    rows_kept: int = 0
    dropped: dict[str, int] = field(default_factory=dict)
    format: str = "jsonl"
    ts_field: str = "ts"
    duration_field: str = "duration_ms"
    duration_unit: str = "ms"
    key_field: str | None = None

    @property
    def rows_dropped(self) -> int:
        return self.rows_read - self.rows_kept


@dataclass
class SeriesPoint:
    bucket: datetime
    n: int
    p50: float  # milliseconds
    p90: float  # milliseconds


@dataclass
class KeySeries:
    key: str
    rows: int
    points: list[SeriesPoint] = field(default_factory=list)
    insufficient: list[tuple[datetime, int]] = field(default_factory=list)


@dataclass
class ChangePoint:
    """A sustained level change found in a key's percentile series."""

    key: str
    index: int  # index into KeySeries.points of the first bucket at the new level
    at: datetime  # bucket start of that point
    direction: str  # "up" or "down"
    metric: str  # "p50" or "p90": the series with the larger ratio
    score: float
    p50_before: float
    p50_after: float
    p90_before: float
    p90_after: float
    ratio: float  # after / before on ``metric`` (> 1 means slower)
    run_buckets: int  # buckets in the new-level segment
    before_start: datetime  # start of the segment before the change
    after_end: datetime | None  # end (exclusive) of the segment after, None = open


@dataclass
class Observation:
    """Something worth a look that is not a sustained slowdown."""

    key: str
    kind: str  # "spike" | "tail" | "faster"
    at: datetime
    until: datetime  # last bucket start covered
    metric: str
    ratio: float


@dataclass
class Cell:
    value: str
    n_before: int
    n_after: int
    p50_before: float | None
    p50_after: float | None
    p90_before: float | None
    p90_after: float | None
    share_before: float
    share_after: float
    ratio: float | None  # None when the cell is new or too thin to compare
    new: bool = False
    thin: bool = False


@dataclass
class DimVerdict:
    dim: str
    verdict: str
    reason: str  # code, e.g. "one_cell", "new_cell", "composition", "most_cells"
    cells: list[Cell] = field(default_factory=list)
    focus: list[str] = field(default_factory=list)  # cells named by the verdict
    metric: str = "p50"


@dataclass
class Finding:
    change: ChangePoint
    dims: list[DimVerdict] = field(default_factory=list)
    verdict: str = NOT_STRATIFIED
    verdict_dim: str | None = None
    focus: list[str] = field(default_factory=list)


@dataclass
class Report:
    version: str
    source: str
    synthetic: bool
    stats: IngestStats
    bucket: str  # "hour" | "day"
    tz: str
    min_n: int
    min_run: int
    min_ratio: float
    metric: str
    dims: list[str]
    series: list[KeySeries] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)
