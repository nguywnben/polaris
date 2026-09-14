# Streaming Lifecycle Contract

Polaris applies one bounded lifecycle to OpenAI Chat, OpenAI Responses, Anthropic Messages,
Gemini, Vertex OpenAI, and Vertex Gemini streams. The contract covers provider streams, protocol
adapters, optional anti-truncation continuation, quota reservations, credential leases, and request
traces.

## State and retry rules

1. Before model output starts, configured retryable statuses, connection failures, and read
   timeouts may retry within the existing limit. An SSE comment heartbeat does not count as model
   output.
2. Once any data event has been exposed to the client, ordinary retry and credential switching are
   prohibited. A timeout, provider exception, error response, invalid frame, or premature EOF is a
   terminal stream failure.
3. Anti-truncation may issue its explicit continuation request only after a clean EOF without its
   completion marker. It includes the bounded accumulated prefix and requests only the missing
   suffix. A read exception after output is not eligible for continuation.
4. Success is recorded only after a terminal provider event: `[DONE]`, a concrete Gemini
   `finishReason`, or terminal prompt-block feedback. OpenAI Responses additionally requires the
   Chat adapter's `[DONE]` marker before emitting `response.completed`.
5. Client cancellation closes every nested iterator. Credential leases and quota reservations are
   released, no fallback quota estimate is committed, and the request trace is persisted once with
   outcome `cancelled`.

## Timeout ownership

- HTTPX owns connection, write, pool, and read-inactivity timeouts through the existing upstream
  timeout setting. Its streaming response context always closes the connection.
- Vertex bounds the initial `wreq.post` operation with `asyncio.timeout` and gives `wreq` the same
  read-inactivity timeout. Active long streams may continue; stalled reads cannot remain open
  indefinitely.
- A timeout before output remains retry-eligible. A timeout after output emits a protocol-native
  in-stream error and is never retried.

## Memory bounds

| Boundary | Limit | Failure behavior |
| --- | ---: | --- |
| Upstream newline-delimited frame | 1 MiB | Reject as upstream protocol failure |
| Vertex incomplete JSON frame | 1 MiB | Reject as upstream protocol failure |
| Responses Chat SSE frame | 1 MiB | Emit Responses `error`; never emit `response.completed` |
| Responses accumulated final output | 8 MiB | Emit Responses `error` |
| Stream-to-non-stream collection | 8 MiB | Return HTTP 502 |
| Anti-truncation accumulated prefix | 8 MiB | Stop continuation and emit an error event |

Transport reads use 64 KiB chunks. Vertex retains incomplete UTF-8 bytes until the next chunk so a
multibyte character split by the transport is preserved exactly.

## Protocol behavior

SSE data frames and comment heartbeats are normalized with a blank-line terminator. A provider
failure discovered after headers are committed is encoded in the public protocol's existing error
event rather than starting a second HTTP response. Anthropic failures stay `event: error`; OpenAI
Chat and Gemini end after their error event; Responses emits `error` and does not claim completion.

## Operator diagnosis

The existing request trace answers the production questions without storing prompts or output:

- Did the stream complete, fail upstream, time out, or get cancelled?
- Was retry scheduled before output, or suppressed after output began?
- Were usage, quota reservation, credential lease, and trace settlement reached exactly once?

Use the public `X-Request-ID` to find the trace. Relevant decisions are `retry/scheduled`,
`retry/skipped`, `upstream/succeeded`, `upstream/failed`, `usage/recorded`, and the final outcome.

## Authoritative references

- [Starlette responses](https://www.starlette.io/responses/)
- [Starlette release notes](https://www.starlette.io/release-notes/)
- [HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/)
- [HTTPX async streaming](https://www.python-httpx.org/async/#streaming-responses)
- [Python asyncio cancellation and timeouts](https://docs.python.org/3/library/asyncio-task.html)
- [OpenAI Chat streaming](https://platform.openai.com/docs/api-reference/chat/create)
- [OpenAI Responses streaming events](https://platform.openai.com/docs/api-reference/responses-streaming/response/refusal?lang=python)
- [Anthropic streaming Messages](https://platform.claude.com/docs/en/build-with-claude/streaming)
- [Gemini text streaming](https://ai.google.dev/gemini-api/docs/text-generation#generate-a-text-stream)
- [wreq API](https://python.wreq.org/en/latest/api/wreq/)
