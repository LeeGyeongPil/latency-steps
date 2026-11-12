"""AC-5: minimum-sample guard and timezone-aware buckets."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from latency_steps.errors import LatencyStepsError
from latency_steps.ingest import connect, load_events
from latency_steps.series import build_series, choose_bucket


def _load(tmp_path, rows, tz="UTC"):
    path = tmp_path / "rows.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    con = connect()
    load_events(con, str(path), key_field="k", tz=tz)
    return con


def test_min_n_and_tz_buckets(tmp_path):
    rows = (
        [{"ts": f"2025-10-01T{h:02d}:00:00Z", "duration_ms": 100 + h, "k": "x"} for h in range(5)]  # 5 rows
        + [{"ts": "2025-10-02T01:00:00Z", "duration_ms": 50, "k": "x"}] * 2  # 2 rows: too thin
        + [{"ts": "2025-10-01T15:00:00Z", "duration_ms": 70, "k": "y"}]
    )
    con = _load(tmp_path, rows)
    try:
        series = {s.key: s for s in build_series(con, "day", min_n=3)}
    finally:
        con.close()
    assert [(p.bucket, p.n) for p in series["x"].points] == [(datetime(2025, 10, 1), 7 - 2)]
    assert series["x"].insufficient == [(datetime(2025, 10, 2), 2)]
    assert series["y"].points == [] and series["y"].insufficient == [(datetime(2025, 10, 1), 1)]

    # Asia/Seoul is UTC+9: 15:00 UTC is midnight the next day there.
    con = _load(tmp_path, rows, tz="Asia/Seoul")
    try:
        seoul = {s.key: s for s in build_series(con, "day", min_n=1)}
    finally:
        con.close()
    assert [p.bucket for p in seoul["y"].points] == [datetime(2025, 10, 2)]


def test_percentiles_and_auto_bucket(tmp_path):
    rows = [{"ts": f"2025-10-01T00:{m:02d}:00Z", "duration_ms": float(m + 1), "k": "x"} for m in range(40)]
    con = _load(tmp_path, rows)
    try:
        assert choose_bucket(con, "auto") == "hour"
        point = build_series(con, "hour", min_n=1)[0].points[0]
        assert point.p50 == pytest.approx(20.5) and point.p90 == pytest.approx(36.1)
        with pytest.raises(LatencyStepsError):
            build_series(con, "week", min_n=1)
        with pytest.raises(LatencyStepsError):
            build_series(con, "day", min_n=0)
    finally:
        con.close()


def test_auto_bucket_switches_to_day_for_long_logs(tmp_path):
    rows = [{"ts": "2025-10-01T00:00:00Z", "duration_ms": 1, "k": "x"},
            {"ts": "2025-10-20T00:00:00Z", "duration_ms": 1, "k": "x"}]
    con = _load(tmp_path, rows)
    try:
        assert choose_bucket(con, "auto") == "day"
    finally:
        con.close()
