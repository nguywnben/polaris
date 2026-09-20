# GroqCloud, DeepSeek Platform, Mistral AI Studio and Cerebras Cloud

All four use API keys, not OAuth. Select the provider on **Providers**, paste its
key, and save. **Advanced settings** contains only the endpoint for that key.
Leave it blank for the official default. JSON/ZIP imports and downloadable JSON
templates are available in the same workspace; imported credentials remain
unverified until catalog discovery in the credential pool.

| Name | Provider ID in JSON | Default endpoint |
| --- | --- | --- |
| GroqCloud | `groq` | `https://api.groq.com/openai/v1` |
| DeepSeek Platform | `deepseek` | `https://api.deepseek.com/v1` |
| Mistral AI Studio | `mistral` | `https://api.mistral.ai/v1` |
| Cerebras Cloud | `cerebras` | `https://api.cerebras.ai/v1` |

The credential JSON uses `provider`, `api_key` and optional `base_url` and
`credential_label`. Use the UI template; do not put real keys in repository files.
Only trusted HTTPS vendor hosts are accepted, with redirects disabled.

Discovery calls `/models`, not paid inference. Test a selected model explicitly
in the credential pool or Playground after discovery. Catalog visibility is not
proof of inference permission. Streaming and non-streaming client responses use
the existing bounded upstream stream and collection path, routing and retries.
No vendor key or billable request was used during implementation.

## Supported boundary and deliberate limits

- Chat text, model-supported image inputs, and declared function tools; one
  response candidate. No embeddings, speech, batch, files, hosted agents/tools,
  OAuth, quota simulation or arbitrary proxy hosts.
- Groq discovery excludes known speech models, Prompt Guard and Compound hosted
  agent systems, as well as inactive entries. Future vendor catalog changes may
  require new filters. Mistral requires `capabilities.completion_chat: true` and
  excludes archived models. Catalogs remain dynamic, not a hardcoded availability list.
- Groq and DeepSeek request streaming usage explicitly. Mistral and Cerebras do
  not receive that undocumented option. Usage is reported only when supplied;
  Groq `x_groq.usage` and `x_groq.error` are handled as well as standard usage.
- These four adapters reject explicit Chat `reasoning_effort`; public Chat
  also rejects `reasoning_content` request history. The separate
  [Chat reasoning extension](../protocol-translation-contract.md#chat-reasoning-extension)
  supports selected Google/OpenAI transports, not native vendor parity here. DeepSeek defaults to
  `thinking: {type: disabled}` and Mistral to `reasoning_effort: none` for
  replay-safe translated chat. Canonical histories already containing thoughts
  retain them; their continuation uses enabled/high reasoning respectively.
  Explicit unsupported Gemini generation options fail instead of being dropped.
- Mistral thinking/text chunks are decoded; invalid content fails closed. Tool
  IDs not already nine alphanumeric characters are mapped to paired per-request
  wire IDs without mutating the source conversation. Its seed uses `random_seed`.
- Cerebras image URL support is vendor-specific: its current contract requires
  base64 PNG/JPEG data URIs, not external URLs. Tool plus structured-output support
  also depends on model. Upstream rejection is surfaced, not silently retried with
  those options removed. Function/vision/JSON support must be checked for the
  model selected; discovery alone does not advertise those capabilities.

## Sources checked on 2026-09-15

- [Groq compatibility](https://console.groq.com/docs/openai),
  [catalog](https://console.groq.com/docs/models),
  [stream schema](https://github.com/groq/groq-python/blob/main/src/groq/types/chat/chat_completion_chunk.py).
- [DeepSeek API](https://api-docs.deepseek.com/),
  [thinking and history](https://api-docs.deepseek.com/guides/thinking_mode/).
- [Mistral chat](https://docs.mistral.ai/api/endpoint/chat),
  [models](https://docs.mistral.ai/api/endpoint/models),
  [reasoning chunks](https://docs.mistral.ai/studio/conversations/reasoning).
- [Cerebras compatibility](https://inference-docs.cerebras.ai/resources/openai).

The user-approved logos are local PNGs. Groq and DeepSeek were rendered from their
official favicon SVGs; Mistral uses the supplied white glyph on Studio blue;
Cerebras retains its original 144×144 favicon. No SVG source is shipped for these
four assets. DeepSeek's monochrome mark switches contrast with the theme.
