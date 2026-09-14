# Provider Connection Diagnostics

The credential console tests one explicitly selected model with a minimal generation request.
Every failure and limited-provider result uses the same safe diagnostic contract regardless of
provider or authentication variant.

## Response contract

The existing `POST /api/credentials/test/{filename}` route remains compatible. Failure responses
retain the legacy string fields `error` and `detail`, but those fields now contain the same safe
summary instead of a raw upstream body. The additive `diagnostic` object is the authoritative
machine-readable contract:

```json
{
  "success": false,
  "status_code": 403,
  "message": "Model test failed.",
  "error": "The credential does not have permission to use this provider resource.",
  "detail": "The credential does not have permission to use this provider resource.",
  "diagnostic": {
    "schema_version": 1,
    "code": "provider_connection_permission",
    "category": "permission",
    "message": "The credential does not have permission to use this provider resource.",
    "remediation": "Review the provider account, project, and model permissions, then retry.",
    "retryable": false,
    "provider_status": 403,
    "provider_code": "permission_error"
  },
  "filename": "claude-platform-example.json",
  "provider": "anthropic",
  "credential_type": "api_key",
  "model": "claude-sonnet-example"
}
```

`provider_status` is present only when an HTTP response was received. `provider_code` is present
only when the provider returned a recognized, non-secret code. Clients must branch on `category`
or `code`, not on human-readable text.

## Categories

| Category | Meaning | Default retry guidance |
| --- | --- | --- |
| `credential` | Missing, expired, or rejected credential | Correct or refresh the credential first |
| `permission` | Authenticated account lacks access | Correct account, project, or model permissions |
| `quota` | Billing or account quota is unavailable | Restore quota or billing before retrying |
| `rate_limit` | Temporary provider rate limit | Wait for reset or use another healthy credential |
| `network` | DNS or outbound connection failure | Check endpoint and outbound connectivity |
| `proxy` | Configured outbound proxy failed | Check proxy address, credentials, and access |
| `tls` | TLS negotiation or certificate failure | Check clock, CA trust, inspection, and endpoint |
| `upstream` | Provider rejected the request or failed | Check provider status/settings; retry only when marked |
| `invalid_model` | Selected model is no longer available | Refresh models and choose an advertised model |
| `unsupported_operation` | Variant does not implement the operation | Use an operation declared by the capability matrix |
| `timeout` | Complete test exceeded its deadline | Check reachability and retry |
| `cancelled` | Console/client cancelled the test | Start another test when ready |
| `internal` | Polaris could not complete the test | Retry once, then inspect local logs |

HTTP 429 proves that the credential reached the provider, so the route preserves the existing
`success: true` connection result while returning a `rate_limit` or `quota` diagnostic and
remediation. It does not claim that inference capacity is currently available.

## Safety and lifecycle

- Raw upstream bodies and exception messages are never returned or persisted by this route.
- Only a small allowlist of common provider error codes is retained; unknown values are discarded.
- Provider HTTP status remains visible without turning untrusted response text into console HTML.
- One 30-second hard deadline covers refresh, request preparation, provider I/O, and the optional
  Code Assist preview probe. Individual adapter timeouts cannot extend the total operation.
- Closing the model-test dialog or pressing Escape aborts the browser request. The server watches
  for the ASGI disconnect, cancels the provider coroutine, and preserves caller cancellation.
- The test route does not add automatic retries, disable credentials, or alter inference retry
  policy. General streaming, timeout ownership, and retry semantics remain P2.4.

## Provider maintenance

Add or change deterministic cases in
`backend/tests/fixtures/provider-connection-errors-v1.json`. The fixture must cover every variant
advertised by the provider capability matrix. Add a provider code to the public allowlist only when
it has stable documented semantics and cannot contain account, request, credential, or free-form
upstream data.
