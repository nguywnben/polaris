# Model pricing and cost coverage

Polaris estimates token costs; it is not a subscription billing system. Retail API
equivalent estimates for Antigravity, Muse Code or other subscription providers
are not the account's actual invoice. Inference model IDs are never rewritten by
pricing configuration.

## Resolution

1. Exact operator `provider/model` price in `model_pricing.json`.
2. Legacy unqualified operator price (longest hyphen-boundary prefix).
3. Exact provider-qualified LiteLLM catalog entry.
4. Explicit provider-scoped, one-hop alias; resolve its target using manual,
   catalog and matching-vendor built-in prices, without following another alias.
5. Existing built-in family price, restricted to the matching vendor.
6. Unknown price: no guessed tariff, no claim of free usage.

Catalog synchronization accepts validated token-generation prices across provider
names, rather than a four-vendor allowlist. Provider aliases such as
`google_antigravity`/`google_ai_studio` map to Gemini for retail estimates. Unknown
providers do not borrow another provider's same-named price. Region/path-qualified
models retain their identity; punctuation and `:batch` are not blindly removed.
Antigravity `gemini-3.8-flash-tiered` has an explicit pricing identity of
`gemini/gemini-3.8-flash`. No arbitrary `-tiered`, `-high`, or `-thinking` rule exists.

## Operator configuration

Both files live in `CREDENTIALS_DIR` and reload after their modification time
changes. There is no need to re-add credentials. Prices use USD per million tokens.
Example **manual reference rates**, not a promise of subscription billing:

```json
{
  "google_antigravity/gemini-3.8-flash-tiered": {
    "input": 0.75,
    "output": 3.75,
    "cache_read": 0.075,
    "reasoning": 3.75
  }
}
```

Prefer a catalog alias to keep future catalog price changes automatic. Example
`model_pricing_aliases.json` (this particular alias is already included):

```json
{
  "google_antigravity": {
    "gemini-3.8-flash-tiered": {
      "provider": "gemini",
      "model": "gemini-3.8-flash"
    }
  }
}
```

Alias identities are explicit and non-recursive: cycles cannot resolve. Configuration
has a 1 MiB/4,096-alias limit. Invalid alias configuration uses only the verified
built-ins; it never invents rates. Both input and output manual prices must be
explicit, finite and nonnegative; omitted cache rates use normal input prices.
Use explicit zero rates only for a deliberately free tariff.

## Costs, usage and coverage

Normal input, cache reads and cache writes are disjoint portions of total input.
Normalized output excludes separately tracked reasoning. Each class is multiplied
by its rate exactly once. Provider-specific token normalization remains authoritative.

New ledger records retain `cost_status`, `cost_source`, `pricing_model`, and
`pricing_provider`. Statuses are `estimated`, `reported`, `free`, `unpriced`,
`unknown_usage` and `legacy`. Validated adapter-supplied `reported_cost_usd` wins
over an estimate (including when explicitly zero). Matching virtual-key cost
estimates preserve their original pricing source; fallback/different amounts are
marked as budget estimates, **not** provider-reported charges. No arbitrary
upstream `cost` field is automatically trusted.

`/api/usage/aggregated` and credential statistics add `priced_calls` and
`unpriced_calls` for successful attempts. An unknown price, missing usage, or old
row without provenance does not count as priced. `total_cost_usd` stays a numeric
recorded subtotal for compatibility. Dashboard coverage explains incompleteness;
zero subtotal with incomplete coverage renders as `—`, not a claim of free usage.

## Deliberate limits and budgets

- This calculation uses normalized text-token classes. Per-image, per-second,
  storage, search, audio/video and other charges need their own measured units;
  they are not included in a text-token estimate.
- Conditional long-context / `tiered_pricing` catalog entries are explicitly
  unpriced until their rate-selection semantics are supported or the operator
  supplies a deliberate fixed reference estimate. They must not fall through to
  a cheaper flat built-in price. This can cause hard-budget admission to deny a
  model that previously used an incomplete flat estimate.
- Unknown hard-budget prices retain existing deny/warn/fallback policy. Before
  routing selects a provider, admission uses a conservative per-token-class
  maximum across matching catalog, explicit alias and scoped manual candidates.
  An unresolved or unsupported candidate stays unknown rather than being ignored.
- A general resolver does not imply every provider/model has a verified price.

## History and rollback

Catalog changes affect new records only. Old amounts and serialized payloads stay
unchanged and have `legacy` coverage. There is no automatic historical revaluation
or change to consumed budgets. New provenance lives in the existing JSON payload;
no SQL column migration is required. Older binaries reject new payload fields:
rollback therefore requires the pre-update data backup as well as the old image,
not merely switching the image against newer data. Back up before deployment.

## Tiếng Việt

- Ánh xạ giá áp dụng theo **provider + model**, không đổi tên model gửi lên upstream.
  Có thể bổ sung tên bất kỳ bằng `model_pricing_aliases.json`, hoặc cấu hình giá
  rõ ràng trong `model_pricing.json`. Không tự đoán tên gần giống.
- `—` cùng tỷ lệ lượt đã tính giá nghĩa là số liệu chưa đầy đủ, không phải miễn phí.
  Số tiền hiển thị là tổng đã ghi nhận; giá API tham chiếu không phải hóa đơn gói thuê bao.
- Lượt cũ không tự tính lại và không sửa ngân sách đã dùng. Những cách tính chưa
  hỗ trợ (giá theo bậc/ngưỡng, ảnh/giây...) không được coi là giá phẳng hay miễn phí.
- Bản này thêm metadata vào payload. Trước khi cập nhật phải sao lưu; nếu quay về
  bản cũ cần khôi phục cả dữ liệu tương ứng, không chỉ đổi Docker image.

Sources: [LiteLLM catalog](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json),
[Google pricing](https://ai.google.dev/gemini-api/docs/pricing), reviewed 2026-09-20.
