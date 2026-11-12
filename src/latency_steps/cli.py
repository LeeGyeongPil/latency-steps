"""Command line entry point: ``latency-steps analyze|demo``."""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
import typing
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .analysis import Options, analyze
from .errors import LatencyStepsError
from .i18n import LANGS, resolve_lang, scan_lang_argv, t
from .model import Report
from .render.jsonout import render_json
from .render.markdown import render_markdown
from .render.svg import render_svg
from .render.table import render_table
from .synth import DAYS, write_logs

FORMATS = ("table", "md", "svg", "json")
DEMO_BY = ["host", "concurrency:1-3,4-7,8+"]
EXIT_OK, EXIT_STEP, EXIT_ERROR = 0, 1, 2


def _formatter(lang: str) -> type[argparse.HelpFormatter]:
    class Formatter(argparse.HelpFormatter):
        def add_usage(self, usage, actions, groups, prefix=None):  # type: ignore[no-untyped-def]
            # An explicit empty prefix is used by argparse to build sub-command names.
            return super().add_usage(usage, actions, groups, t(lang, "usage") if prefix is None else prefix)

    return Formatter


_ARGPARSE_PATTERNS = (
    (r"argument (.+?): invalid choice: (.+?) \(choose from (.+)\)$", "argp.invalid_choice", ("arg", "value", "choices")),
    (r"argument (.+?): invalid (?:int|float) value: (.+)$", "argp.invalid_number", ("arg", "value")),
    (r"argument (.+?): expected one argument$", "argp.expected_one", ("arg",)),
    (r"the following arguments are required: (.+)$", "argp.required", ("names",)),
    (r"unrecognized arguments: (.+)$", "argp.unrecognized", ("names",)),
)


def translate_argparse_error(lang: str, message: str) -> str:
    """Map the common argparse error texts to the catalog; unknown texts stay as they are."""
    if lang == "en":
        return message
    for regex, key, names in _ARGPARSE_PATTERNS:
        match = re.match(regex, message)
        if match:
            return t(lang, key, **dict(zip(names, match.groups())))
    return message


def _parser_class(lang: str) -> type[argparse.ArgumentParser]:
    class Parser(argparse.ArgumentParser):
        def error(self, message: str) -> typing.NoReturn:
            self.print_usage(sys.stderr)
            text = translate_argparse_error(lang, message)
            self.exit(EXIT_ERROR, f"{self.prog}: {t(lang, 'err.prefix')}: {text}\n")

    return Parser


def _localize_help(p: argparse.ArgumentParser, lang: str) -> None:
    """Add a translated -h/--help and translate the section titles."""
    p.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS, help=t(lang, "help.help"))
    p._positionals.title = t(lang, "help.positionals")  # type: ignore[attr-defined]
    p._optionals.title = t(lang, "help.options")  # type: ignore[attr-defined]


def _add_common(p: argparse.ArgumentParser, lang: str) -> None:
    """Options shared by ``analyze`` and ``demo``."""
    p.add_argument("--by", action="append", default=None, metavar="DIM", help=t(lang, "help.by"))
    p.add_argument("--bucket", default="auto", choices=("hour", "day", "auto"), help=t(lang, "help.bucket"))
    p.add_argument("--min-n", type=int, default=30, metavar="N", help=t(lang, "help.min_n"))
    p.add_argument("--min-run", type=int, default=3, metavar="N", help=t(lang, "help.min_run"))
    p.add_argument("--min-ratio", type=float, default=1.2, metavar="X", help=t(lang, "help.min_ratio"))
    p.add_argument("--metric", default="both", choices=("p50", "p90", "both"), help=t(lang, "help.metric"))
    p.add_argument("--tz", default="UTC", metavar="ZONE", help=t(lang, "help.tz"))
    p.add_argument("--only", action="append", default=None, metavar="KEY", help=t(lang, "help.only"))
    p.add_argument("--memory-limit", default="1GB", metavar="SIZE", help=t(lang, "help.memory_limit"))
    p.add_argument("--format", default="table", choices=FORMATS, help=t(lang, "help.format"))
    p.add_argument("--out", default=None, metavar="FILE", help=t(lang, "help.out"))
    p.add_argument("--fail-on-step", action="store_true", help=t(lang, "help.fail_on_step"))
    p.add_argument("--threshold", type=float, default=6.0, help=argparse.SUPPRESS)
    p.add_argument("--lang", choices=LANGS, default=argparse.SUPPRESS, help=t(lang, "help.lang"))


def build_parser(lang: str) -> argparse.ArgumentParser:
    fmt = _formatter(lang)
    cls = _parser_class(lang)
    parser = cls(
        prog="latency-steps", description=t(lang, "help.description"),
        epilog=t(lang, "help.epilog"), formatter_class=fmt, add_help=False,
    )
    _localize_help(parser, lang)
    parser.add_argument("--lang", choices=LANGS, default=None, help=t(lang, "help.lang"))
    parser.add_argument("--version", action="version", version=f"latency-steps {__version__}",
                        help=t(lang, "help.version"))
    sub = parser.add_subparsers(dest="command", required=True, parser_class=cls)

    a = sub.add_parser("analyze", help=t(lang, "help.analyze"), description=t(lang, "help.analyze"),
                       epilog=t(lang, "help.epilog"), formatter_class=fmt, add_help=False)
    _localize_help(a, lang)
    a.add_argument("path", help=t(lang, "help.path"))
    a.add_argument("--ts", default=None, metavar="FIELD", help=t(lang, "help.ts"))
    a.add_argument("--duration", default=None, metavar="FIELD", help=t(lang, "help.duration"))
    a.add_argument("--duration-unit", default=None, choices=("ms", "s", "us"), help=t(lang, "help.duration_unit"))
    a.add_argument("--key", default=None, metavar="FIELD", help=t(lang, "help.key"))
    _add_common(a, lang)

    d = sub.add_parser("demo", help=t(lang, "help.demo"), description=t(lang, "help.demo"),
                       epilog=t(lang, "help.epilog"), formatter_class=fmt, add_help=False)
    _localize_help(d, lang)
    d.add_argument("--seed", type=int, default=7, help=t(lang, "help.demo_seed"))
    d.add_argument("--per-hour", type=int, default=40, metavar="N", help=t(lang, "help.demo_per_hour"))
    d.add_argument("--save", default=None, metavar="FILE", help=t(lang, "help.demo_save"))
    _add_common(d, lang)
    return parser


def _options(args: argparse.Namespace, *, demo: bool) -> Options:
    if demo:
        return Options(
            ts="ts", duration="duration_ms", duration_unit="ms", key="tool",
            by=args.by if args.by is not None else list(DEMO_BY), bucket=args.bucket,
            min_n=args.min_n, min_run=args.min_run, min_ratio=args.min_ratio,
            metric=args.metric, tz=args.tz, only=args.only or [],
            memory_limit=args.memory_limit, threshold=args.threshold,
        )
    return Options(
        ts=args.ts, duration=args.duration, duration_unit=args.duration_unit, key=args.key,
        by=args.by or [], bucket=args.bucket, min_n=args.min_n, min_run=args.min_run,
        min_ratio=args.min_ratio, metric=args.metric, tz=args.tz, only=args.only or [],
        memory_limit=args.memory_limit, threshold=args.threshold,
    )


def render(report: Report, fmt: str, lang: str) -> str:
    if fmt == "md":
        return render_markdown(report, lang)
    if fmt == "svg":
        return render_svg(report, lang)
    if fmt == "json":
        return render_json(report, lang)
    return render_table(report, lang)


def _run_demo(args: argparse.Namespace, lang: str) -> Report:
    opts = _options(args, demo=True)
    if args.per_hour < 1:
        raise LatencyStepsError("bad_number", name="--per-hour", value=args.per_hour)
    label = t(lang, "demo.label", seed=args.seed, days=DAYS, per_hour=args.per_hour)
    if args.save:
        write_logs(args.save, args.seed, args.per_hour)
        return analyze(args.save, opts, synthetic=True, label=label)
    with tempfile.TemporaryDirectory(prefix="latency-steps-demo-") as tmp:
        path = Path(tmp) / "demo.jsonl"
        write_logs(path, args.seed, args.per_hour)
        return analyze(str(path), opts, synthetic=True, label=label)


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    lang = resolve_lang(scan_lang_argv(argv))
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    parser = build_parser(lang)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            report = _run_demo(args, lang)
        else:
            report = analyze(args.path, _options(args, demo=False))
        text = render(report, args.format, lang)
        if args.out:
            try:
                Path(args.out).write_text(text, encoding="utf-8")
            except OSError as exc:
                raise LatencyStepsError("out_write", path=args.out, reason=exc.strerror or str(exc)) from exc
        else:
            sys.stdout.write(text)
    except LatencyStepsError as exc:
        print(f"{t(lang, 'err.prefix')}: {t(lang, 'err.' + exc.code, **exc.params)}", file=sys.stderr)
        return EXIT_ERROR
    if args.fail_on_step and report.findings:
        return EXIT_STEP
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
