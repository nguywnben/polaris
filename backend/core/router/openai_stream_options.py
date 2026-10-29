"""Apply Chat Completions usage framing to internal, converted SSE events."""

import json
from typing import Any, AsyncIterator

from core.router.stream_passthrough import close_async_iterator
from fastapi import Response


def sum_attempt_usage(snapshots: list[dict]) -> dict:
    """Sum final cumulative snapshots across continuation attempts, including details."""
    total = {}
    for snapshot in snapshots:
        for key, value in snapshot.items():
            if isinstance(value, dict):
                total[key] = sum_attempt_usage([total.get(key, {}), value])
            else:
                total[key] = total.get(key, 0) + value
    return total


async def apply_stream_options(iterator: AsyncIterator[Any], *, include_usage: bool):
    # Upstreams report cumulative snapshots, not deltas. Retain only the latest.
    usage = None
    envelope = None
    failed = False
    tool_choices = set()
    try:
        async for item in iterator:
            if isinstance(item, Response):
                failed = True
                yield item
                continue
            text = item.decode("utf-8") if isinstance(item, bytes) else item
            if text.strip() == "data: [DONE]":
                if include_usage and usage is not None and envelope is not None and not failed:
                    final = {**envelope, "choices": [], "usage": usage}
                    yield f"data: {json.dumps(final)}\n\n".encode()
                yield b"data: [DONE]\n\n"
                return
            if not text.startswith("data: "):
                yield item  # Preserve heartbeat comments.
                continue
            payload = json.loads(text[6:])
            if "error" in payload:
                failed = True
                yield item
                continue
            if payload.get("object") != "chat.completion.chunk":
                yield item
                continue
            if envelope is None:
                envelope = {key: payload[key] for key in ("id", "object", "created", "model")}
            snapshot = payload.pop("usage", None)
            if snapshot is not None:
                usage = snapshot
            if not payload.get("choices"):
                continue  # Usage is sent exactly once, immediately before DONE.
            for choice in payload["choices"]:
                index = choice.get("index", 0)
                if choice.get("delta", {}).get("tool_calls"):
                    tool_choices.add(index)
                if choice.get("finish_reason") == "stop" and index in tool_choices:
                    choice["finish_reason"] = "tool_calls"
            if any(c.get("finish_reason") == "error" for c in payload["choices"]):
                failed = True
            if include_usage:
                payload["usage"] = None
            yield f"data: {json.dumps(payload)}\n\n".encode()
    finally:
        await close_async_iterator(iterator)
