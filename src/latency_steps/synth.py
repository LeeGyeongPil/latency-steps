"""Seeded synthetic log generator behind the ``demo`` command.

This is practice data: the numbers are planted, not a real incident.

Planted behaviour (start 2026-10-01 UTC, 21 days, 4 keys x 4 hosts):

* ``search``  - from day 10 every host is ~2.8x slower            -> global step
* ``embed``   - from day 12 only host ``h3`` is slower            -> localized step
* ``rerank``  - from day 8 concurrency widens from 1-4 to 1-12 and
                concurrency >= 8 is slow, hosts stay equal          -> load-mix shift
* ``chat``    - one slow day (day 5), otherwise flat              -> spike, not a step
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

START = datetime(2026, 10, 1, tzinfo=timezone.utc)
DAYS = 21
HOSTS = ("h1", "h2", "h3", "h4")
KEYS = ("search", "embed", "rerank", "chat")
SIGMA = 0.35  # log-normal spread of every key

# Planted days (0-based offsets from START) used by tests and the README.
SEARCH_STEP_DAY = 10
RERANK_STEP_DAY = 8
EMBED_STEP_DAY = 12
CHAT_SPIKE_DAY = 5


def _median_seconds(key: str, day: int, host: str, concurrency: int) -> float:
    if key == "search":
        return 1.2 if day < SEARCH_STEP_DAY else 3.4
    if key == "embed":
        return 1.5 if (day >= EMBED_STEP_DAY and host == "h3") else 0.3
    if key == "rerank":
        return 1.6 if concurrency >= 8 else 0.5
    return 2.4 if day == CHAT_SPIKE_DAY else 0.8


def write_logs(path: Path | str, seed: int = 7, per_hour: int = 40) -> int:
    """Write the synthetic JSONL log to ``path`` and return the row count."""
    if per_hour < 1:
        raise ValueError("per_hour must be at least 1")
    rng = random.Random(seed)
    rows = 0
    with open(path, "w", encoding="utf-8", newline="\n") as out:
        for day in range(DAYS):
            for hour in range(24):
                stamp = (START + timedelta(days=day, hours=hour)).strftime("%Y-%m-%dT%H:")
                lines = []
                for _ in range(per_hour):
                    sec = rng.randrange(3600)
                    host = rng.choice(HOSTS)
                    key = rng.choice(KEYS)
                    concurrency = rng.randint(1, 4) if day < RERANK_STEP_DAY else rng.randint(1, 12)
                    median = _median_seconds(key, day, host, concurrency)
                    ms = round(rng.lognormvariate(0.0, SIGMA) * median * 1000, 1)
                    lines.append(
                        f'{{"ts":"{stamp}{sec // 60:02d}:{sec % 60:02d}Z","duration_ms":{ms},'
                        f'"tool":"{key}","host":"{host}","concurrency":{concurrency}}}\n'
                    )
                out.writelines(lines)
                rows += per_hour
    return rows
