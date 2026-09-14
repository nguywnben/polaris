"""Lightweight token estimation for request budgeting and usage hints."""

from __future__ import annotations

import math
from typing import Any, Dict

MAX_ESTIMATION_NODES = 1_000_000


class TokenEstimationError(ValueError):
    """Raised when a payload cannot be estimated safely and deterministically."""


def _string_tokens(value: str) -> int:
    return max(1, math.ceil(len(value.encode("utf-8", errors="replace")) / 4))


def _estimate_value(value: Any) -> int:
    total = 0
    nodes = 0
    active_containers: set[int] = set()
    stack: list[tuple[bool, Any]] = [(False, value)]

    while stack:
        exiting, current = stack.pop()
        if exiting:
            active_containers.remove(id(current))
            continue

        nodes += 1
        if nodes > MAX_ESTIMATION_NODES:
            raise TokenEstimationError("Token estimation node limit exceeded.")

        if isinstance(current, str):
            total += _string_tokens(current)
            continue
        if isinstance(current, dict):
            container_id = id(current)
            if container_id in active_containers:
                raise TokenEstimationError("Cyclic request payload cannot be estimated.")
            active_containers.add(container_id)
            total += 2 + (300 if current.get("type") == "image" or "inlineData" in current else 0)
            stack.append((True, current))
            for key, item in reversed(tuple(current.items())):
                total += _string_tokens(str(key))
                stack.append((False, item))
            continue
        if isinstance(current, list):
            container_id = id(current)
            if container_id in active_containers:
                raise TokenEstimationError("Cyclic request payload cannot be estimated.")
            active_containers.add(container_id)
            total += 1 + len(current)
            stack.append((True, current))
            for item in reversed(current):
                stack.append((False, item))
            continue
        if current is not None:
            total += 1

    return total


def estimate_input_tokens(payload: Dict[str, Any]) -> int:
    """Estimate serialized prompt tokens without a provider tokenizer dependency."""
    return max(1, _estimate_value(payload))
