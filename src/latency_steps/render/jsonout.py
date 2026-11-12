"""JSON report (``schema_version`` 1). Keys and codes are always English."""

from __future__ import annotations

import json
from typing import Any

from ..i18n import t
from ..model import Cell, DimVerdict, Finding, Observation, Report
from .common import finding_summary, fmt_bucket, verdict_dim

SCHEMA_VERSION = 1


def _round(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


def _cell(c: Cell) -> dict[str, Any]:
    return {
        "value": c.value, "n_before": c.n_before, "n_after": c.n_after,
        "p50_before_ms": _round(c.p50_before), "p50_after_ms": _round(c.p50_after),
        "p90_before_ms": _round(c.p90_before), "p90_after_ms": _round(c.p90_after),
        "share_before": _round(c.share_before, 4), "share_after": _round(c.share_after, 4),
        "ratio": _round(c.ratio), "new": c.new, "thin": c.thin,
    }


def _dim(d: DimVerdict) -> dict[str, Any]:
    return {
        "dim": d.dim, "verdict": d.verdict, "reason": d.reason, "metric": d.metric,
        "focus": d.focus, "cells": [_cell(c) for c in d.cells],
    }


def _finding(f: Finding, report: Report, lang: str) -> dict[str, Any]:
    c = f.change
    dv = verdict_dim(f)
    return {
        "key": c.key,
        "at": c.at.isoformat(),
        "since": fmt_bucket(c.at, report.bucket),
        "metric": c.metric,
        "ratio": _round(c.ratio),
        "score": c.score,
        "run_buckets": c.run_buckets,
        "p50_before_ms": _round(c.p50_before), "p50_after_ms": _round(c.p50_after),
        "p90_before_ms": _round(c.p90_before), "p90_after_ms": _round(c.p90_after),
        "verdict": f.verdict,
        "verdict_dim": f.verdict_dim,
        "verdict_reason": dv.reason if dv else None,
        "focus": f.focus,
        "summary": finding_summary(f, report, lang),
        "stratification": [_dim(d) for d in f.dims],
    }


def _observation(o: Observation) -> dict[str, Any]:
    return {
        "key": o.key, "kind": o.kind, "at": o.at.isoformat(), "until": o.until.isoformat(),
        "metric": o.metric, "ratio": _round(o.ratio),
    }


def build_json(report: Report, lang: str) -> dict[str, Any]:
    s = report.stats
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "latency-steps",
        "version": report.version,
        "lang": lang,
        "synthetic": report.synthetic,
        "input": {
            "source": report.source,
            "format": s.format,
            "rows_read": s.rows_read,
            "rows_kept": s.rows_kept,
            "rows_dropped": s.rows_dropped,
            "dropped": s.dropped,
            "ts_field": s.ts_field,
            "duration_field": s.duration_field,
            "duration_unit": s.duration_unit,
            "key_field": s.key_field,
        },
        "settings": {
            "bucket": report.bucket, "tz": report.tz, "min_n": report.min_n,
            "min_run": report.min_run, "min_ratio": report.min_ratio,
            "metric": report.metric, "by": report.dims,
        },
        "summary": (
            t(lang, "summary.none") if not report.findings
            else " ".join(finding_summary(f, report, lang) for f in report.findings)
        ),
        "findings": [_finding(f, report, lang) for f in report.findings],
        "observations": [_observation(o) for o in report.observations],
        "insufficient": {
            s.key: [{"bucket": b.isoformat(), "n": n} for b, n in s.insufficient]
            for s in report.series if s.insufficient
        },
    }


def render_json(report: Report, lang: str) -> str:
    return json.dumps(build_json(report, lang), ensure_ascii=False, indent=2) + "\n"
