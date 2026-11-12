"""AC-3: stratification verdicts match the planted scenarios and show Simpson's paradox."""

from __future__ import annotations

import pytest

from latency_steps.errors import LatencyStepsError
from latency_steps.model import GLOBAL, INCONCLUSIVE, LOCALIZED, MIX_SHIFT, Cell
from latency_steps.stratify import _verdict, parse_dim


def _finding(report, key):
    return next(f for f in report.findings if f.change.key == key)


def _dim(finding, name):
    return next(d for d in finding.dims if d.dim == name)


def test_verdicts_match_scenarios(demo_report):
    search = _finding(demo_report, "search")
    assert search.verdict == GLOBAL

    embed = _finding(demo_report, "embed")
    assert embed.verdict == LOCALIZED and embed.verdict_dim == "host"
    assert embed.focus == ["h3"]

    rerank = _finding(demo_report, "rerank")
    assert rerank.verdict == MIX_SHIFT and rerank.verdict_dim == "concurrency"
    by_conc = _dim(rerank, "concurrency")
    top = next(c for c in by_conc.cells if c.value == "8+")
    assert top.new is True and top.n_before == 0
    # Simpson's paradox: every host looks slower, no concurrency level got slower.
    host_ratios = [c.ratio for c in _dim(rerank, "host").cells]
    conc_ratios = [c.ratio for c in by_conc.cells if c.ratio is not None]
    assert host_ratios and all(r >= 1.2 for r in host_ratios)
    assert conc_ratios and all(r < 1.1 for r in conc_ratios)


def test_cells_carry_evidence(demo_report):
    cell = _dim(_finding(demo_report, "embed"), "host").cells[0]
    assert cell.n_before > 0 and cell.n_after > 0
    assert 0 < cell.share_before < 1 and 0 < cell.share_after < 1


def _cell(name, ratio, nb=100, na=100, sb=0.5, sa=0.5, new=False, thin=False):
    return Cell(name, nb, na, 1.0, 1.0, 1.0, 1.0, sb, sa, ratio, new, thin)


def test_verdict_rules():
    assert _verdict([_cell("a", 2.0), _cell("b", 1.0), _cell("c", 1.0)], 1.2)[0] == LOCALIZED
    assert _verdict([_cell("a", 2.0), _cell("b", 1.9), _cell("c", 2.1)], 1.2)[0] == GLOBAL
    assert _verdict([_cell("a", 1.0, sb=0.8, sa=0.4), _cell("b", 1.0, sb=0.2, sa=0.6)], 1.2) == (
        MIX_SHIFT, "composition", ["a", "b"],
    )
    assert _verdict([_cell("a", 1.0), _cell("b", None, nb=0, new=True)], 1.2)[0] == MIX_SHIFT
    assert _verdict([_cell("a", 2.0), _cell("b", 1.0)], 1.2)[0] == LOCALIZED  # one of two
    half = [_cell("a", 2.0), _cell("b", 2.0), _cell("c", 1.0), _cell("d", 1.0)]
    assert _verdict(half, 1.2)[0] == INCONCLUSIVE  # half and half is no pattern
    assert _verdict([_cell("a", None, thin=True)], 1.2)[0] == INCONCLUSIVE


def test_thin_cells_are_left_out_of_the_verdict():
    cells = [_cell("a", 2.0), _cell("b", 1.0), _cell("c", None, nb=3, na=4, thin=True)]
    assert _verdict(cells, 1.2)[0] == LOCALIZED


def test_parse_dim_specs():
    assert parse_dim("host", 0).bins is None
    spec = parse_dim("concurrency:1-3,4-7,8+", 1)
    assert [b[0] for b in spec.bins] == ["1-3", "4-7", "8+"]
    assert spec.bins[2][2] is None
    for bad in ("", "x:", "x:a-b", "x:5-2", ":1-3"):
        with pytest.raises(LatencyStepsError):
            parse_dim(bad, 0)


def test_many_categories_collapse_into_other(tmp_path):
    from latency_steps.analysis import Options, analyze

    lines = []
    for day in range(10):
        for i in range(60):
            slow = 5.0 if day >= 5 else 1.0
            lines.append(
                f'{{"ts":"2026-10-{day + 1:02d}T{i % 24:02d}:00:00Z","duration_ms":{100 * slow + i % 3},'
                f'"user":"u{i % 25}"}}'
            )
    path = tmp_path / "many.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = analyze(str(path), Options(by=["user"], min_n=10, bucket="day"))
    assert len(report.findings) == 1
    values = [c.value for c in report.findings[0].dims[0].cells]
    assert len(values) == 21 and values[-1] == "(other)"
