# High request error rate

1. Open **Overview → Operational health** and identify affected routes and outcomes.
2. Pivot to **Observability → Request traces** for recent failing requests; do not begin with raw
   logs.
3. Separate client errors and policy denials from upstream failures. For upstream failures, inspect
   provider cooldown, credential health, and fallback decisions.
4. Disable only the affected credential or route when a healthy fallback exists. Avoid fleet-wide
   mutations during an active incident.
5. Confirm the error ratio remains below threshold for two alert windows before resolving.

Rollback: restore the prior provider or quality-policy revision from the audited management change
record if the incident began after a configuration mutation.
