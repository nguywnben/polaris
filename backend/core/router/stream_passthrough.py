from typing import Any, AsyncIterator

from core.router.protocol_errors import (
    ProtocolName,
    adapt_protocol_error_response,
)
from fastapi import Response
from fastapi.responses import StreamingResponse
from log import log


async def close_async_iterator(iterator: AsyncIterator[Any]) -> None:
    """Close an async iterator when it exposes the standard ``aclose`` hook."""
    close = getattr(iterator, "aclose", None)
    if close is not None:
        await close()


class ManagedStreamingResponse(StreamingResponse):
    """Streaming response that closes its body after completion or disconnect."""

    async def stream_response(self, send) -> None:
        try:
            await super().stream_response(send)
        finally:
            await close_async_iterator(self.body_iterator)


def sse_heartbeat_bytes(item: Any) -> bytes | None:
    """Normalize an upstream SSE comment without treating it as model output."""
    if not isinstance(item, (str, bytes)):
        return None
    raw = item if isinstance(item, bytes) else item.encode("utf-8")
    comment = raw.strip()
    if not comment.startswith(b":"):
        return None
    return comment + b"\n\n"


async def cascade_close_async_iterator(
    iterator: AsyncIterator[Any], owned_iterators: list[AsyncIterator[Any]]
):
    """Ensure nested provider iterators close with their public wrapper."""
    try:
        async for item in iterator:
            yield item
    finally:
        candidates = [iterator, *reversed(owned_iterators)]
        seen: set[int] = set()
        for candidate in candidates:
            if id(candidate) in seen:
                continue
            seen.add(id(candidate))
            try:
                await close_async_iterator(candidate)
            except Exception as exc:
                # Cleanup continues so one faulty wrapper cannot strand its provider stream.
                log.debug(f"Provider stream cleanup failed ({type(exc).__name__}).")
                continue


async def prepend_async_item(first_item: Any, iterator: AsyncIterator[Any]):
    """Yield a prefetched item before continuing the original iterator."""
    try:
        yield first_item
        async for item in iterator:
            yield item
    finally:
        await close_async_iterator(iterator)


async def read_first_async_item(iterator: AsyncIterator[Any]) -> Any:
    """Python 3.9-compatible async equivalent of built-in anext()."""
    return await iterator.__anext__()


async def build_streaming_response_or_error(
    iterator: AsyncIterator[Any],
    media_type: str = "text/event-stream",
    error_protocol: ProtocolName | None = None,
):
    """
    Prefetch the first async item so router code can return an upstream error
    response directly before FastAPI commits a 200 streaming response.
    """
    try:
        first_item = await read_first_async_item(iterator)
    except StopAsyncIteration:
        return Response(status_code=204)

    if isinstance(first_item, Response):
        await close_async_iterator(iterator)
        if error_protocol:
            return adapt_protocol_error_response(first_item, error_protocol)
        return first_item

    return ManagedStreamingResponse(
        prepend_async_item(first_item, iterator),
        media_type=media_type,
    )
