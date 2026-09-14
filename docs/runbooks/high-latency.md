# High request latency

1. Confirm P95 rather than a single slow trace and compare route rows on **Overview**.
2. Inspect trace decisions for retries, fallbacks, compression, cooldown waits, and upstream time.
3. Check provider capacity and local Ollama host health. Do not reduce output limits or disable
   quality controls globally without validating output quality.
4. Prefer routing traffic away from one degraded provider. Revert when P95 is stable for two alert
   windows.
