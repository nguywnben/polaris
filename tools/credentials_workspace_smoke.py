"""Synthetic credential sections, management dialogs and scoped actions. No live providers."""

from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    items = [
        {
            "filename": f"deepseek-{index}.json",
            "provider": "deepseek",
            "provider_variant": "deepseek",
            "credential_type": "api_key",
            "credential_label": "" if index == 0 else f"Development {index}",
            "disabled": index == 2,
            "model_count": 3,
        }
        for index in range(5)
    ] + [
        {
            "filename": "antigravity-test.json",
            "provider": "google_antigravity",
            "provider_variant": "google_antigravity",
            "credential_type": "oauth",
            "user_email": "long.account.name.for.layout.testing@example.test",
            "model_count": 41,
            "tier": "pro",
        },
        {
            "filename": "muse-code-account-fingerprint.json",
            "provider": "muse_code",
            "provider_variant": "muse_code",
            "credential_type": "oauth",
            "model_count": 5,
        },
        {
            "filename": "environment-key.json",
            "provider": "openai",
            "provider_variant": "openai_platform",
            "credential_type": "api_key",
            "credential_label": '<script>alert("untrusted")</script>',
            "source": "environment",
            "model_count": 2,
        },
    ]
    muse_quota = {
        "success": True,
        "supported": True,
        "provider": "muse_code",
        "quota_type": "account_rate_limits",
        "subscription_tier": "fixture_TIER-2",
        "windows": [
            {
                "id": "session",
                "label": "Session Limit",
                "used_percentage": 25,
                "remaining_percentage": 75,
                "reset_time": "2030-01-01T00:00:00+00:00",
            }
        ],
    }
    batches = []
    detail_requests = []

    def batch(route):
        body = route.request.post_data_json
        batches.append(body)
        route.fulfill(
            json={
                "preview_token": "synthetic-preview",
                "total_count": len(body["filenames"]),
                "success_count": len(body["filenames"]),
                "outcome_counts": {"eligible": len(body["filenames"])},
                "results": [],
            }
        )

    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.route("https://**", lambda route: route.abort())
        context.route(
            "**/api/credentials/status?**",
            lambda route: route.fulfill(
                json={
                    "items": items,
                    "total": len(items),
                    "has_more": False,
                    "stats": {"total": len(items), "normal": 7, "disabled": 1},
                }
            ),
        )
        context.route("**/api/credentials/batch-action?**", batch)
        context.route(
            "**/api/credentials/quota/muse-code-account-fingerprint.json?**",
            lambda route: route.fulfill(json=muse_quota),
        )
        context.route(
            "**/api/credentials/detail/**",
            lambda route: (
                detail_requests.append(route.request.url),
                route.fulfill(json={"content": {"credential_label": "Synthetic detail"}}),
            ),
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        screenshots = ROOT / "temp/credentials-workspace"
        screenshots.mkdir(parents=True, exist_ok=True)
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.evaluate("""() => {
                AppState.quotaPreviewCache['antigravity-test.json'] = {
                    summary: {level: 'success', label: 'Còn 75%', modelCount: 41}
                };
                AppState.quotaPreviewCache['muse-code-account-fingerprint.json'] = {
                    summary: {level: 'info', label: 'Chưa có dữ liệu hạn mức'}
                };
            }""")
            page.locator('#primaryNavigation [data-tab="credentials"]').click()
            cards = page.locator("#primaryCredsList .cred-card")
            expect(cards).to_have_count(8)
            groups = page.locator(".credential-provider-group")
            expect(groups).to_have_count(4)
            deepseek = groups.filter(has=page.locator("#credentialProviderGroup-deepseek"))
            first = deepseek.locator(".cred-card").first
            expect(first.locator("h3")).to_have_text("deepseek-0")
            expect(page.locator("#primaryCredsList")).not_to_contain_text("Email không khả dụng")
            expect(first.locator(".cred-quota-preview")).to_have_count(0)
            expect(groups.nth(1).locator(".cred-account-name")).to_contain_text("@example.test")
            expect(groups.nth(2).locator(".cred-account-name")).to_have_text(
                "muse-code-account-fingerprint"
            )
            expect(groups.nth(3).locator("script")).to_have_count(0)

            muse_card = groups.nth(2).locator(".cred-card")
            muse_card.locator("[data-quota-preview]").click()
            expect(muse_card.locator(".subscription-badge")).to_contain_text("fixture_TIER-2")
            page.evaluate("AppState.primaryCreds.renderList()")
            expect(muse_card.locator(".subscription-badge")).to_contain_text("fixture_TIER-2")
            muse_card.locator('[data-credential-command="manage"]').click()
            expect(page.locator('[role="dialog"] [data-management-quota]')).to_contain_text(
                "fixture_TIER-2"
            )
            page.locator("[data-dialog-close]").click()
            # Observed Muse key response: a named plan, but no usage observation.
            original_windows = muse_quota["windows"]
            muse_quota.update(plan="Muse Code Power Usage", quota_status="unavailable", windows=[])
            muse_card.locator("[data-quota-preview]").click()
            expect(muse_card.locator(".subscription-badge")).to_contain_text(
                "Muse Code Power Usage"
            )
            expect(muse_card.locator("[data-quota-preview]")).not_to_contain_text("100%")
            expect(muse_card.locator("[data-quota-preview]")).not_to_contain_text(
                "Không có hạn mức"
            )
            page.evaluate("AppState.primaryCreds.renderList()")
            expect(muse_card.locator(".subscription-badge")).to_contain_text(
                "Muse Code Power Usage"
            )
            muse_card.locator('[data-credential-command="manage"]').click()
            expect(page.locator('[role="dialog"] [data-management-quota]')).to_contain_text(
                "Muse Code Power Usage"
            )
            expect(
                page.locator('[role="dialog"] [data-management-quota] .modal-empty-state')
            ).to_be_visible()
            page.locator("[data-dialog-close]").click()
            del muse_quota["plan"]
            del muse_quota["quota_status"]
            muse_quota["windows"] = original_windows
            # A later response without a tier must remove the old badge, not retain a stale plan.
            del muse_quota["subscription_tier"]
            muse_card.locator("[data-quota-preview]").click()
            expect(muse_card.locator(".subscription-badge")).to_be_hidden()
            muse_quota["subscription_tier"] = "<img src=x onerror=alert(1)>"
            muse_card.locator("[data-quota-preview]").click()
            expect(muse_card.locator(".subscription-badge")).to_contain_text(
                "<img src=x onerror=alert(1)>"
            )
            expect(muse_card.locator(".subscription-badge img")).to_have_count(0)
            muse_quota["subscription_tier"] = "x" * 128
            muse_card.locator("[data-quota-preview]").click()
            expect(muse_card.locator(".subscription-badge")).to_have_attribute(
                "title", "Cấp: " + "x" * 128
            )
            assert not muse_card.evaluate("el => el.scrollWidth > el.clientWidth"), (
                muse_card.evaluate("""el => [el, ...el.querySelectorAll('.cred-header, .cred-status, .subscription-badge')].map(node => ({
                    name: node.className, width: node.clientWidth, scroll: node.scrollWidth,
                    min: getComputedStyle(node).minWidth, columns: getComputedStyle(node).gridTemplateColumns,
                    overflow: getComputedStyle(node).overflow
                }))""")
            )
            muse_quota["subscription_tier"] = "fixture_TIER-2"
            muse_card.locator("[data-quota-preview]").click()
            expect(muse_card.locator(".subscription-badge")).to_contain_text("fixture_TIER-2")

            # Management overview does not fetch any raw secrets; only supported actions exist.
            manage = first.locator('[data-credential-command="manage"]')
            manage.click()
            dialog = page.locator('[role="dialog"]')
            expect(dialog).to_be_visible()
            expect(dialog).to_be_focused()
            assert not detail_requests
            expect(dialog.locator("[data-management-configuration]")).to_be_visible()
            expect(dialog.locator('[data-management-action="reauthenticate"]')).to_have_count(0)
            expect(dialog.locator("[data-management-quota]")).to_have_count(0)
            expect(dialog.locator('[data-management-action="delete"]')).to_be_visible()
            page.keyboard.press("Shift+Tab")
            expect(dialog.locator("[data-dialog-close]")).to_be_focused()
            page.keyboard.press("Escape")
            expect(dialog).to_be_visible()
            dialog.locator("[data-dialog-close]").click()
            expect(dialog).to_have_count(0)
            expect(manage).to_be_focused()

            groups.nth(2).locator('[data-credential-command="manage"]').click()
            expect(dialog.locator('[data-management-action="reauthenticate"]')).to_be_visible()
            expect(dialog.locator("[data-management-quota]")).to_be_visible()
            dialog.locator("[data-dialog-close]").click()
            groups.nth(3).locator('[data-credential-command="manage"]').click()
            expect(dialog.locator("[data-management-configuration]")).to_have_count(0)
            expect(dialog.locator('[data-management-action="reauthenticate"]')).to_have_count(0)
            dialog.locator("[data-dialog-close]").click()

            # Scoped batch retains selection from another provider, previews and confirms.
            other_selection = groups.nth(2).locator("[data-credential-select]")
            other_selection.check()
            expect(deepseek.locator("button[data-provider-actions]")).to_have_count(0)
            expect(deepseek.locator('[data-provider-batch="enable"]')).to_be_visible()
            expect(deepseek.locator('[data-provider-batch="delete"]')).to_be_visible()
            deepseek.locator('[data-provider-batch="disable"]').click()
            confirm = page.get_by_role("dialog", name="Tắt thông tin xác thực", exact=True)
            expect(confirm).to_contain_text("DeepSeek Platform")
            expect(confirm).to_contain_text("Chỉ áp dụng cho 5")
            assert len(batches) == 1 and batches[0]["preview"]
            confirm.get_by_role("button", name="Tắt", exact=True).click()
            expect(page.locator(".message-modal-overlay")).to_have_count(1)
            page.locator("[data-dialog-close]").click()
            expect(other_selection).to_be_checked()
            assert len(batches) == 2
            expected = [f"deepseek-{index}.json" for index in range(5)]
            assert all(body["filenames"] == expected for body in batches)
            assert batches[1]["preview_token"] == "synthetic-preview"

            for width, theme, columns in (
                (1440, "light", 4),
                (1920, "dark", 4),
                (1200, "light", 3),
                (1024, "dark", 2),
                (768, "light", 1),
                (360, "dark", 1),
                (320, "light", 1),
            ):
                page.set_viewport_size({"width": width, "height": 1000})
                page.emulate_media(color_scheme=theme)
                assert not page.locator("body").evaluate("el => el.scrollWidth > innerWidth"), width
                actual = deepseek.locator(".credential-provider-grid").evaluate(
                    "el => getComputedStyle(el).gridTemplateColumns.split(' ').length"
                )
                assert actual == columns, (width, actual)
                for heading in cards.locator(".cred-account-name").all():
                    layout = heading.evaluate("""el => {
                        const style = getComputedStyle(el);
                        return {whiteSpace: style.whiteSpace, overflow: style.overflow,
                            ellipsis: style.textOverflow, height: el.getBoundingClientRect().height,
                            lineHeight: parseFloat(style.lineHeight), title: el.title, text: el.textContent};
                    }""")
                    assert layout["whiteSpace"] == "nowrap", (width, layout)
                    assert layout["overflow"] == "hidden" and layout["ellipsis"] == "ellipsis"
                    assert layout["height"] <= layout["lineHeight"] + 1, (width, layout)
                    assert layout["title"] == layout["text"], "Full identity must remain available"
                assert groups.nth(1).bounding_box()["y"] >= (
                    deepseek.bounding_box()["y"] + deepseek.bounding_box()["height"]
                )
                page.mouse.move(0, 0)
                page.evaluate("document.activeElement.blur()")
                page.screenshot(path=str(screenshots / f"{width}-{theme}.png"), full_page=True)
                manage.click()
                assert not dialog.evaluate("el => el.scrollWidth > el.clientWidth"), width
                if width in (1440, 360):
                    page.screenshot(path=str(screenshots / f"modal-{width}-{theme}.png"))
                dialog.locator("[data-dialog-close]").click()

            # Every locale renders real translated controls and remains within narrow viewports.
            for locale in page.evaluate("Object.keys(CREDENTIAL_WORKSPACE_COPY)"):
                page.evaluate(
                    "locale => {AppState.lang = locale; applyLanguage(); AppState.primaryCreds.renderList();}",
                    locale,
                )
                expect(deepseek.locator(".credential-provider-actions")).not_to_contain_text(
                    "credentials.workspace"
                )
                assert not page.locator("body").evaluate("el => el.scrollWidth > innerWidth"), (
                    locale
                )
            assert not errors, errors
            print(
                "PASS: identity, 4-column sections, scoped preview/commit, capability-aware dialogs, focus, 15 locales, 320–1920px light/dark"
            )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
