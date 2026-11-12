"""The analysis pipeline: ingest -> percentile series -> steps -> stratification."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import __version__
from .detect import DEFAULT_THRESHOLD, detect_all
from .errors import LatencyStepsError
from .ingest import connect, load_events
from .model import Report
from .series import build_series, choose_bucket
from .stratify import parse_dim, stratify_change


@dataclass
class Options:
    """Everything ``analyze`` needs; defaults match the CLI defaults."""

    ts: str | None = None
    duration: str | None = None
    duration_unit: str | None = None
    key: str | None = None
    by: list[str] = field(default_factory=list)
    bucket: str = "auto"
    min_n: int = 30
    min_run: int = 3
    min_ratio: float = 1.2
    metric: str = "both"
    tz: str = "UTC"
    only: list[str] = field(default_factory=list)
    memory_limit: str = "1GB"
    threshold: float = DEFAULT_THRESHOLD


def analyze(path: str, opts: Options, *, synthetic: bool = False, label: str | None = None) -> Report:
    """Run the full analysis on ``path`` (``-`` reads standard input)."""
    if opts.min_run < 2:
        raise LatencyStepsError("bad_number", name="--min-run", value=opts.min_run)
    if opts.min_ratio <= 1.0:
        raise LatencyStepsError("bad_number", name="--min-ratio", value=opts.min_ratio)
    if opts.metric not in ("p50", "p90", "both"):
        raise LatencyStepsError("bad_metric", value=opts.metric)
    dims = [parse_dim(spec, i) for i, spec in enumerate(opts.by)]
    con = connect(opts.memory_limit)
    try:
        stats = load_events(
            con,
            path,
            ts_field=opts.ts,
            duration_field=opts.duration,
            duration_unit=opts.duration_unit,
            key_field=opts.key,
            by_fields=[d.field for d in dims],
            tz=opts.tz,
        )
        bucket = choose_bucket(con, opts.bucket)
        series = build_series(con, bucket, opts.min_n, opts.only or None)
        if opts.only and not series:
            raise LatencyStepsError("no_such_key", keys=", ".join(opts.only))
        steps, observations = detect_all(
            series,
            min_run=opts.min_run,
            min_ratio=opts.min_ratio,
            metric=opts.metric,
            threshold=opts.threshold,
        )
        findings = [stratify_change(con, s, dims, min_ratio=opts.min_ratio) for s in steps]
    finally:
        con.close()
    return Report(
        version=__version__,
        source=label or ("<stdin>" if path == "-" else path),
        synthetic=synthetic,
        stats=stats,
        bucket=bucket,
        tz=opts.tz,
        min_n=opts.min_n,
        min_run=opts.min_run,
        min_ratio=opts.min_ratio,
        metric=opts.metric,
        dims=[d.field for d in dims],
        series=series,
        findings=findings,
        observations=observations,
    )
