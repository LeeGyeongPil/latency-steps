"""Markdown report for pasting into issues, PRs and chat."""

from __future__ import annotations

from ..i18n import t
from ..model import Report
from .common import (
    dropped_detail, fmt_bucket, fmt_ms, fmt_pct, fmt_ratio, insufficient_summary, key_label,
    where_text,
)


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |"


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    return [_row(headers), _row(["---"] * len(headers)), *[_row(r) for r in rows]]


def render_markdown(report: Report, lang: str) -> str:
    out: list[str] = [f"# {t(lang, 'r.title')}", ""]
    if report.synthetic:
        out += [f"> **{t(lang, 'r.synthetic')}**", ""]
    s = report.stats
    out.append(
        t(lang, "r.input", source=f"`{report.source}`", rows_read=s.rows_read,
          rows_kept=s.rows_kept, dropped=s.rows_dropped)
    )
    if s.dropped:
        out.append("")
        out.append(t(lang, "r.dropped_detail", detail=dropped_detail(report, lang)))
    out += [
        "",
        t(lang, "r.fields", ts=s.ts_field, duration=s.duration_field, unit=s.duration_unit,
          key=key_label(report, lang)),
        "",
        t(lang, "r.settings", bucket=report.bucket, tz=report.tz, min_n=report.min_n,
          min_run=report.min_run, ratio=f"{report.min_ratio:g}"),
    ]
    n_short, short_keys = insufficient_summary(report)
    if n_short:
        out += ["", t(lang, "r.insufficient", min_n=report.min_n, n=n_short, keys=", ".join(short_keys))]

    out += ["", f"## {t(lang, 'r.findings')}", ""]
    if report.findings:
        rows = []
        for f in report.findings:
            c = f.change
            rows.append([
                c.key, fmt_bucket(c.at, report.bucket),
                f"{fmt_ms(c.p50_before)} > {fmt_ms(c.p50_after)}",
                f"{fmt_ms(c.p90_before)} > {fmt_ms(c.p90_after)}",
                f"x{fmt_ratio(c.ratio)} ({c.metric})",
                t(lang, f"verdict.{f.verdict}"), where_text(f, lang),
            ])
        headers = [t(lang, k) for k in ("col.key", "col.since", "col.p50", "col.p90", "col.ratio", "col.verdict", "col.where")]
        out += _table(headers, rows)
    else:
        out.append(t(lang, "r.no_findings"))

    out += ["", f"## {t(lang, 'r.observations')}", ""]
    if report.observations:
        rows = []
        for o in report.observations:
            when = fmt_bucket(o.at, report.bucket)
            if o.until != o.at:
                when += " .. " + fmt_bucket(o.until, report.bucket)
            rows.append([o.key, when, t(lang, f"obs.{o.kind}"), f"x{fmt_ratio(o.ratio)} ({o.metric})"])
        out += _table([t(lang, k) for k in ("col.key", "col.when", "col.kind", "col.ratio")], rows)
    else:
        out.append(t(lang, "r.no_observations"))

    out += ["", f"## {t(lang, 'r.stratification')}", ""]
    if not report.findings:
        out.append(t(lang, "r.no_findings"))
    elif not report.dims:
        out.append(t(lang, "r.no_dims"))
    for f in report.findings:
        c = f.change
        out += [f"### {t(lang, 'r.stratify_for', key=c.key, at=fmt_bucket(c.at, report.bucket), metric=c.metric, ratio=fmt_ratio(c.ratio))}", ""]
        for d in f.dims:
            out += [f"**{t(lang, 'r.by_dim', dim=d.dim, verdict=t(lang, f'verdict.{d.verdict}'), reason=t(lang, f'reason.{d.reason}'))}**", ""]
            rows = []
            for cell in d.cells:
                before, after = (
                    (cell.p50_before, cell.p50_after) if d.metric == "p50"
                    else (cell.p90_before, cell.p90_after)
                )
                note = t(lang, "cell.new") if cell.new else (t(lang, "cell.thin") if cell.thin else "")
                rows.append([
                    cell.value, f"{cell.n_before}/{cell.n_after}", f"{fmt_ms(before)} > {fmt_ms(after)}",
                    "-" if cell.ratio is None else f"x{fmt_ratio(cell.ratio)}",
                    f"{fmt_pct(cell.share_before)} > {fmt_pct(cell.share_after)}", note,
                ])
            headers = [t(lang, k) for k in ("col.cell", "col.n", "col.metric", "col.ratio", "col.share", "col.note")]
            headers[2] = d.metric
            out += _table(headers, rows)
            out.append("")
    if report.findings:
        out += [f"_{t(lang, 'r.verdict_legend')}_"]
    return "\n".join(out).rstrip() + "\n"
