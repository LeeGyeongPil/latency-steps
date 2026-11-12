"""Shared fixtures: seeded synthetic logs written once per seed."""

from __future__ import annotations

from pathlib import Path

import pytest

from latency_steps.analysis import Options, analyze
from latency_steps.cli import DEMO_BY
from latency_steps.synth import write_logs


@pytest.fixture(autouse=True)
def _neutral_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests must not depend on the developer's locale: default to English."""
    for name in ("LATENCY_STEPS_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="session")
def synth_log(tmp_path_factory: pytest.TempPathFactory):
    """Return ``make(seed) -> Path`` of a 21-day synthetic JSONL log (cached per seed)."""
    cache: dict[int, Path] = {}

    def make(seed: int = 7) -> Path:
        if seed not in cache:
            path = tmp_path_factory.mktemp("synth") / f"seed{seed}.jsonl"
            write_logs(path, seed=seed, per_hour=40)
            cache[seed] = path
        return cache[seed]

    return make


@pytest.fixture(scope="session")
def demo_options() -> Options:
    return Options(ts="ts", duration="duration_ms", key="tool", by=list(DEMO_BY))


@pytest.fixture(scope="session")
def demo_report(synth_log, demo_options):
    """Full analysis of the default-seed synthetic log."""
    return analyze(str(synth_log(7)), demo_options, synthetic=True)
