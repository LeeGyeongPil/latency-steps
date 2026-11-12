"""AC-10: packaging metadata, single runtime dependency, CI timeout."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import latency_steps

ROOT = Path(__file__).resolve().parent.parent


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_packaging_metadata():
    project = _pyproject()["project"]
    assert project["dependencies"] == ["duckdb>=2.0.0,<3"]
    assert project["requires-python"] == ">=3.11"
    assert project["scripts"]["latency-steps"] == "latency_steps.cli:main"
    assert project["license"] == "MIT"
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "timeout-minutes:" in ci
    assert "uv run pytest -q" in ci
    result = subprocess.run(
        [sys.executable, "-m", "latency_steps", "--version"],
        capture_output=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0
    assert latency_steps.__version__ in result.stdout


def test_version_matches_pyproject():
    assert latency_steps.__version__ == _pyproject()["project"]["version"]


def test_pytest_has_a_timeout():
    assert "timeout" in _pyproject()["tool"]["pytest"]["ini_options"]


def test_changelog_mentions_current_version():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"[{latency_steps.__version__}]" in changelog
