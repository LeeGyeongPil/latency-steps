# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.2] - 2026-11-23

### Fixed
- JSONL lines with invalid UTF-8 bytes (plain, `.gz` and standard input) no longer abort the run with a traceback and exit code 1. They are counted as dropped rows with the reason `invalid UTF-8` and the remaining rows are analysed as before. Each bad line is counted once.
- JSONL lines the reader rejects for other reasons (a raw `0x1F` byte, a line over the 2 MB line limit) are now counted as `unparseable line` instead of aborting with a traceback.
- Input DuckDB cannot read at all (for example mixed line endings) now ends with a one-line localized error and exit code 2 instead of a traceback and exit code 1.

### Known issues
- CSV rows with invalid UTF-8 bytes are still skipped without being counted in the dropped-rows summary (JSONL is fixed, see above).

## [0.1.1] - 2026-11-13

### Fixed
- CSV files with a UTF-8 byte order mark (Excel "CSV UTF-8", Windows PowerShell exports) are read correctly; the first column name was not recognised before (plain, `.gz` and standard input).

### Known issues
- The screenshots `demo-table` and `dropped-rows` still show the version line `0.1.0`; they will be re-taken in a later release.
- Rows with invalid UTF-8 bytes are not yet counted in the dropped-rows summary.

## [0.1.0] - 2026-11-12

### Added
- `latency-steps analyze`: raw JSONL / CSV logs (optionally `.gz` / `.zst`, or standard input) to per-key p50 / p90 time series with a minimum-sample guard.
- Step detection on log-scale series by robust binary segmentation (pure Python), with `--min-run` and `--min-ratio` instead of a penalty value. Brief spikes, trailing shifts and speed-ups are reported as observations, not findings.
- Stratification of the windows before and after each step by `--by` dimensions (fields or numeric ranges) with `localized`, `mix_shift`, `global` and `inconclusive` verdicts and an evidence table per dimension.
- `latency-steps demo`: seeded synthetic practice log with planted steps, a one-host regression, a load-mix shift and a one-day spike.
- Output as terminal table, Markdown, SVG and JSON (`schema_version` 1); exit codes 0 / 1 (`--fail-on-step`) / 2.
- English and Korean interface (`--lang`, `LATENCY_STEPS_LANG`, `LC_ALL` / `LC_MESSAGES` / `LANG`).
