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


# --- UTF-8 byte order mark (Excel "CSV UTF-8", PowerShell exports) -------------------------
_BOM = b"\xef\xbb\xbf"
_BOM_ROWS = [
    {"ts": "2026-01-01T10:00:00Z", "duration_ms": 12, "tool": "a", "host": "h1"},
    {"ts": "2026-01-01T10:05:00Z", "duration_ms": 30, "tool": "b", "host": "h2"},
    {"ts": "2026-01-01T11:00:00Z", "duration_ms": 40, "tool": "a", "host": "h2"},
]


def _csv_bytes(bom: bool) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=list(_BOM_ROWS[0]))
    writer.writeheader()
    writer.writerows(_BOM_ROWS)
    data = buf.getvalue().encode("utf-8")
    return _BOM + data if bom else data


def _jsonl_bytes(bom: bool) -> bytes:
    data = ("\n".join(json.dumps(r) for r in _BOM_ROWS) + "\n").encode("utf-8")
    return _BOM + data if bom else data


def _load_auto(path, **kwargs):
    con = connect()
    try:
        stats = load_events(con, str(path), key_field="tool", **kwargs)
        rows = con.execute("SELECT key, lts, ms FROM events ORDER BY key, lts").fetchall()
    finally:
        con.close()
    return stats, rows


@pytest.mark.parametrize(
    "name, gz",
    [("bom.csv", False), ("bom.csv.gz", True), ("bom.data", False)],
)
def test_bom_csv_matches_plain_csv(tmp_path, name, gz):
    def write(file, bom):
        data = _csv_bytes(bom)
        file.write_bytes(gzip.compress(data) if gz else data)

    bom_file, plain_file = tmp_path / name, tmp_path / ("plain_" + name)
    write(bom_file, True)
    write(plain_file, False)
    stats, rows = _load_auto(bom_file)
    expected_stats, expected_rows = _load_auto(plain_file)
    assert stats.ts_field == "ts"
    assert stats.rows_kept == expected_stats.rows_kept == 3
    assert rows == expected_rows


def test_bom_csv_with_explicit_ts_option(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_bytes(_csv_bytes(True))
    stats, _ = _load_auto(path, ts_field="ts")
    assert stats.ts_field == "ts" and stats.rows_kept == 3


def test_bom_jsonl_without_extension_is_detected_as_jsonl(tmp_path):
    path = tmp_path / "bom.data"
    path.write_bytes(_jsonl_bytes(True))
    stats, rows = _load_auto(path)
    assert stats.rows_kept == 3 and len(rows) == 3


def test_bom_csv_from_stdin(tmp_path, capsys, monkeypatch):
    from latency_steps.cli import main

    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(_csv_bytes(True))))
    assert main(["analyze", "-", "--key", "tool", "--format", "json", "--lang", "en"]) == 0
    assert '"rows_kept": 3' in capsys.readouterr().out.replace('":3', '": 3')


def _utf8_lines(extra_bad: int = 1) -> bytes:
    good = [json.dumps(r) for r in CLEAN_ROWS if r["time"] != "not-a-time"]
    bad = b'{"time": "2026-01-01T13:00:00Z", "took": 5, "route": "ch\xff\xfe", "host": "h1"}'
    return ("\n".join(good) + "\n").encode() + (bad + b"\n") * extra_bad


@pytest.mark.parametrize("mode", ["plain", "gz", "stdin"])
def test_invalid_utf8_line_is_dropped_and_counted(tmp_path, monkeypatch, mode):
    data = _utf8_lines(2)
    if mode == "plain":
        target = tmp_path / "bad.jsonl"
        target.write_bytes(data)
        path = str(target)
    elif mode == "gz":
        target = tmp_path / "bad.jsonl.gz"
        target.write_bytes(gzip.compress(data))
        path = str(target)
    else:
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data)))
        path = "-"
    stats, rows = _load(path)
    assert stats.dropped == {"bad_duration": 1, "invalid_utf8": 2}
    assert stats.rows_read == 7 and stats.rows_kept == 4
    assert len(rows) == 4


def test_invalid_utf8_reason_is_localized():
    from latency_steps.i18n import MESSAGES

    for lang in ("en", "ko"):
        assert "{n}" in MESSAGES[lang]["r.drop.invalid_utf8"]


def test_mixed_invalid_line_is_counted_once(tmp_path):
    # One line with invalid UTF-8 and a raw 0x1F byte yields two DuckDB reject rows.
    good = _utf8_lines(0)
    bad = b'{"time": "2026-01-01T13:00:00Z", "took": 5, "route": "\xff\x1f\xfe"}\n'
    target = tmp_path / "mixed.jsonl"
    target.write_bytes(good + bad)
    stats, rows = _load(str(target))
    assert stats.rows_read == 6 and len(rows) == 4
    assert stats.dropped == {"bad_duration": 1, "invalid_utf8": 1}


def test_non_encoding_rejects_are_counted_as_unparseable(tmp_path):
    # A raw 0x1F byte (without bad UTF-8) is a rejected line: counted, not a crash.
    target = tmp_path / "ctl.jsonl"
    target.write_bytes(_utf8_lines(0) + b'{"time": "x", "took": 5, "route": "a\x1fb"}\n')
    stats, rows = _load(str(target))
    assert stats.rows_read == 6 and len(rows) == 4
    assert stats.dropped == {"bad_duration": 1, "invalid_record": 1}


def test_mixed_line_endings_is_a_localized_error(tmp_path):
    from latency_steps.cli import main

    target = tmp_path / "crlf.jsonl"
    data = _utf8_lines(0).replace(b"\n", b"\r", 1)
    target.write_bytes(data)
    con = connect()
    try:
        try:
            load_events(con, str(target), **FIELDS)
        except LatencyStepsError as exc:
            assert exc.code == "read_failed"
        else:  # pragma: no cover - DuckDB version without the error
            pytest.skip("this DuckDB version reads the file")
    finally:
        con.close()
    assert main(["analyze", str(target), "--format", "json", "--lang", "en"]) == 2


def test_csv_read_error_is_a_localized_error(tmp_path, capsys):
    from latency_steps.cli import main

    target = tmp_path / "mixed.csv"
    target.write_bytes(
        b"time,took,route\r2026-01-01T13:00:00Z,5,a\n2026-01-01T13:00:01Z,5,a\r\n"
    )
    for lang in ("en", "ko"):
        assert main(["analyze", str(target), "--format", "json", "--lang", lang]) == 2
        err = capsys.readouterr().err
        assert ".." not in err and "Traceback" not in err
        assert ("could not read the input" if lang == "en" else "입력을 읽을 수 없습니다") in err


def test_read_failed_message_has_no_double_full_stop(tmp_path, capsys):
    from latency_steps.cli import main

    target = tmp_path / "crlf.jsonl"
    target.write_bytes(_utf8_lines(0).replace(b"\n", b"\r", 1))
    for lang in ("en", "ko"):
        main(["analyze", str(target), "--format", "json", "--lang", lang])
        assert ".." not in capsys.readouterr().err


def test_read_failed_message_exists_in_both_languages():
    from latency_steps.i18n import MESSAGES

    for lang in ("en", "ko"):
        assert "{detail}" in MESSAGES[lang]["err.read_failed"]


def test_overlong_line_is_counted_as_unparseable(tmp_path):
    big = b'{"time": "2026-01-01T13:00:00Z", "took": 5, "route": "' + b"a" * (3 * 1024 * 1024) + b'"}\n'
    target = tmp_path / "big.jsonl"
    target.write_bytes(_utf8_lines(0) + big)
    stats, rows = _load(str(target))
    assert stats.rows_read == 6 and len(rows) == 4
    assert stats.dropped == {"bad_duration": 1, "invalid_record": 1}


def _csv_text_rows(n: int, latin1_every: int = 0) -> bytes:
    lines = ["time,took,route,host"]
    for i in range(n):
        host = "hé1" if latin1_every and i % latin1_every == 0 else "h2"
        lines.append(f"2026-01-01T10:{i // 60:02d}:{i % 60:02d}Z,{100 + i % 7},a,{host}")
    return ("\n".join(lines) + "\n").encode("latin-1")


def test_csv_latin1_rows_are_counted_as_invalid_utf8(tmp_path):
    # 2999 rows, every 4th host holds a Latin-1 "é" (0xE9): 750 bad rows.
    target = tmp_path / "latin1.csv"
    target.write_bytes(_csv_text_rows(2999, latin1_every=4))
    stats, rows = _load(str(target))
    bad = len(range(0, 2999, 4))
    assert stats.dropped == {"invalid_utf8": bad}
    assert stats.rows_read == 2999 and stats.rows_kept == 2999 - bad
    assert len(rows) == 2999 - bad


def test_csv_last_line_with_invalid_byte_is_counted(tmp_path):
    data = _csv_text_rows(40) + b"2026-01-01T11:00:00Z,5,ch\xffat,h2\n"
    target = tmp_path / "last.csv"
    target.write_bytes(data)
    stats, rows = _load(str(target))
    assert stats.dropped == {"invalid_utf8": 1}
    assert stats.rows_read == 41 and stats.rows_kept == 40


@pytest.mark.parametrize("delim, name", [(",", "d.csv"), (";", "d_semi.csv"), ("\t", "d.tsv"), ("|", "d_pipe.csv")])
@pytest.mark.parametrize("explicit", [False, True])
def test_delimited_files_match_comma_csv(tmp_path, delim, name, explicit):
    path = tmp_path / name
    lines = [delim.join([r["ts"], str(r["duration_ms"]), r["tool"]]) for r in _BOM_ROWS]
    path.write_text(delim.join(["ts", "duration_ms", "tool"]) + "\n" + "\n".join(lines) + "\n")
    kwargs = {"ts_field": "ts", "duration_field": "duration_ms"} if explicit else {}
    stats, rows = _load_auto(path, **kwargs)
    ref = tmp_path / "ref.csv"
    ref.write_bytes(_csv_bytes(False))
    _, expected = _load_auto(ref)
    assert stats.ts_field == "ts" and stats.rows_kept == 3
    assert rows == expected
