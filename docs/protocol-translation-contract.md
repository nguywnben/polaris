# Protocol Translation Contract

Polaris accepts five advertised public ingress families and routes them through a canonical
Gemini-shaped request/response boundary. The versioned contract is defined by
`backend/tests/fixtures/protocol-contract-corpus-v1.json`; request and response examples are locked
by the adjacent `protocol-request-golden-v1.json` and `protocol-response-golden-v1.json` fixtures.

## Public families

| Family | Public surface | Translation boundary |
| --- | --- | --- |
| OpenAI Chat Completions | `/v1/chat/completions` and Vertex OpenAI alias | OpenAI Chat to canonical Gemini |
| OpenAI Responses | `/v1/responses` | Responses to Chat, then canonical Gemini |
| Anthropic Messages | `/v1/messages` | Anthropic Messages to canonical Gemini |
| Gemini native | `/v1beta/models/*` | Native canonical request/response |
| Vertex | `/vertex/v1*` | Native Gemini or OpenAI-to-Gemini, according to the path |

Every conversion classifies text, image input, system instructions, tools, structured output,
reasoning control/output, usage, finish reasons, and normalized errors as `supported`, `translated`,
or `rejected`. A provider's eligibility for a family remains defined by the separate
[provider capability contract](provider-capabilities.md).

## Model discovery

`GET /v1/models` and `GET /v1beta/models` advertise the discovered provider catalog and
enabled configured virtual aliases, deduplicated in discovery order. They do not synthesize
`fake-streaming/` or `streaming-anti-truncation/` copies. Provider-returned model variants
remain unchanged. Response envelopes and authentication are unchanged.

The feature prefixes remain accepted by inference routes as explicit advanced opt-ins;
existing saved IDs do not need migration. Clients that populate pickers exclusively from
discovery must enter these IDs manually to select the modes. No automatic mode selection
or new discovery parameter is introduced.

## Fail-closed request rules

- Unknown top-level request fields and unknown typed content/config fields return HTTP 400 using
  the endpoint's native error envelope.
- OpenAI Chat and Responses image translation currently accepts data URLs. Remote URL/file inputs
  are rejected instead of disappearing from the prompt.
- OpenAI `developer` messages become canonical system instructions. Responses `text.format` and
  Chat `response_format` preserve text, JSON object, and JSON-schema intent.
- Anthropic base64 images, tool history, signed thinking blocks, `thinking` control, and
  `output_config.format` JSON schema are translated. A `redacted_thinking` request block cannot be
  represented safely and is rejected.
- The additive `chat-reasoning-v1` extension accepts nullable Chat `reasoning_effort`:
  `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`. It is resolved after model/provider
  selection, separately on each fallback attempt. The original R1 corpus is unchanged.
  Responses `reasoning` controls and Chat `reasoning_content` history remain rejected.
- Unsupported tool/content types return a bounded validation error; they are never serialized into
  prompt text or silently skipped.

## Chat reasoning extension

Gemini text models on Antigravity, AI Studio and the Vertex Chat alias receive native
`generationConfig.thinkingConfig`. Gemini 2.5 maps minimal/low to 1,024, medium to 8,192 and high
to 24,576 thinking tokens. `none` maps to zero only on 2.5 Flash/Flash-Lite. Known Gemini 3 families
use their supported thinking levels; 3.1 Pro maps minimal to low per Google's compatibility API.
Gemini 3.7/3.8 Flash only accept low/medium/high; 3 Pro accepts low/high. Unknown families,
specialized image/audio/live models and unsupported levels fail explicitly rather than being guessed.

`none` on Gemini 2.5 Pro or Gemini 3 returns HTTP 400 explaining that the model cannot disable
reasoning. No automatic downgrade, omission or retry without the requested control occurs.
OpenAI Platform forwards `reasoning_effort` unchanged; Codex forwards `reasoning.effort`. Those
upstreams validate model-specific support. Other provider adapters currently return an explicit
unsupported-control error; this extension does not claim universal vendor reasoning parity.
Omitting the field retains existing defaults.

Effort is part of the response cache key. Internal intent is removed before provider serialization;
the content-free trace records `request.applied` with the requested effort reason code. Rejected
translations release the credential without marking it unhealthy.

Tiếng Việt: Polaris chuyển mức reasoning theo đúng model/nhà cung cấp đã chọn. Nếu model không
cho tắt reasoning, `none` trả lỗi 400 rõ ràng, không tự đổi sang `low` hay bỏ tham số. Không gửi
tham số thì giữ hành vi mặc định. Nhà cung cấp chưa có ánh xạ an toàn vẫn báo không hỗ trợ.

## Response rules

- Chat Completions accepts nullable `stream_options`; a non-null object requires
  `stream: true`. The supported option is the boolean `include_usage` (default false).
  Unknown options remain rejected rather than silently ignored.
- With `include_usage: true`, ordinary chunks carry `usage: null` and one separate chunk
  with `choices: []` carries the latest reported usage immediately before `[DONE]`.
  Without it, usage is omitted from streaming chunks. Missing upstream usage is not
  invented; interrupted/error streams need not emit a final usage chunk. Continuation
  attempts sum their last cumulative snapshots without double-counting intermediate frames.
  These rules also apply to fake streaming and the Vertex OpenAI alias.

- Gemini thought parts map to OpenAI `reasoning_content`, Responses reasoning summary items, and
  Anthropic thinking blocks with the official `signature` field.
- Tool calls, text, generated inline images, and supported code-execution parts remain visible in
  translated output. An unknown upstream part fails with a normalized HTTP 502 rather than
  returning a deceptively empty or partial response.
- Gemini `promptTokenCount` already includes cached content. OpenAI input/prompt totals therefore
  retain it while exposing `cached_tokens` as detail. Gemini thoughts are added to OpenAI or
  Anthropic output totals once, not zero or twice.
- `MAX_TOKENS` maps to OpenAI `length`, Responses `incomplete/max_output_tokens`, and Anthropic
  `max_tokens`. Safety/recitation maps to OpenAI `content_filter`, Responses
  `incomplete/content_filter`, and Anthropic `refusal`.

## Native errors

Validation, authentication, translation, and upstream failures use the public protocol's existing
OpenAI, Anthropic, or Gemini error envelope. Translation failures are HTTP 502 because the accepted
client request could not be represented from the upstream response; messages remain bounded and
redacted by the common error adapter.

## Maintainer workflow

When a protocol field or content type changes:

1. update the explicit Pydantic boundary and conversion logic together;
2. update the versioned feature matrix if its disposition changes;
3. add or revise one shared golden fixture before changing behavior;
4. verify both the direct converter and the public protocol error envelope; and
5. preserve the immutable R1 compatibility fixture or use the accepted change-control process.

Streaming frame lifecycle, disconnect propagation, timeout ownership, retry eligibility, and
bounded aggregation are defined by the separate [streaming lifecycle contract](streaming-lifecycle.md).

## Authoritative references

- [OpenAI Chat Completions API](https://developers.openai.com/api/reference/resources/chat)
- [OpenAI Responses create API](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
- [Anthropic Messages API](https://platform.claude.com/docs/en/api/http/messages/create)
- [Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Gemini GenerateContent API](https://ai.google.dev/api/generate-content)
- [Gemini OpenAI reasoning mapping](https://ai.google.dev/gemini-api/docs/openai#thinking)
- [Gemini thinking capabilities](https://ai.google.dev/gemini-api/docs/thinking)
- [Vertex AI generative API reference](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rpc/google.cloud.aiplatform.v1)
