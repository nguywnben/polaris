"""Single-surface credential management, using only synthetic local API fixtures."""

from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    items = [
        {
            "filename": "work.json",
            "provider": "deepseek",
            "provider_variant": "deepseek",
            "credential_type": "api_key",
            "credential_label": "Development",
            "model_count": 3,
            "disabled": False,
        },
        {
            "filename": "muse.json",
            "provider": "muse_code",
            "provider_variant": "muse_code",
            "credential_type": "oauth",
            "model_count": 5,
            "disabled": False,
        },
        {
            "filename": "google.json",
            "provider": "google_antigravity",
            "provider_variant": "google_antigravity",
            "credential_type": "oauth",
            "user_email": "work@example.test",
            "model_count": 2,
            "disabled": False,
            "tier": "pro",
        },
        {
            "filename": "environment.json",
            "provider": "openai",
            "provider_variant": "openai_platform",
            "credential_type": "api_key",
            "source": "environment",
            "model_count": 2,
        },
    ]
    calls = []
    quota_failure = False
    configuration_failure = False

    def api(route):
        request = route.request
        url = request.url.split("/api/credentials/", 1)[1].split("?", 1)[0]
        calls.append((request.method, url, request.post_data_json if request.post_data else None))
        filename = url.split("/")[-1]
        item = next((item for item in items if item["filename"] == filename), items[0])
        if url == "status":
            return route.fulfill(
                json={
                    "items": items,
                    "total": len(items),
                    "has_more": False,
                    "stats": {"total": len(items), "normal": len(items)},
                }
            )
        if url.startswith("configuration/"):
            if request.method == "PATCH":
                if configuration_failure:
                    return route.fulfill(status=400, json={"error": "Synthetic save rejected"})
                item.update(request.post_data_json)
            return route.fulfill(
                json={
                    "editable": True,
                    "editable_fields": ["credential_label", "api_key"]
                    if item["credential_type"] == "api_key"
                    else ["credential_label"],
                    "credential_label": item.get("credential_label", ""),
                    "provider": item["provider"],
                }
            )
        if url.startswith("models/"):
            return route.fulfill(
                json={"model_ids": ["model-alpha", "model-beta", "model-long-" + "name-" * 12]}
            )
        if url.startswith("errors/"):
            return route.fulfill(
                json={
                    "error_codes": [429] if filename == "work.json" else [],
                    "error_messages": {"429": "Synthetic rate limit. Try again later."},
                }
            )
        if url.startswith("quota/"):
            if quota_failure:
                return route.fulfill(status=502, json={"error": "Synthetic quota unavailable"})
            if filename == "google.json":
                return route.fulfill(
                    json={
                        "success": True,
                        "models": {
                            "model-alpha": {"remaining": 0.8, "resetTime": "2030-01-01T00:00:00Z"}
                        },
                    }
                )
            return route.fulfill(
                json={
                    "success": True,
                    "provider": "muse_code",
                    "quota_type": "account_rate_limits",
                    "plan": "Muse Code Power Usage",
                    "windows": [
                        {
                            "id": "session",
                            "label": "Session",
                            "used_percentage": 25,
                            "remaining_percentage": 75,
                            "reset_time": "2030-01-01T00:00:00Z",
                        }
                    ],
                }
            )
        if url.startswith("test/"):
            return route.fulfill(
                json={
                    "success": True,
                    "status_code": 200,
                    "model": request.post_data_json["model"],
                    "message": "Synthetic test complete",
                }
            )
        if url.startswith("verify/"):
            return route.fulfill(
                json={
                    "success": True,
                    "message": "Synthetic verification complete",
                    "model_count": 3,
                }
            )
        if url.startswith("detail/"):
            return route.fulfill(json={"content": {"api_key": "synthetic-sensitive-value"}})
        if url == "action":
            target = next(
                item for item in items if item["filename"] == request.post_data_json["filename"]
            )
            action = request.post_data_json["action"]
            if action == "delete":
                items.remove(target)
            else:
                target["disabled"] = action == "disable"
            return route.fulfill(json={"success": True})
        return route.fulfill(json={"success": True})

    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.route("https://**", lambda route: route.abort())
        context.route("**/api/credentials/**", api)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        captures = ROOT / "temp/credential-management"
        captures.mkdir(parents=True, exist_ok=True)
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.locator('#primaryNavigation [data-tab="credentials"]').click()
            cards = page.locator("#primaryCredsList .cred-card")
            expect(cards).to_have_count(4)
            trigger = cards.first.locator('[data-credential-command="manage"]')
            trigger.click()
            dialog = page.locator(".credential-management-modal")
            expect(dialog).to_be_visible()
            expect(dialog.locator("[data-management-models]")).to_contain_text("model-alpha")
            expect(dialog.locator("[data-management-errors]")).to_contain_text("429")
            expect(dialog.locator('[name="credential_label"]')).to_have_value("Development")
            expect(dialog.locator('[name="api_key"]')).to_have_value("")
            assert not any(url.startswith("detail/") for _, url, _ in calls)
            assert not any(url.startswith("test/") for _, url, _ in calls)
            expect(
                dialog.locator(
                    '[data-credential-command="models"], [data-credential-command="quota"], [data-credential-command="errors"], [data-credential-command="edit"]'
                )
            ).to_have_count(0)
            dialog.locator('[name="credential_label"]').fill("Renamed work")
            dialog.locator('[data-credential-edit-form] button[type="submit"]').click()
            expect(dialog).to_be_visible()
            expect(page.locator('[role="dialog"]')).to_have_count(1)
            expect(dialog.locator("[data-management-name]")).to_have_text("Renamed work")
            configuration_failure = True
            dialog.locator('[name="credential_label"]').fill("Rejected change")
            dialog.locator('[data-credential-edit-form] button[type="submit"]').click()
            expect(dialog.locator("[data-credential-edit-error]")).to_have_text(
                "Synthetic save rejected"
            )
            expect(dialog.locator('[name="credential_label"]')).to_have_value("Rejected change")
            dialog.locator("[data-credential-edit-cancel]").click()
            expect(dialog.locator('[name="credential_label"]')).to_have_value("Renamed work")
            configuration_failure = False
            dialog.locator("[data-management-search]").fill("not-a-model")
            expect(dialog.locator("[data-management-model-empty]")).to_be_visible()
            dialog.locator("[data-management-search]").fill("alpha")
            expect(dialog.locator("[data-management-model]:visible")).to_have_count(1)
            dialog.locator("[data-management-search]").fill("")
            dialog.locator('[data-management-action="verify"]').click()
            expect(dialog.locator("[data-management-result]")).to_contain_text(
                "Synthetic verification complete"
            )
            dialog.locator("[data-management-model-select]").select_option("model-beta")
            dialog.locator('[data-management-action="test"]').click()
            expect(dialog.locator("[data-management-result]")).to_contain_text("model-beta")
            expect(page.locator('[role="dialog"]')).to_have_count(1)
            dialog.locator('[data-management-action="toggle"]').click()
            expect(dialog.locator("[data-management-state]")).to_contain_text("Đã tắt")
            dialog.locator("[data-management-sensitive] summary").click()
            assert not any(url.startswith("detail/") for _, url, _ in calls)
            dialog.locator('[data-management-action="reveal"]').click()
            expect(dialog.locator("[data-management-payload]")).to_contain_text(
                "synthetic-sensitive-value"
            )
            dialog.locator('[data-management-action="hide"]').click()
            expect(dialog).not_to_contain_text("synthetic-sensitive-value")
            dialog.locator('[data-management-action="delete"]').click()
            expect(dialog.locator("[data-management-delete-confirm]")).to_be_visible()
            expect(page.locator('[role="dialog"]')).to_have_count(1)
            dialog.locator('[data-management-action="cancel-delete"]').click()
            assert not any(body and body.get("action") == "delete" for _, _, body in calls)
            dialog.locator("[data-dialog-close]").click()

            # Fresh quota, failure then retry without a nested modal or stale percentage.
            cards.nth(1).locator('[data-credential-command="manage"]').click()
            expect(dialog.locator("[data-management-quota]")).to_contain_text("75%")
            expect(dialog).to_contain_text("Muse Code Power Usage")
            quota_failure = True
            dialog.locator('[data-management-load="quota"]').click()
            expect(dialog.locator("[data-management-quota]")).to_contain_text(
                "Synthetic quota unavailable"
            )
            expect(dialog.locator("[data-management-quota]")).not_to_contain_text("75%")
            quota_failure = False
            dialog.locator('[data-management-load="quota"]').click()
            expect(dialog.locator("[data-management-quota]")).to_contain_text("75%")
            dialog.locator("[data-dialog-close]").click()

            # Batched visual verification: desktop/mobile, old/new OAuth, API keys, environment.
            for width, theme, index in (
                (1440, "light", 0),
                (1440, "dark", 1),
                (1440, "light", 2),
                (768, "light", 2),
                (1024, "light", 2),
                (360, "dark", 1),
                (320, "light", 3),
            ):
                page.set_viewport_size({"width": width, "height": 1000})
                page.emulate_media(color_scheme=theme)
                active_trigger = cards.nth(index).locator('[data-credential-command="manage"]')
                active_trigger.click()
                expect(dialog.locator("[data-management-models]")).to_contain_text("model-alpha")
                if index == 3:
                    expect(dialog.locator("[data-credential-edit-form]")).to_have_count(0)
                    expect(
                        dialog.locator('[data-management-action="reauthenticate"]')
                    ).to_have_count(0)
                assert not dialog.evaluate("el => el.scrollWidth > el.clientWidth"), (width, theme)
                overview = dialog.locator(".credential-management-overview")
                toolbar = overview.locator(":scope > .credential-management-toolbar")
                facts = overview.locator(":scope > .credential-management-facts")
                toolbar_box = toolbar.bounding_box()
                facts_box = facts.bounding_box()
                if toolbar.locator("button").count():
                    assert toolbar_box and facts_box
                    if width > 700:
                        assert toolbar_box["y"] + toolbar_box["height"] <= facts_box["y"], width
                    else:
                        assert toolbar_box["y"] >= facts_box["y"] + facts_box["height"], width
                    assert toolbar.evaluate("el => el.scrollWidth <= el.clientWidth"), width
                page.screenshot(path=str(captures / f"{width}-{theme}-{index}.png"))
                page.keyboard.press("Tab")
                assert dialog.evaluate("el => el.contains(document.activeElement)")
                page.keyboard.press("Escape")
                expect(dialog).to_be_visible()
                page.mouse.click(2, 2)
                expect(dialog).to_be_visible()
                dialog.locator("[data-dialog-close]").click()
                expect(dialog).to_have_count(0)
                expect(active_trigger).to_be_focused()
            for locale in page.evaluate("Object.keys(CREDENTIAL_MANAGEMENT_COPY)"):
                page.evaluate(
                    "locale => {AppState.lang = locale; applyLanguage(); AppState.primaryCreds.renderList();}",
                    locale,
                )
                cards.first.locator('[data-credential-command="manage"]').click()
                expect(dialog.locator('[name="credential_label"]')).to_have_value("Renamed work")
                expect(dialog).not_to_contain_text("credentials.management.")
                assert not dialog.evaluate("el => el.scrollWidth > el.clientWidth"), locale
                dialog.locator("[data-dialog-close]").click()
            # Confirmation affects only the selected synthetic credential.
            cards.first.locator('[data-credential-command="manage"]').click()
            dialog.locator('[data-management-action="delete"]').click()
            dialog.locator('[data-management-action="confirm-delete"]').click()
            expect(dialog).to_have_count(0)
            expect(cards).to_have_count(3)
            deletes = [body for _, _, body in calls if body and body.get("action") == "delete"]
            assert len(deletes) == 1 and deletes[0]["filename"] == "work.json"
            assert not errors, errors
            print(
                "PASS: inline data/edit/test/verify/quota/errors, explicit secret reveal, scoped actions, no nested dialogs, themes/responsive/focus"
            )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
