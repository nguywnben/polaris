# Unknown model pricing

1. Identify the requested model and virtual key pricing policy from **Access** and request traces.
2. Check `pricing.dynamic_state` and `pricing.dynamic_last_error` from
   `GET /api/usage/aggregated`. If sync is unavailable or the provider does not publish the model,
   add a reviewed price to `model_pricing.json`, select an explicit bounded fallback price, or keep
   the default deny policy. Do not silently allow unpriced hard-budget traffic.
3. Exercise a small request and verify estimated and actual cost settlement.
4. Confirm the `pricing_denied` or `pricing_warned` counter stops increasing. Both policies reject
   unknown pricing when a hard budget is present; `warn` additionally writes a bounded warning log.

Each override is expressed in USD per one million tokens. `input` and `output` are required;
`cache_read`, `cache_creation`, and `reasoning` are optional and fall back to the corresponding
normal input or output price when omitted:

```json
{
  "provider-model-id": {
    "input": 3.0,
    "output": 15.0,
    "cache_read": 0.3,
    "cache_creation": 3.75,
    "reasoning": 15.0
  }
}
```
