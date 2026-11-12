"""Errors carrying a message code and parameters so the CLI can translate them."""

from __future__ import annotations

from typing import Any


class LatencyStepsError(Exception):
    """A user-fixable problem (bad input, bad option). The CLI maps it to exit code 2."""

    def __init__(self, code: str, **params: Any) -> None:
        self.code = code
        self.params = params
        super().__init__(f"{code}: {params}" if params else code)
