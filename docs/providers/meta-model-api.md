# Meta Model API

Select **Meta Model API** on Providers and enter a Model API key from
[Meta](https://dev.meta.ai/docs/authentication). This is not a Muse Code subscription
or a browser-session integration. The provider uses `https://api.meta.ai/v1` and
authenticated model discovery; discovery does not generate a paid completion.

JSON/ZIP import, credential editing, export and explicit connection tests use the
same workflows as other API-key providers. Model tests can incur vendor charges.
The supplied logo is stored as `meta-model-api.png`.

## Models and privacy

Supported coding models are Muse Spark 1.1, 1.2 and 1.3, including the explicitly
named 1.2/1.3 Contributor variants when returned for the key. Image-generation and
speech-transcription model families are not exposed as text routes.

Choose a Contributor model deliberately: Meta says its prompts and completions
may be used for training. Polaris does not substitute a Contributor model for a
Standard model. If configuring the virtual `polaris` route, review each selected
model, including fallback candidates. See [Meta's model tiers](https://dev.meta.ai/docs/models).

## Client protocols

Use a **Polaris virtual key** in client configuration, not the upstream Meta key.
The Responses base URL for a local installation is `http://127.0.0.1:4283/v1`;
the Anthropic base URL is `http://127.0.0.1:4283`.

- Responses supports text/image input, function tools and streaming, structured
  text output, reasoning effort/summary, assistant phase and encrypted reasoning
  replay. Set `store: false` and request `include: ["reasoning.encrypted_content"]`
  when retaining reasoning history. Only an all-Meta virtual route can replay
  Meta reasoning. Replay complete output items and matching function results.
- `max` reasoning requires Standard `muse-spark-1.3`; it is not available for
  Contributor. Other supported efforts are minimal, low, medium, high and xhigh.
- Chat Completions and Anthropic Messages support the existing text/function-tool
  translation subset. **Full Claude Code compatibility is not claimed**: adaptive
  thinking, Anthropic encrypted reasoning replay, tool search and deferred tools
  are not implemented in this integration. Do not enable `ENABLE_TOOL_SEARCH=true`
  for requests through Polaris. Unsupported fields are rejected, not ignored.
- Stored conversations, `previous_response_id`, hosted tools/files, background jobs,
  audio/video/PDF requests, image generation and transcription are outside scope.

Native Responses still uses Polaris authentication, virtual-key limits, routing,
guardrails, usage accounting and cancellation. Encrypted history is not pruned by
the canonical history compressor. If a guardrail rewrites the policy-visible
mirror (for example PII masking), the request fails closed instead of sending a
different, unmasked native payload. New requests always use upstream `store: false`.

These contracts were checked against public Meta documentation on 2026-09-15:
[Responses](https://dev.meta.ai/docs/protocols/responses),
[Messages](https://dev.meta.ai/docs/protocols/messages) and
[reasoning](https://dev.meta.ai/docs/reasoning). Automated tests use synthetic
credentials and mocked upstream responses. A successful live Meta completion has
not been verified without an operator-supplied key.
