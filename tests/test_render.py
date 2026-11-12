"""AC-7: Markdown and SVG reports."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from latency_steps.render.markdown import render_markdown
from latency_steps.render.svg import render_svg

NS = {"s": "http://www.w3.org/2000/svg"}


def test_markdown_and_svg(demo_report):
    md = render_markdown(demo_report, "en")
    assert "## Findings" in md and "## Observations" in md and "## Stratification" in md
    assert "| cell |" in md and "| 8+ |" in md and "new" in md
    assert "SYNTHETIC PRACTICE DATA" in md
    # Every table row has the same number of columns as its header.
    tables = [b for b in md.split("\n\n") if b.startswith("| ")]
    assert tables
    for block in tables:
        counts = {line.count("|") for line in block.splitlines()}
        assert len(counts) == 1

    svg = render_svg(demo_report, "en")
    root = ET.fromstring(svg)  # must be well-formed XML
    panels = root.findall(".//s:g[@class='panel']", NS)
    assert sorted(p.get("data-key") for p in panels) == ["chat", "embed", "rerank", "search"]
    assert len(root.findall(".//s:line[@class='step']", NS)) == len(demo_report.findings) == 3
    assert len(root.findall(".//s:circle[@class='spike']", NS)) == 1
    # One step marker lives inside the matching key's panel.
    for panel in panels:
        steps = panel.findall("s:line[@class='step']", NS)
        assert len(steps) == (0 if panel.get("data-key") == "chat" else 1)


def test_svg_labels_follow_language(demo_report):
    assert "Percentile series per key" in render_svg(demo_report, "en")
    assert "키별 백분위 시계열" in render_svg(demo_report, "ko")
