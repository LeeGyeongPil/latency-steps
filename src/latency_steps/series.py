"""Per-key percentile time series with a minimum-sample guard."""

from __future__ import annotations

from datetime import timedelta

import duckdb

from .errors import LatencyStepsError
from .model import KeySeries, SeriesPoint

AUTO_DAY_AFTER_DAYS = 14


def choose_bucket(con: duckdb.DuckDBPyConnection, bucket: str) -> str:
    """Resolve ``auto`` to ``day`` for spans of 14 days or more, else ``hour``."""
    if bucket in ("hour", "day"):
        return bucket
    if bucket != "auto":
        raise LatencyStepsError("bad_bucket", value=bucket)
    first, last = con.execute("SELECT min(lts), max(lts) FROM events").fetchone()
    if first is None:
        return "day"
    return "day" if last - first >= timedelta(days=AUTO_DAY_AFTER_DAYS) else "hour"


def build_series(
    con: duckdb.DuckDBPyConnection,
    bucket: str,
    min_n: int,
    only: list[str] | None = None,
) -> list[KeySeries]:
    """Return one ``KeySeries`` per key: p50/p90/n per bucket for buckets with n >= ``min_n``.

    Buckets below ``min_n`` are not part of the series; they are listed in
    ``KeySeries.insufficient`` so reports can say so.
    """
    if bucket not in ("hour", "day"):
        raise LatencyStepsError("bad_bucket", value=bucket)
    if min_n < 1:
        raise LatencyStepsError("bad_number", name="--min-n", value=min_n)
    rows = con.execute(
        f"""
        SELECT key, date_trunc('{bucket}', lts) AS bucket, count(*) AS n,
               quantile_cont(ms, 0.5) AS p50, quantile_cont(ms, 0.9) AS p90
        FROM events
        GROUP BY key, bucket
        ORDER BY key, bucket
        """
    ).fetchall()
    by_key: dict[str, KeySeries] = {}
    for key, b, n, p50, p90 in rows:
        if only and key not in only:
            continue
        ks = by_key.setdefault(key, KeySeries(key=key, rows=0))
        ks.rows += n
        if n >= min_n:
            ks.points.append(SeriesPoint(bucket=b, n=n, p50=float(p50), p90=float(p90)))
        else:
            ks.insufficient.append((b, n))
    return sorted(by_key.values(), key=lambda s: s.key)
