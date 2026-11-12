"""Formatting helpers shared by all renderers."""

from __future__ import annotations

from datetime import datetime

from ..i18n import t
from ..model import (
    GLOBAL, INCONCLUSIVE, LOCALIZED, MIX_SHIFT, NOT_STRATIFIED, DimVerdict, Finding, Report,
)


def fmt_bucket(dt: datetime, bucket: str) -> str:
    return dt.strftime("%Y-%m-%d") if bucket == "day" else dt.strftime("%Y-%m-%d %H:00")


def fmt_ms(ms: float | None) -> str:
    if ms is None:
        return "-"
    if ms >= 1000:
        return f"{ms / 1000:.2f} s"
    if ms >= 100:
        return f"{ms:.0f} ms"
    return f"{ms:.1f} ms"


def fmt_ratio(ratio: float | None) -> str:
    return "-" if ratio is None else f"{ratio:.2f}"


def fmt_pct(share: float) -> str:
    return f"{share * 100:.0f}%"


def verdict_dim(f: Finding) -> DimVerdict | None:
    return next((d for d in f.dims if d.dim == f.verdict_dim and d.verdict == f.verdict), None)


def where_text(f: Finding, lang: str) -> str:
    """Human-readable scope of a finding, built from the verdict code and focus cells."""
    if f.verdict == LOCALIZED:
        return t(lang, "where.localized", dim=f.verdict_dim, cells=", ".join(f.focus))
    if f.verdict == MIX_SHIFT:
        dv = verdict_dim(f)
        key = "where.mix_shift_new" if dv and dv.reason == "new_cell" else "where.mix_shift_composition"
        return t(lang, key, dim=f.verdict_dim, cells=", ".join(f.focus))
    if f.verdict == GLOBAL:
        return t(lang, "where.global")
    if f.verdict == INCONCLUSIVE:
        return t(lang, "where.inconclusive")
    return t(lang, "where.not_stratified")


def finding_summary(f: Finding, report: Report, lang: str) -> str:
    c = f.change
    before, after = (c.p50_before, c.p50_after) if c.metric == "p50" else (c.p90_before, c.p90_after)
    return t(
        lang, "summary.finding", key=c.key, metric=c.metric, before=fmt_ms(before),
        after=fmt_ms(after), ratio=fmt_ratio(c.ratio), at=fmt_bucket(c.at, report.bucket),
        verdict=t(lang, f"verdict.{f.verdict}"),
    )


def dropped_detail(report: Report, lang: str) -> str:
    return ", ".join(t(lang, f"r.drop.{code}", n=n) for code, n in report.stats.dropped.items())


def key_label(report: Report, lang: str) -> str:
    return report.stats.key_field or t(lang, "r.key_none")


def insufficient_summary(report: Report) -> tuple[int, list[str]]:
    total = sum(len(s.insufficient) for s in report.series)
    keys = [s.key for s in report.series if s.insufficient]
    return total, keys


__all__ = [
    "NOT_STRATIFIED", "fmt_bucket", "fmt_ms", "fmt_pct", "fmt_ratio", "where_text",
    "finding_summary", "dropped_detail", "key_label", "insufficient_summary", "verdict_dim",
]
