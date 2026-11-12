"""AC-2: step detection finds planted steps and keeps a one-day spike out of the findings."""

from __future__ import annotations

import ast
import math
import random
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import latency_steps.detect as detect_module
from latency_steps.analysis import analyze
from latency_steps.detect import detect
from latency_steps.model import KeySeries, SeriesPoint

EXPECTED = {"search": "2026-10-11", "rerank": "2026-10-09", "embed": "2026-10-13"}


def _day(text: str) -> datetime:
    return datetime.fromisoformat(text)


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_synthetic_steps_found(seed, synth_log, demo_options):
    report = analyze(str(synth_log(seed)), demo_options)
    found = {f.change.key: f.change for f in report.findings}
    # No false findings: exactly the three planted keys, one step each.
    assert sorted(found) == sorted(EXPECTED), [f.change.key for f in report.findings]
    assert len(report.findings) == 3
    for key, planted in EXPECTED.items():
        assert abs(found[key].at - _day(planted)) <= timedelta(days=1), (key, found[key].at)
        assert found[key].direction == "up"
    # chat: the one-day spike is an observation, never a finding.
    chat = [o for o in report.observations if o.key == "chat"]
    assert len(chat) == 1
    assert chat[0].kind == "spike" and chat[0].at == _day("2026-10-06")
    assert all(f.change.key != "chat" for f in report.findings)


def _series(values, start=datetime(2026, 1, 1), step=timedelta(days=1), n=100):
    return KeySeries(
        key="k", rows=len(values) * n,
        points=[SeriesPoint(start + i * step, n, v, v * 1.5) for i, v in enumerate(values)],
    )


def _noisy(rng, level, count, sigma=0.04):
    return [level * math.exp(rng.gauss(0, sigma)) for _ in range(count)]


def test_two_bucket_blip_is_not_a_step():
    rng = random.Random(3)
    values = _noisy(rng, 100, 10) + _noisy(rng, 400, 2) + _noisy(rng, 100, 10)
    steps, observations = detect(_series(values), min_run=3)
    assert steps == []
    assert [o.kind for o in observations] == ["spike"]


def test_sustained_shift_is_a_step_and_gets_the_right_edge():
    rng = random.Random(4)
    values = _noisy(rng, 100, 12) + _noisy(rng, 200, 8)
    steps, _ = detect(_series(values), min_run=3)
    assert len(steps) == 1
    assert steps[0].index == 12
    assert 1.8 < steps[0].ratio < 2.2


def test_speedup_is_an_observation_not_a_finding():
    rng = random.Random(5)
    values = _noisy(rng, 200, 10) + _noisy(rng, 100, 10)
    steps, observations = detect(_series(values), min_run=3)
    assert steps == []
    assert [o.kind for o in observations] == ["faster"]


def test_recent_short_shift_is_reported_as_tail():
    rng = random.Random(6)
    values = _noisy(rng, 100, 16) + _noisy(rng, 300, 2)
    steps, observations = detect(_series(values), min_run=3)
    assert steps == []
    assert [o.kind for o in observations] == ["tail"]


def test_small_changes_below_min_ratio_are_ignored():
    rng = random.Random(7)
    values = _noisy(rng, 100, 12, 0.005) + _noisy(rng, 110, 12, 0.005)
    steps, _ = detect(_series(values), min_run=3, min_ratio=1.2)
    assert steps == []


def test_2000_point_series_is_fast():
    rng = random.Random(8)
    values = _noisy(rng, 100, 1200) + _noisy(rng, 180, 800)
    series = _series(values, step=timedelta(hours=1))
    started = time.perf_counter()
    steps, _ = detect(series, min_run=3)
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0, elapsed
    assert any(abs(s.index - 1200) <= 3 for s in steps)


def test_detect_module_uses_only_the_standard_library():
    tree = ast.parse(Path(detect_module.__file__).read_text(encoding="utf-8"))
    import sys

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in sys.stdlib_module_names, alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                assert node.module.split(".")[0] in sys.stdlib_module_names, node.module
            else:
                assert node.module == "model"  # only the plain data containers
