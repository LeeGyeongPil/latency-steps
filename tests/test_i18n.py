"""AC-8: UI language selection, catalogs with identical keys."""

from __future__ import annotations

import re

import pytest

from latency_steps.cli import main
from latency_steps.i18n import MESSAGES, resolve_lang, scan_lang_argv, t
from latency_steps.render.jsonout import build_json
from latency_steps.render.table import display_width, render_table


def _placeholders(text: str) -> list[str]:
    return sorted(re.findall(r"\{(\w+)\}", text))


def test_lang_resolution_and_catalogs(capsys, demo_report):
    # --lang beats LATENCY_STEPS_LANG beats LC_ALL / LC_MESSAGES / LANG.
    env = {"LATENCY_STEPS_LANG": "ko", "LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"}
    assert resolve_lang("en", env) == "en"
    assert resolve_lang(None, env) == "ko"
    assert resolve_lang(None, {"LATENCY_STEPS_LANG": "en", "LANG": "ko_KR.UTF-8"}) == "en"
    assert resolve_lang(None, {"LC_ALL": "ko_KR.UTF-8", "LANG": "en_US.UTF-8"}) == "ko"
    assert resolve_lang(None, {"LC_MESSAGES": "ko_KR.UTF-8", "LANG": "en_US.UTF-8"}) == "ko"
    assert resolve_lang(None, {"LANG": "ko_KR.UTF-8"}) == "ko"
    assert resolve_lang(None, {"LANG": "fr_FR.UTF-8"}) == "en"
    assert resolve_lang(None, {}) == "en"
    assert scan_lang_argv(["analyze", "--lang=ko"]) == "ko"
    assert scan_lang_argv(["--lang", "en", "demo"]) == "en"

    # Both catalogs have the same keys and the same placeholders.
    assert set(MESSAGES["en"]) == set(MESSAGES["ko"])
    for key in MESSAGES["en"]:
        assert _placeholders(MESSAGES["en"][key]) == _placeholders(MESSAGES["ko"][key]), key

    # Help text really switches.
    for lang, marker in (("en", "log file"), ("ko", "로그 파일")):
        with pytest.raises(SystemExit) as info:
            main(["--lang", lang, "analyze", "--help"])
        assert info.value.code == 0
        assert marker in capsys.readouterr().out

    # Table headers switch too; JSON keys stay English, only the summary text changes.
    en, ko = render_table(demo_report, "en"), render_table(demo_report, "ko")
    assert "verdict" in en and "판정" not in en
    assert "판정" in ko
    j_en, j_ko = build_json(demo_report, "en"), build_json(demo_report, "ko")
    assert j_en.keys() == j_ko.keys()
    assert j_en["findings"][0]["verdict"] == j_ko["findings"][0]["verdict"]
    assert j_en["summary"] != j_ko["summary"]


def test_env_var_selects_language_for_the_cli(monkeypatch, capsys):
    monkeypatch.setenv("LATENCY_STEPS_LANG", "ko")
    assert main(["demo", "--only", "chat"]) == 0
    assert "지연 계단 보고서" in capsys.readouterr().out
    monkeypatch.setenv("LATENCY_STEPS_LANG", "en")
    assert main(["--lang", "ko", "demo", "--only", "chat"]) == 0
    assert "지연 계단 보고서" in capsys.readouterr().out


def test_unknown_language_falls_back_to_english_and_width_counts_hangul():
    assert t("fr", "r.title") == MESSAGES["en"]["r.title"]
    assert display_width("판정") == 4 and display_width("ab") == 2


def test_korean_help_and_argument_errors_are_translated(capsys):
    # Q-3: no English argparse boilerplate in Korean help.
    for argv in (["--lang", "ko", "--help"], ["--lang", "ko", "analyze", "--help"], ["--lang", "ko", "demo", "--help"]):
        with pytest.raises(SystemExit) as info:
            main(argv)
        assert info.value.code == 0
        out = capsys.readouterr().out
        for english in ("positional arguments", "options:", "show this help", "usage:"):
            assert english not in out, (argv, english)
        assert "위치 인자" in out or "옵션" in out

    cases = (
        (["--lang", "ko", "demo", "--bucket", "week"], "허용되지 않는 값"),
        (["--lang", "ko", "demo", "--min-n", "abc"], "숫자가 올바르지 않습니다"),
        (["--lang", "ko"], "다음 인자가 필요합니다"),
        (["--lang", "ko", "demo", "--nope"], "알 수 없는 인자"),
        (["--lang", "ko", "demo", "--seed"], "값이 하나 필요합니다"),
    )
    for argv, expected in cases:
        with pytest.raises(SystemExit) as info:
            main(argv)
        assert info.value.code == 2
        err = capsys.readouterr().err
        assert expected in err and "오류" in err, argv
        assert "invalid" not in err and "required" not in err and "unrecognized" not in err

    # English stays English and exits 2 as well.
    with pytest.raises(SystemExit) as info:
        main(["--lang", "en", "demo", "--bucket", "week"])
    assert info.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_demo_label_is_translated(capsys):
    assert main(["--lang", "ko", "demo", "--only", "chat", "--format", "json"]) == 0
    source = __import__("json").loads(capsys.readouterr().out)["input"]["source"]
    assert "시드" in source and "seed 7," not in source
    assert main(["--lang", "en", "demo", "--only", "chat", "--format", "json"]) == 0
    assert "seed 7" in __import__("json").loads(capsys.readouterr().out)["input"]["source"]
