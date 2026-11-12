"""English / Korean message catalogs and language resolution.

All user-facing text lives in ``MESSAGES``; code elsewhere passes message
codes and parameters. Language order: ``--lang`` > ``LATENCY_STEPS_LANG`` >
``LC_ALL`` / ``LC_MESSAGES`` / ``LANG`` (a value starting with ``ko`` selects
Korean, anything else English).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

LANGS = ("en", "ko")
ENV_VAR = "LATENCY_STEPS_LANG"

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        # --- command line help ---
        "usage": "usage: ",
        "help.description": "Find when latency stepped up in raw event logs, then see whether the step is one host, a load-mix shift, or everything.",
        "help.epilog": "Exit codes: 0 ok, 1 step found (with --fail-on-step), 2 input or option error.",
        "help.lang": "interface language (en or ko); also LATENCY_STEPS_LANG",
        "help.version": "show the version and exit",
        "help.analyze": "analyze a JSONL or CSV event log (use - for standard input)",
        "help.demo": "analyze built-in synthetic practice data (no input needed)",
        "help.path": "log file: .jsonl/.ndjson/.csv, optionally .gz or .zst; - reads standard input",
        "help.ts": "timestamp field (default: first of ts, timestamp, time, ...)",
        "help.duration": "duration field (default: first of duration_ms, latency_ms, duration, ...)",
        "help.duration_unit": "unit of bare duration numbers: ms, s or us (default: from the field name, else ms); values like 12ms or 1.2s carry their own unit",
        "help.key": "field to keep one series per value of, e.g. endpoint or tool (default: one series)",
        "help.by": "dimension to stratify by; repeatable. A field (host) or numeric ranges (concurrency:1-3,4-7,8+)",
        "help.bucket": "time bucket: hour, day or auto (day when the log spans 14+ days)",
        "help.min_n": "minimum rows per bucket; thinner buckets are left out of the series (default 30)",
        "help.min_run": "a step must last at least this many buckets (default 3)",
        "help.min_ratio": "a step must change p50 or p90 by at least this factor (default 1.2)",
        "help.metric": "percentile series to inspect: p50, p90 or both (default both)",
        "help.tz": "timezone for buckets, e.g. UTC or Asia/Seoul (default UTC)",
        "help.only": "analyze only this key; repeatable",
        "help.memory_limit": "DuckDB memory limit (default 1GB)",
        "help.format": "output format: table, md, svg or json (default table)",
        "help.out": "write the report to this file instead of standard output",
        "help.fail_on_step": "exit with code 1 when at least one step is found",
        "help.threshold": "detection threshold of the split statistic (advanced)",
        "help.demo_seed": "random seed of the synthetic log (default 7)",
        "help.demo_per_hour": "synthetic rows per hour over 21 days (default 40, about 20,000 rows)",
        "help.demo_save": "also save the synthetic log to this JSONL file",
        "help.help": "show this help message and exit",
        "help.positionals": "positional arguments",
        "help.options": "options",
        "demo.label": "demo (seed {seed}, {days} days, {per_hour}/hour)",
        "argp.invalid_choice": "argument {arg}: invalid choice {value} (choose from {choices})",
        "argp.invalid_number": "argument {arg}: invalid number {value}",
        "argp.expected_one": "argument {arg}: expected one value",
        "argp.required": "the following arguments are required: {names}",
        "argp.unrecognized": "unrecognized arguments: {names}",
        "err.empty_input": "the file is empty: no non-blank lines found. Check that the file has content.",
        # --- errors ---
        "err.prefix": "error",
        "err.file_not_found": "input file not found: {path}. Check the path, or pass - to read standard input.",
        "err.field_not_found": "could not find the {what} field. Fields seen: {seen}. Name it with the matching option.",
        "err.bad_unit": "unknown duration unit '{value}'. Use ms, s or us.",
        "err.bad_timezone": "unknown timezone '{value}'. Use a name such as UTC or Asia/Seoul.",
        "err.bad_bucket": "unknown bucket '{value}'. Use hour, day or auto.",
        "err.bad_number": "invalid value {value} for {name}.",
        "err.bad_metric": "unknown metric '{value}'. Use p50, p90 or both.",
        "err.bad_by": "cannot read --by '{spec}'. Use a field name (host) or ranges (concurrency:1-3,4-7,8+).",
        "err.bad_field_name": "field name '{name}' is empty or contains a quote or backslash.",
        "err.bad_memory_limit": "invalid memory limit '{value}'. Use for example 512MB or 2GB.",
        "err.no_rows": "no usable rows: {rows} read, all dropped. Check --ts ({ts}) and --duration ({duration}) against your file.",
        "err.no_such_key": "no series for --only {keys}. Check the key spelling.",
        "err.out_write": "cannot write {path}: {reason}",
        # --- report: header ---
        "r.synthetic": "SYNTHETIC PRACTICE DATA - the numbers are planted, not a real incident.",
        "r.title": "Latency step report",
        "r.input": "Input: {source} - {rows_read} rows read, {rows_kept} kept, dropped rows {dropped}",
        "r.dropped_detail": "dropped: {detail}",
        "r.drop.invalid_record": "unparseable line {n}",
        "r.drop.bad_timestamp": "bad timestamp {n}",
        "r.drop.bad_duration": "bad duration {n}",
        "r.fields": "Fields: timestamp={ts}, duration={duration} ({unit}), key={key}",
        "r.key_none": "(none)",
        "r.settings": "Buckets: {bucket} ({tz}), min rows {min_n}, step lasts {min_run}+ buckets, change x{ratio}+",
        "r.insufficient": "Buckets skipped for having fewer than {min_n} rows: {n} ({keys})",
        # --- report: sections ---
        "r.findings": "Findings",
        "r.findings_hint": "sustained steps",
        "r.no_findings": "No sustained step found.",
        "r.observations": "Observations",
        "r.observations_hint": "worth a look, not a sustained step",
        "r.no_observations": "None.",
        "r.stratification": "Stratification",
        "r.stratify_for": "{key}: step at {at} ({metric} x{ratio})",
        "r.by_dim": "by {dim}: {verdict} - {reason}",
        "r.no_dims": "No --by dimension given, so steps are not stratified. Add for example --by host.",
        "r.verdict_legend": "Verdicts are heuristics: read them together with the cell tables.",
        # --- report: columns ---
        "col.key": "key",
        "col.since": "since",
        "col.p50": "p50 before > after",
        "col.p90": "p90 before > after",
        "col.ratio": "ratio",
        "col.metric": "metric",
        "col.verdict": "verdict",
        "col.where": "where",
        "col.when": "when",
        "col.kind": "kind",
        "col.cell": "cell",
        "col.n": "rows before/after",
        "col.share": "share before > after",
        "col.note": "note",
        "cell.new": "new",
        "cell.thin": "too few rows",
        # --- observations ---
        "obs.spike": "brief spike",
        "obs.tail": "recent shift (too short to call a step)",
        "obs.faster": "got faster",
        # --- verdicts ---
        "verdict.localized": "localized",
        "verdict.mix_shift": "mix shift",
        "verdict.global": "global",
        "verdict.inconclusive": "inconclusive",
        "verdict.not_stratified": "not stratified",
        "verdict_long.localized": "only part of the traffic got slower",
        "verdict_long.mix_shift": "cells are flat but the traffic mix changed",
        "verdict_long.global": "nearly every cell got slower",
        "verdict_long.inconclusive": "no clear pattern or too few rows",
        "verdict_long.not_stratified": "no dimension requested",
        "reason.few_cells": "only a minority of cells got slower",
        "reason.new_cell": "a cell that did not exist before appeared",
        "reason.composition": "cells are flat but their shares changed",
        "reason.most_cells": "most cells got slower",
        "reason.too_few_samples": "not enough rows per cell",
        "reason.no_pattern": "no clear pattern",
        "where.localized": "{dim} = {cells}",
        "where.mix_shift_new": "{dim}: new {cells}",
        "where.mix_shift_composition": "{dim}: mix of {cells} changed",
        "where.global": "all cells",
        "where.inconclusive": "-",
        "where.not_stratified": "-",
        # --- one-line summary (JSON) ---
        "summary.finding": "{key}: {metric} went from {before} to {after} (x{ratio}) starting {at}; verdict {verdict}.",
        "summary.none": "No sustained latency step found.",
        # --- svg ---
        "svg.title": "Percentile series per key",
        "svg.p50": "p50",
        "svg.p90": "p90",
        "svg.step": "step",
        "svg.spike": "spike",
        "svg.synthetic": "synthetic practice data",
    },
    "ko": {
        "usage": "사용법: ",
        "help.description": "원시 이벤트 로그에서 지연이 계단처럼 오른 시점을 찾고, 그 계단이 한 호스트인지, 부하 구성 변화인지, 전체인지 가려 줍니다.",
        "help.epilog": "종료 코드: 0 정상, 1 계단 발견(--fail-on-step 사용 시), 2 입력·옵션 오류.",
        "help.lang": "화면 언어(en 또는 ko), 환경 변수 LATENCY_STEPS_LANG 도 사용 가능",
        "help.version": "버전을 보여 주고 끝냅니다",
        "help.analyze": "JSONL 또는 CSV 이벤트 로그를 분석합니다(표준 입력은 -)",
        "help.demo": "내장 합성 연습 데이터를 분석합니다(입력 파일 불필요)",
        "help.path": "로그 파일: .jsonl/.ndjson/.csv, .gz·.zst 압축도 가능, - 는 표준 입력",
        "help.ts": "시각 필드(기본: ts, timestamp, time 등 중 처음 발견한 것)",
        "help.duration": "지연 시간 필드(기본: duration_ms, latency_ms, duration 등 중 처음 발견한 것)",
        "help.duration_unit": "단위 없는 숫자의 단위: ms, s, us(기본: 필드 이름에서 추정, 없으면 ms). 12ms, 1.2s 처럼 단위가 붙은 값은 그대로 해석",
        "help.key": "값마다 계열을 따로 만들 필드(예: endpoint, tool). 기본은 계열 하나",
        "help.by": "층화할 차원, 여러 번 지정 가능. 필드(host) 또는 숫자 구간(concurrency:1-3,4-7,8+)",
        "help.bucket": "시간 버킷: hour, day, auto(로그가 14일 이상이면 day)",
        "help.min_n": "버킷당 최소 행 수, 적은 버킷은 계열에서 뺍니다(기본 30)",
        "help.min_run": "계단은 이 버킷 수 이상 이어져야 합니다(기본 3)",
        "help.min_ratio": "계단은 p50 또는 p90 이 이 배수 이상 바뀌어야 합니다(기본 1.2)",
        "help.metric": "검사할 백분위 계열: p50, p90, both(기본 both)",
        "help.tz": "버킷 시간대, 예: UTC, Asia/Seoul(기본 UTC)",
        "help.only": "이 키만 분석합니다, 여러 번 지정 가능",
        "help.memory_limit": "DuckDB 메모리 상한(기본 1GB)",
        "help.format": "출력 형식: table, md, svg, json(기본 table)",
        "help.out": "표준 출력 대신 이 파일에 보고서를 씁니다",
        "help.fail_on_step": "계단이 하나라도 있으면 종료 코드 1로 끝냅니다",
        "help.threshold": "분할 통계량 임계값(고급)",
        "help.demo_seed": "합성 로그의 난수 시드(기본 7)",
        "help.demo_per_hour": "21일 동안 시간당 합성 행 수(기본 40, 약 2만 행)",
        "help.demo_save": "합성 로그를 이 JSONL 파일로도 저장합니다",
        "help.help": "도움말을 보여 주고 끝냅니다",
        "help.positionals": "위치 인자",
        "help.options": "옵션",
        "demo.label": "demo (시드 {seed}, {days}일, 시간당 {per_hour}건)",
        "argp.invalid_choice": "인자 {arg}: 허용되지 않는 값 {value} (선택 가능: {choices})",
        "argp.invalid_number": "인자 {arg}: 숫자가 올바르지 않습니다 {value}",
        "argp.expected_one": "인자 {arg}: 값이 하나 필요합니다",
        "argp.required": "다음 인자가 필요합니다: {names}",
        "argp.unrecognized": "알 수 없는 인자: {names}",
        "err.empty_input": "파일이 비어 있습니다: 내용이 있는 줄이 없습니다. 파일에 내용이 있는지 확인하세요.",
        "err.prefix": "오류",
        "err.file_not_found": "입력 파일을 찾을 수 없습니다: {path}. 경로를 확인하거나 표준 입력은 - 를 쓰세요.",
        "err.field_not_found": "{what} 필드를 찾지 못했습니다. 로그에서 본 필드: {seen}. 해당 옵션으로 이름을 지정하세요.",
        "err.bad_unit": "알 수 없는 단위 '{value}'. ms, s, us 중 하나를 쓰세요.",
        "err.bad_timezone": "알 수 없는 시간대 '{value}'. UTC, Asia/Seoul 같은 이름을 쓰세요.",
        "err.bad_bucket": "알 수 없는 버킷 '{value}'. hour, day, auto 중 하나를 쓰세요.",
        "err.bad_number": "{name} 값 {value} 이(가) 올바르지 않습니다.",
        "err.bad_metric": "알 수 없는 지표 '{value}'. p50, p90, both 중 하나를 쓰세요.",
        "err.bad_by": "--by '{spec}' 을(를) 해석할 수 없습니다. 필드 이름(host) 또는 구간(concurrency:1-3,4-7,8+)을 쓰세요.",
        "err.bad_field_name": "필드 이름 '{name}' 이(가) 비었거나 따옴표·역슬래시를 포함합니다.",
        "err.bad_memory_limit": "메모리 상한 '{value}' 이(가) 올바르지 않습니다. 예: 512MB, 2GB.",
        "err.no_rows": "쓸 수 있는 행이 없습니다: {rows}행을 읽었지만 모두 버려졌습니다. --ts({ts}), --duration({duration}) 이 파일과 맞는지 확인하세요.",
        "err.no_such_key": "--only {keys} 에 해당하는 계열이 없습니다. 키 철자를 확인하세요.",
        "err.out_write": "{path} 에 쓸 수 없습니다: {reason}",
        "r.synthetic": "연습용 합성 데이터 - 숫자는 일부러 심어 둔 것이며 실제 장애가 아닙니다.",
        "r.title": "지연 계단 보고서",
        "r.input": "입력: {source} - {rows_read}행 읽음, {rows_kept}행 사용, 버린 행 {dropped}",
        "r.dropped_detail": "버린 이유: {detail}",
        "r.drop.invalid_record": "해석 못 한 줄 {n}",
        "r.drop.bad_timestamp": "시각 오류 {n}",
        "r.drop.bad_duration": "지연 시간 오류 {n}",
        "r.fields": "필드: 시각={ts}, 지연={duration} ({unit}), 키={key}",
        "r.key_none": "(없음)",
        "r.settings": "버킷: {bucket} ({tz}), 최소 행 {min_n}, 계단은 {min_run}버킷 이상, 변화 x{ratio} 이상",
        "r.insufficient": "행이 {min_n}개 미만이라 건너뛴 버킷: {n}개 ({keys})",
        "r.findings": "결론(Findings)",
        "r.findings_hint": "지속된 계단",
        "r.no_findings": "지속된 계단을 찾지 못했습니다.",
        "r.observations": "관찰(Observations)",
        "r.observations_hint": "눈여겨볼 것, 지속된 계단은 아님",
        "r.no_observations": "없음.",
        "r.stratification": "층화(Stratification)",
        "r.stratify_for": "{key}: {at} 부터의 계단 ({metric} x{ratio})",
        "r.by_dim": "{dim} 기준: {verdict} - {reason}",
        "r.no_dims": "--by 차원을 주지 않아 층화하지 않았습니다. 예: --by host 를 추가하세요.",
        "r.verdict_legend": "판정은 휴리스틱입니다. 칸별 표와 함께 읽으세요.",
        "col.key": "키",
        "col.since": "시작",
        "col.p50": "p50 전 > 후",
        "col.p90": "p90 전 > 후",
        "col.ratio": "배수",
        "col.metric": "지표",
        "col.verdict": "판정",
        "col.where": "범위",
        "col.when": "시점",
        "col.kind": "종류",
        "col.cell": "칸",
        "col.n": "행 수 전/후",
        "col.share": "구성비 전 > 후",
        "col.note": "비고",
        "cell.new": "신규",
        "cell.thin": "행 부족",
        "obs.spike": "잠깐 튐",
        "obs.tail": "최근 변화(계단이라 하기엔 짧음)",
        "obs.faster": "빨라짐",
        "verdict.localized": "일부 한정",
        "verdict.mix_shift": "구성 변화",
        "verdict.global": "전체",
        "verdict.inconclusive": "판단 보류",
        "verdict.not_stratified": "층화 안 함",
        "verdict_long.localized": "트래픽 일부만 느려졌습니다",
        "verdict_long.mix_shift": "칸별로는 평평한데 트래픽 구성이 바뀌었습니다",
        "verdict_long.global": "거의 모든 칸이 느려졌습니다",
        "verdict_long.inconclusive": "뚜렷한 패턴이 없거나 행이 부족합니다",
        "verdict_long.not_stratified": "요청한 차원이 없습니다",
        "reason.few_cells": "소수의 칸만 느려졌습니다",
        "reason.new_cell": "이전에 없던 칸이 새로 생겼습니다",
        "reason.composition": "칸별 값은 평평하지만 구성비가 바뀌었습니다",
        "reason.most_cells": "대부분의 칸이 느려졌습니다",
        "reason.too_few_samples": "칸별 행이 부족합니다",
        "reason.no_pattern": "뚜렷한 패턴이 없습니다",
        "where.localized": "{dim} = {cells}",
        "where.mix_shift_new": "{dim}: 신규 {cells}",
        "where.mix_shift_composition": "{dim}: {cells} 구성 변화",
        "where.global": "모든 칸",
        "where.inconclusive": "-",
        "where.not_stratified": "-",
        "summary.finding": "{key}: {metric} 이(가) {before} 에서 {after} 로 (x{ratio}) {at} 부터 올랐습니다. 판정: {verdict}.",
        "summary.none": "지속된 지연 계단을 찾지 못했습니다.",
        "svg.title": "키별 백분위 시계열",
        "svg.p50": "p50",
        "svg.p90": "p90",
        "svg.step": "계단",
        "svg.spike": "튐",
        "svg.synthetic": "연습용 합성 데이터",
    },
}


def resolve_lang(cli_value: str | None = None, env: Mapping[str, str] | None = None) -> str:
    """Pick ``"en"`` or ``"ko"``: ``--lang`` > ``LATENCY_STEPS_LANG`` > ``LC_ALL``/``LC_MESSAGES``/``LANG``."""
    import os

    env = os.environ if env is None else env
    if cli_value in LANGS:
        return cli_value  # type: ignore[return-value]
    candidates = [env.get(ENV_VAR)]
    if not (env.get(ENV_VAR) or "").strip():
        candidates = [env.get("LC_ALL"), env.get("LC_MESSAGES"), env.get("LANG")]
    for value in candidates:
        value = (value or "").strip().lower()
        if not value:
            continue
        return "ko" if value.startswith("ko") else "en"
    return "en"


def scan_lang_argv(argv: Sequence[str]) -> str | None:
    """Find ``--lang X`` / ``--lang=X`` anywhere in ``argv`` (before argparse runs)."""
    for i, arg in enumerate(argv):
        if arg == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--lang="):
            return arg.split("=", 1)[1]
    return None


def t(lang: str, key: str, /, **params: object) -> str:
    """Translate ``key`` into ``lang`` (falls back to English) and fill ``params``."""
    table = MESSAGES.get(lang, MESSAGES["en"])
    text = table.get(key) or MESSAGES["en"][key]
    return text.format(**params) if params else text
