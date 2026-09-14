# Quota, budget, or capacity exhaustion

1. Identify whether the signal is quota, budget, rate limit, cooldown, or no eligible capacity.
2. Inspect the virtual key on **Access** and the provider route on **Overview**. Keep tenant limits
   distinct from provider credential limits.
3. For budget denials, validate pricing and actual usage before changing a limit. For rate limits,
   respect `Retry-After` and add healthy credentials or routes instead of creating retry storms.
4. Use request traces to verify reservation release/commit and fallback behavior.
5. Record any emergency limit increase with an owner and expiry, then revert it after recovery.
