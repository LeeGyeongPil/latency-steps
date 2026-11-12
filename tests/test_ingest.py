"""AC-4: tolerant ingest of messy input across jsonl, gz, csv and stdin."""

from __future__ import annotations

import csv
import gzip
import io
import json
import sys
from datetime import datetime

import pytest

from latency_steps.errors import LatencyStepsError
from latency_steps.ingest import connect, load_events

# Values a real log might hold: unit suffixes, epoch seconds, ISO text, numbers.
CLEAN_ROWS = [
    {"time": "2026-01-01T10:00:00Z", "took": "12ms", "route": "a", "host": "h1"},
    {"time": "2026-01-01T10:05:00Z", "took": "1.2s", "route": "b", "host": "h2"},
    {"time": 1759276800, "took": 250, "route": "c", "host": "h1"},
    {"time": "2026-01-01T11:00:00+00:00", "took": 40.5, "route": "a", "host": "h2"},
    {"time": "not-a-time", "took": 10, "route": "a", "host": "h1"},  # dropped: bad timestamp
    {"time": "2026-01-01T12:00:00Z", "took": "fast", "route": "a", "host": "h1"},  # bad duration
]
FIELDS = dict(ts_field="time", duration_field="took", key_field="route", by_fields=["host"])


def _load(path: str):
    con = connect()
    try:
        stats = load_events(con, path, **FIELDS)
        rows = con.execute("SELECT key, lts, ms, d0 FROM events ORDER BY key, lts, ms").fetchall()
    finally:
        con.close()
    return stats, rows


def _write_jsonl(path, rows, extra=()):
    lines = [json.dumps(r) for r in rows] + list(extra)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_tolerant_parsing(tmp_path, monkeypatch):
    base = tmp_path / "messy.jsonl"
    _write_jsonl(base, CLEAN_ROWS, extra=['{"time": "2026-01-01T13:00:00Z", "took": 5, "route":'])
    stats, rows = _load(str(base))

    # 7 non-empty lines: 1 broken JSON, 1 bad timestamp, 1 bad duration are dropped.
    assert stats.rows_read == 7 and stats.rows_kept == 4 and stats.rows_dropped == 3
    assert stats.dropped == {"invalid_record": 1, "bad_timestamp": 1, "bad_duration": 1}
    by_key = {(k, d): (lts, ms) for k, lts, ms, d in rows}
    assert by_key[("a", "h1")][1] == 12.0  # "12ms"
    assert by_key[("b", "h2")][1] == 1200.0  # "1.2s"
    assert by_key[("c", "h1")] == (datetime(2025, 10, 1, 0, 0), 250.0)  # epoch seconds -> 2025-10-01T00:00:00Z

    # The same logical rows as gzip, CSV and standard input give the same events.
    clean = [r for r in CLEAN_ROWS if r["time"] != "not-a-time"]
    plain = tmp_path / "clean.jsonl"
    _write_jsonl(plain, clean)
    expected = _load(str(plain))
    assert expected[0].rows_kept == 4

    gz = tmp_path / "clean.jsonl.gz"
    gz.write_bytes(gzip.compress(plain.read_bytes()))
    assert _load(str(gz))[1] == expected[1]

    csv_path = tmp_path / "clean.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["time", "took", "route", "host"])
        writer.writeheader()
        writer.writerows(clean)
    assert _load(str(csv_path))[1] == expected[1]

    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(plain.read_bytes())))
    assert _load("-")[1] == expected[1]


def test_duration_unit_option_and_field_name_hint(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text('{"ts":"2026-01-01T00:00:00Z","elapsed":2}\n{"ts":"2026-01-01T00:00:01Z","elapsed":"300ms"}\n', encoding="utf-8")
    con = connect()
    try:
        stats = load_events(con, str(path), duration_unit="s")
        values = sorted(r[0] for r in con.execute("SELECT ms FROM events").fetchall())
    finally:
        con.close()
    assert values == [300.0, 2000.0] and stats.duration_unit == "s"


def test_fields_are_guessed_from_the_data(tmp_path):
    path = tmp_path / "g.jsonl"
    path.write_text('{"timestamp":"2026-01-01T00:00:00Z","latency_ms":5}\n', encoding="utf-8")
    con = connect()
    try:
        stats = load_events(con, str(path))
    finally:
        con.close()
    assert (stats.ts_field, stats.duration_field, stats.duration_unit) == ("timestamp", "latency_ms", "ms")


@pytest.mark.parametrize(
    "content, code",
    [
        ('{"a":1}\n', "field_not_found"),
        ('{"ts":"x","duration_ms":"y"}\n', "no_rows"),
    ],
)
def test_unusable_input_raises_a_helpful_error(tmp_path, content, code):
    path = tmp_path / "bad.jsonl"
    path.write_text(content, encoding="utf-8")
    con = connect()
    try:
        with pytest.raises(LatencyStepsError) as info:
            load_events(con, str(path))
    finally:
        con.close()
    assert info.value.code == code


def test_missing_file_and_bad_options(tmp_path):
    con = connect()
    try:
        with pytest.raises(LatencyStepsError) as info:
            load_events(con, str(tmp_path / "nope.jsonl"))
        assert info.value.code == "file_not_found"
        sample = tmp_path / "s.jsonl"
        sample.write_text('{"ts":"2026-01-01T00:00:00Z","duration_ms":1}\n', encoding="utf-8")
        with pytest.raises(LatencyStepsError) as info:
            load_events(con, str(sample), tz="Mars/Base")
        assert info.value.code == "bad_timezone"
        with pytest.raises(LatencyStepsError) as info:
            load_events(con, str(sample), key_field='a"b')
        assert info.value.code == "bad_field_name"
    finally:
        con.close()
    with pytest.raises(LatencyStepsError):
        connect("lots")
