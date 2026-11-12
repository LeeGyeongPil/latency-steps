"""AC-1 and AC-6: demo end to end, JSON output and exit codes."""

from __future__ import annotations

import io
import json
import random
import subprocess
import sys

from latency_steps.cli import main


def test_demo_runs_end_to_end(capsys):
    code = main(["demo", "--lang", "en"])
    out = capsys.readouterr().out
    assert code == 0
    assert "SYNTHETIC PRACTICE DATA" in out
    findings = out.split("Findings")[1].split("Observations")[0]
    for key in ("search", "embed", "rerank"):
        assert key in findings
    assert "chat" not in findings
    assert "chat" in out.split("Observations")[1].split("Stratification")[0]


def test_exit_codes_and_json(tmp_path, capsys):
    # A step exists -> exit 1 with --fail-on-step, JSON still printed.
    code = main(["demo", "--format", "json", "--fail-on-step", "--lang", "en"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["schema_version"] == 1
    assert isinstance(payload["findings"], list) and len(payload["findings"]) == 3
    assert payload["input"]["rows_read"] == 20160
    first = payload["findings"][0]
    assert {"key", "verdict", "stratification", "summary", "ratio"} <= set(first)

    # Same log without --fail-on-step exits 0.
    assert main(["demo", "--format", "json"]) == 0
    capsys.readouterr()

    # A flat log has no step -> exit 0 even with --fail-on-step.
    rng = random.Random(1)
    flat = tmp_path / "flat.jsonl"
    lines = [
        json.dumps({"ts": f"2026-03-{d + 1:02d}T{i % 24:02d}:00:00Z", "duration_ms": 100 * rng.lognormvariate(0, 0.3)})
        for d in range(20)
        for i in range(60)
    ]
    flat.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert main(["analyze", str(flat), "--format", "json", "--fail-on-step"]) == 0
    assert json.loads(capsys.readouterr().out)["findings"] == []

    # Input and option errors -> exit 2 with a message on stderr.
    assert main(["analyze", str(tmp_path / "missing.jsonl")]) == 2
    assert "not found" in capsys.readouterr().err
    assert main(["analyze", str(flat), "--by", "concurrency:abc"]) == 2
    assert "--by" in capsys.readouterr().err
    assert main(["analyze", str(flat), "--tz", "Mars/Base"]) == 2
    capsys.readouterr()
    assert main(["analyze", str(flat), "--lang", "ko", "--ts", "nope"]) == 2
    assert "오류" in capsys.readouterr().err


def test_analyze_stdin_and_out_file(tmp_path, capsys, monkeypatch, synth_log):
    data = synth_log(7).read_bytes()
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data)))
    out = tmp_path / "report.md"
    code = main(["analyze", "-", "--key", "tool", "--by", "host", "--format", "md", "--out", str(out)])
    assert code == 0
    text = out.read_text(encoding="utf-8")
    assert "## Findings" in text and "| embed |" in text
    assert capsys.readouterr().out == ""


def test_demo_save_and_only(tmp_path, capsys):
    saved = tmp_path / "demo.jsonl"
    assert main(["demo", "--save", str(saved), "--only", "chat", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert saved.stat().st_size > 0
    assert payload["findings"] == [] and [o["key"] for o in payload["observations"]] == ["chat"]


def test_module_entry_point_prints_utf8():
    result = subprocess.run(
        [sys.executable, "-m", "latency_steps", "demo", "--lang", "ko", "--only", "search"],
        capture_output=True,
        encoding="utf-8",
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "지연 계단 보고서" in result.stdout


def test_jsonl_unknown_key_or_by_field_is_an_error(synth_log, capsys):
    # Q-2: the same typo that CSV rejects must be rejected for JSONL (exit 2, fields listed).
    log = str(synth_log(7))
    for extra in (["--by", "nosuch"], ["--key", "nosuch"]):
        assert main(["analyze", log, *extra, "--fail-on-step"]) == 2
        err = capsys.readouterr().err
        assert "nosuch" in err and "Fields seen" in err
        assert "tool" in err
    assert main(["--lang", "ko", "analyze", log, "--by", "nosuch"]) == 2
    assert "로그에서 본 필드" in capsys.readouterr().err
    # Real fields still work.
    assert main(["analyze", log, "--key", "tool", "--by", "host", "--only", "chat"]) == 0
    capsys.readouterr()


def test_empty_input_file_has_its_own_error(tmp_path, capsys):
    # Q-5: an empty (or blank-only) file is reported as empty, for JSONL and CSV.
    for name, content in (("empty.jsonl", ""), ("blank.jsonl", "\n  \n"), ("empty.csv", "")):
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        assert main(["analyze", str(path)]) == 2
        err = capsys.readouterr().err
        assert "empty" in err and "Fields seen" not in err, name
    assert main(["--lang", "ko", "analyze", str(tmp_path / "empty.jsonl")]) == 2
    assert "비어 있습니다" in capsys.readouterr().err


def test_ci_workflow_tolerates_the_demo_exit_code():
    # Q-1: GitHub runs steps with `bash -e`; the demo's exit 1 must not abort the step.
    import pathlib
    import shutil
    import subprocess

    ci = (pathlib.Path(__file__).parent.parent / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "> /dev/null; test $?" not in ci
    bash = shutil.which("bash")
    if bash is None:
        return
    script = "code=0\n(exit 1) || code=$?\ntest \"$code\" -eq 1\n"
    assert subprocess.run([bash, "-e", "-c", script], check=False).returncode == 0
