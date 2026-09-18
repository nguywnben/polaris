"""Synthetic provider-specific credential facts; never uses the user's accounts."""

from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WINDOW = {
    "id": "session",
    "label": "Session Limit",
    "used_percentage": 25,
    "remaining_percentage": 75,
}
QUOTAS = {
    "google_antigravity": {
        "plan": "g1-pro-tier",
        "models": {
            "model-a": {"remaining": 0.8, "resetTime": "2030-01-01T00:00:00Z"},
            "unknown-model": {"remaining": None},
        },
        "credit_balances": [{"type": "GOOGLE_ONE_AI", "balance": 125, "minimum": 2}],
    },
    "grok": {
        "quota_type": "account_billing",
        "monthly": {"used": 20, "limit": 80, "remaining_percentage": 75, "used_percentage": 25},
        "weekly": {"used_percentage": 50, "remaining_percentage": 50},
    },
    "codex": {
        "quota_type": "account_rate_limits",
        "plan": "plus",
        "windows": [WINDOW],
        "credits": {"has_credits": True, "balance": 12.5, "unlimited": False},
        "reset_credits": {"available_count": 2},
    },
    "claude_code": {
        "quota_type": "account_rate_limits",
        "plan": "max_20x",
        "windows": [WINDOW, {**WINDOW, "id": "weekly_sonnet", "label": "7-Day Sonnet"}],
        "extra_usage": {
            "is_enabled": True,
            "used_credits": 125,
            "monthly_limit": 5000,
            "utilization": 2.5,
        },
    },
    "kiro": {
        "quota_type": "account_rate_limits",
        "plan": "Kiro Pro",
        "windows": [
            {**WINDOW, "kind": "resource", "used": 25, "limit": 100},
            {
                **WINDOW,
                "kind": "trial",
                "id": "trial",
                "used": None,
                "limit": 50,
                "remaining_percentage": None,
                "used_percentage": None,
            },
        ],
        "overage_enabled": True,
    },
    "muse_code": {
        "quota_type": "account_rate_limits",
        "plan": "Muse Code Power Usage",
        "subscription_tier": "POWER",
        "observed_at": 2000000000,
        "windows": [WINDOW],
    },
}
QUOTAS["google_antigravity"]["windows"] = [
    {**WINDOW, "label": "Gemini · Weekly", "remaining_percentage": 40, "used_percentage": 60}
]
QUOTAS["grok"].update(
    {
        "plan": "Build",
        "on_demand_used": 5,
        "on_demand_cap": 20,
        "prepaid_balance": 12,
        "windows": [
            {**WINDOW, "label": "Build product", "remaining_percentage": 30, "used_percentage": 70}
        ],
    }
)
QUOTAS["kiro"].update({"summary_mode": "resource_balances", "summary_remaining_percentage": None})
QUOTAS["muse_code"]["windows"][0] = {**WINDOW, "window_duration_mins": 300}


def main():
    items = [
        {
            "filename": variant + ".json",
            "provider": {"codex": "openai", "claude_code": "anthropic", "grok": "xai"}.get(
                variant, variant
            ),
            "provider_variant": variant,
            "credential_type": "oauth",
            "model_count": 2,
        }
        for variant in QUOTAS
    ]
    items.append(
        {
            "filename": "key.json",
            "provider": "deepseek",
            "provider_variant": "deepseek",
            "credential_type": "api_key",
            "model_count": 2,
        }
    )
    calls = []
    failures = set()

    def api(route):
        path = route.request.url.split("/api/credentials/", 1)[1].split("?", 1)[0]
        calls.append((path, route.request.post_data_json if route.request.post_data else None))
        if path == "status":
            return route.fulfill(
                json={
                    "items": items,
                    "total": len(items),
                    "has_more": False,
                    "stats": {"total": len(items), "normal": len(items)},
                }
            )
        filename = path.split("/")[-1]
        variant = filename.removesuffix(".json")
        if path.startswith("quota/"):
            if variant in failures:
                return route.fulfill(
                    status=503, json={"detail": "Synthetic quota service unavailable"}
                )
            return route.fulfill(json={"success": True, "provider": variant, **QUOTAS[variant]})
        if path.startswith("models/"):
            return route.fulfill(json={"model_ids": ["model-a", "model-b"]})
        if path.startswith("configuration/"):
            return route.fulfill(
                json={
                    "editable": True,
                    "editable_fields": ["credential_label"],
                    "provider": variant,
                }
            )
        if path == "action":
            body = route.request.post_data_json
            item = next(item for item in items if item["filename"] == body["filename"])
            item["enable_credit"] = body["action"] == "enable_credit"
        return route.fulfill(json={"success": True, "error_codes": [], "error_messages": {}})

    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1050})
        context.route("https://**", lambda route: route.abort())
        context.route("**/api/credentials/**", api)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        captures = ROOT / "temp/provider-fidelity"
        captures.mkdir(parents=True, exist_ok=True)
        try:
            page.goto(base + "/setup")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.locator('#primaryNavigation [data-tab="credentials"]').click()
            expect(page.locator("#primaryCredsList .cred-card")).to_have_count(7)
            for width, theme in ((1440, "light"), (1440, "dark"), (768, "light"), (360, "dark")):
                page.set_viewport_size({"width": width, "height": 1050})
                page.emulate_media(color_scheme=theme)
                for variant in [*QUOTAS, "key"]:
                    card = page.locator(".cred-card").filter(
                        has=page.locator(f'[data-filename="{variant}.json"]')
                    )
                    card.locator('[data-credential-command="manage"]').click()
                    modal = page.locator(".credential-management-modal")
                    expect(modal.locator("[data-management-models]")).to_contain_text("model-a")
                    if variant in QUOTAS:
                        quota = modal.locator("[data-management-quota]")
                        expect(quota).to_contain_text("%")
                        if variant == "google_antigravity":
                            expect(quota).to_contain_text("125")
                            expect(quota).to_contain_text("Gemini · Weekly")
                            expect(quota).to_contain_text("40%")
                            expect(
                                modal.locator('[data-management-action="credit"]')
                            ).to_be_visible()
                        if variant == "codex":
                            expect(quota).to_contain_text("12,5")
                        if variant == "claude_code":
                            expect(quota).to_contain_text("1,25")
                        if variant == "kiro":
                            expect(quota).to_contain_text("Dùng thử")
                            expect(quota).to_contain_text("Vượt hạn mức")
                        if variant == "muse_code":
                            expect(quota).to_contain_text("POWER")
                            expect(quota).to_contain_text("Hạn mức 5 giờ")
                    else:
                        expect(modal.locator("[data-management-quota]")).to_have_count(0)
                    if variant != "google_antigravity":
                        expect(modal.locator('[data-management-action="credit"]')).to_have_count(0)
                    assert not modal.evaluate("el => el.scrollWidth > el.clientWidth"), (
                        variant,
                        width,
                    )
                    page.screenshot(path=str(captures / f"{variant}-{width}-{theme}.png"))
                    modal.locator("[data-dialog-close]").click()
            # Missing/invalid values must not silently become zero or full quota.
            for payload in (
                {"models": {"a": {"remaining": None}}},
                {"quota_type": "account_rate_limits", "windows": [{"remaining_percentage": None}]},
                QUOTAS["kiro"],
            ):
                summary = page.evaluate("data => summarizeCredentialQuota(data)", payload)
                assert "%" not in summary["label"], summary
            for locale in (
                "en",
                "vi",
                "de",
                "es",
                "fr",
                "id",
                "it",
                "ja",
                "ko",
                "pt",
                "ru",
                "th",
                "tr",
                "zh-CN",
                "zh-TW",
            ):
                with page.expect_navigation(wait_until="networkidle"):
                    page.evaluate("locale => changeLanguage(locale)", locale)
                text = page.evaluate("data => renderCredentialQuotaFacts(data)", QUOTAS["grok"])
                assert "quota.facts." not in text
            with page.expect_navigation(wait_until="networkidle"):
                page.evaluate("changeLanguage('vi')")
            card = page.locator(".cred-card").filter(
                has=page.locator('[data-filename="google_antigravity.json"]')
            )
            card.locator('[data-credential-command="manage"]').click()
            modal = page.locator(".credential-management-modal")
            modal.locator('[data-management-action="credit"]').click()
            expect(modal.locator("[data-management-credit-confirm]")).to_be_visible()
            modal.locator('[data-management-action="cancel-credit"]').click()
            expect(modal.locator("[data-management-credit-confirm]")).to_be_hidden()
            assert not any(path == "action" for path, _ in calls)
            modal.locator('[data-management-action="credit"]').click()
            modal.locator('[data-management-action="confirm-credit"]').click()
            expect(modal.locator("[data-management-credit-confirm]")).to_be_hidden()
            expect(modal.locator('[data-management-action="credit"]')).to_contain_text("Tắt")
            expect(page.locator('[role="dialog"]')).to_have_count(1)
            failures.add("google_antigravity")
            modal.locator('[data-management-load="quota"]').click()
            expect(modal.locator("[data-management-quota]")).to_contain_text(
                "Synthetic quota service unavailable"
            )
            failures.clear()
            modal.locator('[data-management-load="quota"]').click()
            expect(modal.locator("[data-management-quota]")).to_contain_text("125")
            assert not any(path.startswith(("detail/", "test/")) for path, _ in calls)
            assert [body["action"] for path, body in calls if path == "action"] == ["enable_credit"]
            assert not errors, errors
            print(
                "PASS: six OAuth families + API key, safe facts, partial/error/retry, inline credit confirmation, 15 locales, 28 theme/viewport cases"
            )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
