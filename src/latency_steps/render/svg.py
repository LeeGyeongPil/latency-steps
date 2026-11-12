"""Small-multiples SVG: one panel per key with p50/p90 lines and step markers."""

from __future__ import annotations

import math
from xml.sax.saxutils import escape

from ..i18n import t
from ..model import KeySeries, Report
from .common import fmt_bucket, fmt_ms

PANEL_W, PANEL_H = 380, 190
PAD_L, PAD_R, PAD_T, PAD_B = 52, 12, 26, 28
COLS = 2
HEADER_H = 40
P50_COLOR, P90_COLOR, STEP_COLOR, SPIKE_COLOR = "#2563eb", "#9333ea", "#dc2626", "#d97706"


def _panel(report: Report, ks: KeySeries, ox: float, oy: float, lang: str) -> list[str]:
    out = [f'<g class="panel" data-key="{escape(ks.key)}" transform="translate({ox},{oy})">']
    out.append(f'<rect x="0" y="0" width="{PANEL_W}" height="{PANEL_H}" fill="#ffffff" stroke="#d4d4d8"/>')
    out.append(f'<text x="{PAD_L}" y="16" font-size="13" font-weight="bold">{escape(ks.key)}</text>')
    if not ks.points:
        out.append("</g>")
        return out
    t0, t1 = ks.points[0].bucket.timestamp(), ks.points[-1].bucket.timestamp()
    values = [v for p in ks.points for v in (p.p50, p.p90)]
    lo, hi = math.log(min(values)), math.log(max(values))
    if hi - lo < 1e-6:
        hi = lo + 1.0
    w, h = PANEL_W - PAD_L - PAD_R, PANEL_H - PAD_T - PAD_B

    def x_of(ts: float) -> float:
        return PAD_L + (0.5 if t1 == t0 else (ts - t0) / (t1 - t0)) * w

    def y_of(v: float) -> float:
        return PAD_T + (1 - (math.log(v) - lo) / (hi - lo)) * h

    for name, color, getter in (("p90", P90_COLOR, lambda p: p.p90), ("p50", P50_COLOR, lambda p: p.p50)):
        pts = " ".join(f"{x_of(p.bucket.timestamp()):.1f},{y_of(getter(p)):.1f}" for p in ks.points)
        out.append(f'<polyline class="{name}" fill="none" stroke="{color}" stroke-width="1.6" points="{pts}"/>')
    out.append(f'<text x="{PAD_L - 4}" y="{PAD_T + 4}" font-size="9" text-anchor="end">{escape(fmt_ms(math.exp(hi)))}</text>')
    out.append(f'<text x="{PAD_L - 4}" y="{PAD_T + h}" font-size="9" text-anchor="end">{escape(fmt_ms(math.exp(lo)))}</text>')
    out.append(f'<text x="{PAD_L}" y="{PANEL_H - 10}" font-size="9">{escape(fmt_bucket(ks.points[0].bucket, report.bucket))}</text>')
    out.append(f'<text x="{PANEL_W - PAD_R}" y="{PANEL_H - 10}" font-size="9" text-anchor="end">{escape(fmt_bucket(ks.points[-1].bucket, report.bucket))}</text>')
    for f in report.findings:
        if f.change.key != ks.key:
            continue
        x = x_of(f.change.at.timestamp())
        out.append(
            f'<line class="step" x1="{x:.1f}" y1="{PAD_T}" x2="{x:.1f}" y2="{PAD_T + h}" '
            f'stroke="{STEP_COLOR}" stroke-width="1.4" stroke-dasharray="4 3"/>'
        )
        out.append(
            f'<text x="{x + 3:.1f}" y="{PAD_T + 10}" font-size="9" fill="{STEP_COLOR}">'
            f'{escape(t(lang, "svg.step"))} {escape(fmt_bucket(f.change.at, report.bucket))}</text>'
        )
    by_bucket = {p.bucket: p for p in ks.points}
    for o in report.observations:
        if o.key != ks.key or o.kind == "faster" or o.at not in by_bucket:
            continue
        p = by_bucket[o.at]
        v = p.p50 if o.metric == "p50" else p.p90
        out.append(
            f'<circle class="spike" cx="{x_of(o.at.timestamp()):.1f}" cy="{y_of(v):.1f}" r="3.5" '
            f'fill="{SPIKE_COLOR}"><title>{escape(t(lang, f"obs.{o.kind}"))}</title></circle>'
        )
    out.append("</g>")
    return out


def render_svg(report: Report, lang: str) -> str:
    series = [s for s in report.series if s.points]
    rows = max(1, math.ceil(len(series) / COLS))
    width = COLS * PANEL_W + (COLS + 1) * 10
    header = HEADER_H + (16 if report.synthetic else 0)
    height = header + rows * (PANEL_H + 10) + 22
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="sans-serif">',
        f'<rect width="{width}" height="{height}" fill="#fafafa"/>',
        f'<text x="10" y="22" font-size="15" font-weight="bold">{escape(t(lang, "svg.title"))}</text>',
    ]
    if report.synthetic:
        out.append(f'<text x="10" y="38" font-size="11" fill="{STEP_COLOR}">{escape(t(lang, "svg.synthetic"))}</text>')
    for i, ks in enumerate(series):
        ox = 10 + (i % COLS) * (PANEL_W + 10)
        oy = header + (i // COLS) * (PANEL_H + 10)
        out += _panel(report, ks, ox, oy, lang)
    ly = height - 8
    out.append(
        f'<text x="10" y="{ly}" font-size="10"><tspan fill="{P50_COLOR}">&#9644; {escape(t(lang, "svg.p50"))}</tspan>'
        f'  <tspan fill="{P90_COLOR}">&#9644; {escape(t(lang, "svg.p90"))}</tspan>'
        f'  <tspan fill="{STEP_COLOR}">&#9144; {escape(t(lang, "svg.step"))}</tspan>'
        f'  <tspan fill="{SPIKE_COLOR}">&#9679; {escape(t(lang, "svg.spike"))}</tspan></text>'
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"
