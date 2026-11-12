# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-12

### Added
- `latency-steps analyze`: raw JSONL / CSV logs (optionally `.gz` / `.zst`, or standard input) to per-key p50 / p90 time series with a minimum-sample guard.
- Step detection on log-scale series by robust binary segmentation (pure Python), with `--min-run` and `--min-ratio` instead of a penalty value. Brief spikes, trailing shifts and speed-ups are reported as observations, not findings.
- Stratification of the windows before and after each step by `--by` dimensions (fields or numeric ranges) with `localized`, `mix_shift`, `global` and `inconclusive` verdicts and an evidence table per dimension.
- `latency-steps demo`: seeded synthetic practice log with planted steps, a one-host regression, a load-mix shift and a one-day spike.
- Output as terminal table, Markdown, SVG and JSON (`schema_version` 1); exit codes 0 / 1 (`--fail-on-step`) / 2.
- English and Korean interface (`--lang`, `LATENCY_STEPS_LANG`, `LC_ALL` / `LC_MESSAGES` / `LANG`).
