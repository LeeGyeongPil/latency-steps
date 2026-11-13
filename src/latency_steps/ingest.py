"""Tolerant ingestion of JSONL / CSV logs into an in-memory DuckDB table.

Every field is read as text and converted with ``try_cast`` so one bad value
never fails the whole file; rows that cannot be interpreted are counted by
reason instead of being silently lost.

The result is a table ``events(key, lts, ms, d0, d1, ...)``:

* ``lts``  - timestamp converted to the chosen timezone, naive (wall clock)
* ``ms``   - duration in milliseconds
* ``dN``   - raw text of the Nth ``--by`` field
"""

from __future__ import annotations

import gzip
import re
import shutil
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb

from .errors import LatencyStepsError
from .model import IngestStats

TS_CANDIDATES = ("ts", "timestamp", "time", "@timestamp", "datetime", "date", "start_time")
DURATION_CANDIDATES = (
    "duration_ms", "latency_ms", "elapsed_ms", "duration", "latency", "elapsed",
    "duration_s", "elapsed_s", "latency_s", "took",
)
UNIT_FACTORS = {"ms": 1.0, "s": 1000.0, "us": 0.001}
GZIP_MAGIC = b"\x1f\x8b"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

_NUMBER_WITH_UNIT = r"^\s*([0-9]*\.?[0-9]+)\s*([a-zA-Zµμ]*)\s*$"


def connect(memory_limit: str = "1GB") -> duckdb.DuckDBPyConnection:
    """Open an in-memory DuckDB connection with a memory cap and UTC session time."""
    if not re.fullmatch(r"\d+(\.\d+)?\s*(KB|MB|GB|TB|KiB|MiB|GiB|TiB)", memory_limit, re.IGNORECASE):
        raise LatencyStepsError("bad_memory_limit", value=memory_limit)
    con = duckdb.connect(":memory:")
    con.execute(f"SET memory_limit='{memory_limit}'")
    con.execute("SET TimeZone='UTC'")
    return con


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _check_field_name(name: str) -> str:
    if not name or '"' in name or "'" in name or "\\" in name:
        raise LatencyStepsError("bad_field_name", name=name)
    return name


@contextmanager
def materialize_input(path: str) -> Iterator[Path]:
    """Yield a real file path for ``path``; ``-`` is copied from stdin to a temp file."""
    if path != "-":
        p = Path(path)
        if not p.is_file():
            raise LatencyStepsError("file_not_found", path=path)
        yield p
        return
    with tempfile.TemporaryDirectory(prefix="latency-steps-") as tmp:
        raw = Path(tmp) / "stdin.raw"
        with open(raw, "wb") as out:
            shutil.copyfileobj(sys.stdin.buffer, out)
        with open(raw, "rb") as f:
            magic = f.read(4)
        if magic[:2] == GZIP_MAGIC:
            final = raw.with_name("stdin.data.gz")
        elif magic == ZSTD_MAGIC:
            final = raw.with_name("stdin.data.zst")
        else:
            final = raw.with_name("stdin.data")
        raw.rename(final)
        yield final


def detect_format(path: Path) -> str:
    """Return ``"jsonl"`` or ``"csv"`` from the file name, sniffing the content if needed."""
    name = path.name.lower()
    for suffix in (".gz", ".zst"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    if name.endswith(".csv"):
        return "csv"
    if name.endswith((".jsonl", ".ndjson", ".json", ".log")):
        return "jsonl"
    first = _peek_text(path, 1)
    return "jsonl" if first and first[0].lstrip().startswith("{") else "csv"


def _peek_text(path: Path, lines: int) -> list[str]:
    """First ``lines`` text lines of a possibly compressed file (gzip handled directly)."""
    try:
        if path.name.lower().endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8-sig", errors="replace") as f:
                return [next(f, "") for _ in range(lines)]
        if path.name.lower().endswith(".zst"):
            con = duckdb.connect(":memory:")
            try:
                rows = con.execute(
                    "SELECT l FROM read_csv(?, header=false, columns={'l':'VARCHAR'}, "
                    "delim='\x1f', quote='', escape='', auto_detect=false) LIMIT ?",
                    [str(path), lines],
                ).fetchall()
            finally:
                con.close()
            return [r[0] for r in rows]
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            return [next(f, "") for _ in range(lines)]
    except (OSError, duckdb.Error):
        return []


def _guess_fields(path: Path, fmt: str) -> list[str]:
    """Field names seen in the first lines (union of keys / CSV header)."""
    import csv
    import json

    lines = [ln for ln in _peek_text(path, 50) if ln.strip()]
    if fmt == "csv":
        return next(csv.reader(lines[:1]), [])
    names: dict[str, None] = {}
    for ln in lines:
        try:
            obj = json.loads(ln)
        except ValueError:
            continue
        if isinstance(obj, dict):
            names.update(dict.fromkeys(obj))
    return list(names)


def _pick(explicit: str | None, candidates: tuple[str, ...], seen: list[str], what: str) -> str:
    if explicit:
        return _check_field_name(explicit)
    lowered = {s.lower(): s for s in seen}
    for c in candidates:
        if c in lowered:
            return lowered[c]
    raise LatencyStepsError("field_not_found", what=what, seen=", ".join(seen[:12]) or "-")


def _unit_from_name(field_name: str) -> str | None:
    low = field_name.lower()
    if low.endswith("_ms"):
        return "ms"
    if low.endswith(("_us", "_micros")):
        return "us"
    if low.endswith(("_s", "_sec", "_seconds")):
        return "s"
    return None


def load_events(
    con: duckdb.DuckDBPyConnection,
    path: str,
    *,
    ts_field: str | None = None,
    duration_field: str | None = None,
    duration_unit: str | None = None,
    key_field: str | None = None,
    by_fields: list[str] | None = None,
    tz: str = "UTC",
) -> IngestStats:
    """Read ``path`` into the ``events`` table and return row counts.

    Raises ``LatencyStepsError`` for a missing file, unknown fields, a bad
    timezone, or when no row could be interpreted at all.
    """
    by_fields = [_check_field_name(f) for f in (by_fields or [])]
    if key_field:
        _check_field_name(key_field)
    if duration_unit is not None and duration_unit not in UNIT_FACTORS:
        raise LatencyStepsError("bad_unit", value=duration_unit)
    try:
        con.execute("SELECT timezone(?, TIMESTAMPTZ '2026-01-01 00:00:00+00')", [tz]).fetchall()
    except duckdb.Error as exc:
        raise LatencyStepsError("bad_timezone", value=tz) from exc

    with materialize_input(path) as file:
        fmt = detect_format(file)
        seen = _guess_fields(file, fmt)
        if not [ln for ln in _peek_text(file, 50) if ln.strip()]:
            raise LatencyStepsError("empty_input")
        ts_name = _pick(ts_field, TS_CANDIDATES, seen, "timestamp (--ts)")
        dur_name = _pick(duration_field, DURATION_CANDIDATES, seen, "duration (--duration)")
        unit = duration_unit or _unit_from_name(dur_name) or "ms"
        if seen:
            for needed in [ts_name, dur_name, *([key_field] if key_field else []), *by_fields]:
                if needed not in seen:
                    raise LatencyStepsError("field_not_found", what=needed, seen=", ".join(seen[:12]))

        if fmt == "jsonl":
            def col(name: str) -> str:
                return f"json_extract_string(l, '$.\"{name}\"')"

            source = (
                "SELECT CASE WHEN json_valid(raw) THEN raw END AS l, json_valid(raw) AS ok "
                "FROM read_csv(?, header=false, columns={'raw':'VARCHAR'}, delim='\x1f', "
                "quote='', escape='', auto_detect=false) WHERE length(trim(raw)) > 0"
            )
        else:
            def col(name: str) -> str:
                return _quote_ident(name) + "::VARCHAR"

            source = "SELECT *, true AS ok FROM read_csv(?, header=true, all_varchar=true, ignore_errors=true, null_padding=true)"

        by_cols = "".join(f", {col(f)} AS d{i}" for i, f in enumerate(by_fields))
        key_expr = f"coalesce(nullif({col(key_field)}, ''), '(none)')" if key_field else "'all'"
        default_factor = UNIT_FACTORS[unit]
        con.execute("DROP TABLE IF EXISTS raw_events")
        con.execute(
            f"""
            CREATE TABLE raw_events AS
            SELECT ok,
                   {key_expr} AS key,
                   {col(ts_name)} AS ts_text,
                   {col(dur_name)} AS dur_text
                   {by_cols}
            FROM ({source})
            """,
            [str(file)],
        )

    num = f"regexp_extract(dur_text, '{_NUMBER_WITH_UNIT}', 1)"
    suffix = f"lower(regexp_extract(dur_text, '{_NUMBER_WITH_UNIT}', 2))"
    factor = (
        f"CASE {suffix} WHEN '' THEN {default_factor} WHEN 'ms' THEN 1.0 WHEN 's' THEN 1000.0 "
        "WHEN 'us' THEN 0.001 WHEN 'µs' THEN 0.001 WHEN 'μs' THEN 0.001 WHEN 'm' THEN 60000.0 END"
    )
    epoch = "try_cast(ts_text AS DOUBLE)"
    ts_expr = (
        "CASE WHEN regexp_full_match(trim(ts_text), '[0-9]+(\\.[0-9]+)?') THEN "
        f"to_timestamp(CASE WHEN {epoch} > 1e14 THEN {epoch} / 1e6 "
        f"WHEN {epoch} > 1e11 THEN {epoch} / 1e3 ELSE {epoch} END) "
        "ELSE try_cast(trim(ts_text) AS TIMESTAMPTZ) END"
    )
    con.execute("DROP TABLE IF EXISTS events")
    con.execute(
        f"""
        CREATE TABLE events AS
        SELECT ok, key, timezone(?, {ts_expr}) AS lts,
               try_cast({num} AS DOUBLE) * {factor} AS ms
               {"".join(f", d{i}" for i in range(len(by_fields)))}
        FROM raw_events
        """,
        [tz],
    )
    total, bad_json, bad_ts, bad_dur = con.execute(
        """
        SELECT count(*),
               count(*) FILTER (WHERE NOT ok),
               count(*) FILTER (WHERE ok AND lts IS NULL),
               count(*) FILTER (WHERE ok AND lts IS NOT NULL AND (ms IS NULL OR ms < 0))
        FROM events
        """
    ).fetchone()
    con.execute("DELETE FROM events WHERE NOT ok OR lts IS NULL OR ms IS NULL OR ms < 0")
    kept = con.execute("SELECT count(*) FROM events").fetchone()[0]
    con.execute("DROP TABLE raw_events")

    dropped = {}
    if bad_json:
        dropped["invalid_record"] = bad_json
    if bad_ts:
        dropped["bad_timestamp"] = bad_ts
    if bad_dur:
        dropped["bad_duration"] = bad_dur
    stats = IngestStats(
        rows_read=total,
        rows_kept=kept,
        dropped=dropped,
        format=fmt,
        ts_field=ts_name,
        duration_field=dur_name,
        duration_unit=unit,
        key_field=key_field,
    )
    if kept == 0:
        raise LatencyStepsError(
            "no_rows", rows=total, ts=ts_name, duration=dur_name, dropped=total
        )
    return stats
