"""Actual local CRUD and populated console regressions on disposable fake data."""

import argparse
import json
import time
from collections import Counter

from browser_smoke import ROOT
from demo_full_smoke import PASSWORD
from playwright.sync_api import expect, sync_playwright
from populated_instance_smoke import populated_runtime


def main(stage, regressions_only=False, only=None):
    output = ROOT / "temp/populated-workflows" / stage
    output.mkdir(parents=True, exist_ok=True)
    results, errors = [], []
    with populated_runtime(output) as (base, _directory), sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            locale="vi-VN", reduced_motion="reduce", viewport={"width": 1440, "height": 900}
        )
        context.route("https://**", lambda route: route.abort())
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/setup", wait_until="networkidle")
        page.locator("#setupPassword").fill(PASSWORD)
        page.locator("#setupPasswordConfirm").fill(PASSWORD)
        page.locator("#setupSubmitButton").click()
        expect(page).to_have_url(base + "/dashboard")

        def run(name, action):
            if only and name not in only:
                return
            started = time.monotonic()
            try:
                action()
                results.append(
                    {"name": name, "passed": True, "seconds": round(time.monotonic() - started, 2)}
                )
            except Exception as exc:
                results.append({"name": name, "passed": False, "error": str(exc)[:1500]})
            print(f"{name}: {results[-1]['passed']}", flush=True)

        def fleet():
            response = context.request.get(base + "/api/credentials/status?mode=provider&limit=100")
            assert response.ok
            return response.json()["items"]

        def open_credential(filename):
            page.goto(base + "/credentials", wait_until="networkidle")
            page.locator('[data-ui-action="reset-primary-filters"]').click()
            page.locator("#primaryPageSizeSelect").select_option("100")
            item = page.locator(f'[data-credential-select][data-filename="{filename}"]')
            expect(item).to_be_visible()
            card = item.locator('xpath=ancestor::div[contains(@class,"cred-card")][1]')
            card.locator('[data-credential-command="manage"]').click()
            dialog = page.get_by_role("dialog").last
            expect(dialog).to_contain_text(filename)
            return dialog

        def provider_filters():
            counts = Counter(item["provider_variant"] for item in fleet())
            page.goto(base + "/credentials", wait_until="networkidle")
            variants = page.locator("#primaryProviderFilter option").evaluate_all(
                "els=>els.map(el=>el.value).filter(v=>v!=='all')"
            )
            assert len(variants) == 23
            for variant in variants:
                page.locator("#primaryProviderFilter").select_option(variant)
                expect(
                    page.locator(
                        f'[data-credential-select][data-filename="demo-{variant}-01.json"]'
                    )
                ).to_be_visible()
                filenames = page.locator("[data-credential-select]").evaluate_all(
                    "els=>els.map(el=>el.dataset.filename)"
                )
                assert all(name.startswith(f"demo-{variant}-") for name in filenames), variant
            page.goto(base + "/credentials?pool_provider=muse_code", wait_until="networkidle")
            expect(page.locator("#primaryProviderFilter")).to_have_value("muse_code")
            expect(page.locator("[data-credential-select]")).to_have_count(counts["muse_code"])

        def dashboard_layout():
            page.goto(base + "/dashboard", wait_until="networkidle")
            for width in (768, 1024, 1440, 1920):
                page.set_viewport_size({"width": width, "height": 900})
                widths = page.locator(
                    "#usageProviderSummary .usage-provider-identity"
                ).evaluate_all("els=>els.map(el=>el.getBoundingClientRect().width)")
                page.locator("#usageProviderSummary").screenshot(
                    path=str(output / f"provider-summary-{width}.png")
                )
                assert widths and min(widths) >= 160, (
                    f"Provider identities collapsed at {width}: {min(widths) if widths else 'missing'}"
                )
            page.set_viewport_size({"width": 1440, "height": 900})

        def credential_edit_toggle_delete():
            ollama = open_credential("demo-ollama-01.json")
            expect(ollama.locator('[name="base_url"]')).to_have_attribute("required", "")
            ollama.locator("[data-dialog-close]").click()
            filename = "demo-deepseek-01.json"
            dialog = open_credential(filename)
            label = "DEMO <img src=x onerror=alert(1)> edited"
            dialog.locator('[name="credential_label"]').fill(label)
            invalid = dialog.locator("[data-credential-edit-form] :invalid").evaluate_all(
                "els=>els.map(el=>({name:el.name,message:el.validationMessage}))"
            )
            assert not invalid, invalid
            dialog.locator('[data-credential-edit-form] button[type="submit"]').click()
            expect(dialog.locator("[data-credential-edit-form]")).not_to_have_attribute(
                "aria-busy", "true"
            )
            expect(dialog.locator("[data-credential-edit-error]")).to_be_hidden()
            expect(dialog.locator("[data-management-name]")).to_have_text(label)
            expect(dialog.locator("[data-management-name] img")).to_have_count(0)
            assert (
                next(item for item in fleet() if item["filename"] == filename)["credential_label"]
                == label
            )
            dialog.locator('[data-management-action="toggle"]').click()
            expect(dialog.locator("[data-management-state]")).to_contain_text("Đã tắt")
            assert next(item for item in fleet() if item["filename"] == filename)["disabled"]
            dialog.locator('[data-management-action="delete"]').click()
            expect(dialog.locator("[data-management-delete-confirm]")).to_be_visible()
            dialog.locator('[data-management-action="cancel-delete"]').click()
            assert any(item["filename"] == filename for item in fleet())
            dialog.locator('[data-management-action="delete"]').click()
            dialog.locator('[data-management-action="confirm-delete"]').click()
            expect(dialog).not_to_be_visible()
            assert all(item["filename"] != filename for item in fleet())

        def pagination_selection():
            inventory = fleet()
            counts = Counter(item["provider_variant"] for item in inventory)
            page.goto(base + "/credentials", wait_until="networkidle")
            page.locator('[data-ui-action="reset-primary-filters"]').click()
            page.locator("#primaryPageSizeSelect").select_option("20")
            expect(page.locator("[data-credential-select]")).to_have_count(20)
            page.locator("#primarySelectAllCheckbox").check()
            expect(page.locator("[data-credential-select]:checked")).to_have_count(20)
            page.locator("#primaryProviderFilter").select_option("muse_code")
            expect(page.locator("[data-credential-select]")).to_have_count(counts["muse_code"])
            expect(page.locator("[data-credential-select]:checked")).to_have_count(0)
            page.locator("#primaryProviderFilter").select_option("cerebras")
            assert not any(
                item["disabled"] for item in inventory if item["provider_variant"] == "cerebras"
            )
            page.locator("#primaryStatusFilter").select_option("disabled")
            expect(page.locator("[data-credential-select]")).to_have_count(0)
            expect(page.locator("#primaryProviderFilter")).to_be_visible()
            expect(page.locator("#credentialsFirstRun")).to_be_hidden()

        def key_lifecycle():
            page.goto(base + "/access", wait_until="networkidle")
            page.locator('[data-ui-action="virtual-key-create"]').click()
            form = page.locator("#virtualKeyForm")
            form.locator('[name="name"]').fill("DEMO round2 key")
            form.locator('button[type="submit"]').click()
            expect(form).not_to_be_visible()
            key = next(
                item
                for item in context.request.get(base + "/api/virtual-keys").json()["data"]
                if item["name"] == "DEMO round2 key"
            )
            page.locator("[data-virtual-key-secret-close]").click()
            expect(page.locator("[data-virtual-key-secret-close]")).not_to_be_visible()
            page.locator(f'[data-ui-action="virtual-key-edit"][data-key-id="{key["id"]}"]').click()
            form = page.locator("#virtualKeyForm")
            form.locator('[name="name"]').fill("DEMO round2 renamed")
            form.locator('button[type="submit"]').click()
            expect(form).not_to_be_visible()
            page.locator(
                f'[data-ui-action="virtual-key-rotate"][data-key-id="{key["id"]}"]'
            ).click()
            page.locator("[data-dialog-confirm]").click()
            expect(page.locator("[data-dialog-confirm]")).not_to_be_visible()
            page.locator("[data-virtual-key-secret-close]").click()
            expect(page.locator("[data-virtual-key-secret-close]")).not_to_be_visible()
            page.locator(
                f'[data-ui-action="virtual-key-revoke"][data-key-id="{key["id"]}"]'
            ).click()
            page.locator("[data-dialog-confirm]").click()
            expect(page.locator("[data-dialog-confirm]")).not_to_be_visible()
            records = context.request.get(base + "/api/virtual-keys").json()["data"]
            assert next(item for item in records if item["id"] == key["id"])["status"] == "revoked"

        def identity_create():
            page.goto(base + "/identity", wait_until="networkidle")
            page.locator("#identityCreateButton").click()
            page.locator("#identityCreateIssuer").fill("https://identity.example.invalid")
            page.locator("#identityCreateSubject").fill("DEMO-round2-user")
            page.locator("#identityCreateSubmit").click()
            expect(page.locator("#identityCreateDialog")).not_to_be_visible()
            expect(page.locator("#identityTab")).to_contain_text("DEMO-round2-user")
            assert (
                len(context.request.get(base + "/api/identity/identities").json()["identities"])
                == 6
            )

        def model_quality_settings():
            page.goto(base + "/models", wait_until="networkidle")
            with page.expect_response(
                lambda response: (
                    response.url.endswith("/api/model-routes/polaris")
                    and response.request.method in ("PATCH", "POST")
                )
            ) as response:
                page.locator("#saveModelPoolBtn").click()
            assert response.value.ok
            page.goto(base + "/ai-quality", wait_until="networkidle")
            page.locator('input[name="qualityProfile"][value="quality"]').check()
            with page.expect_response("**/api/quality-policy") as response:
                page.locator("#qualitySaveButton").click()
            assert response.value.ok
            page.reload(wait_until="networkidle")
            expect(page.locator('input[name="qualityProfile"][value="quality"]')).to_be_checked()
            page.goto(base + "/config", wait_until="networkidle")
            page.locator("#upstreamTimeoutSeconds").fill("125")
            with page.expect_response("**/api/config/save") as response:
                page.locator('[data-ui-action="save-config"]').click()
            assert response.value.ok
            page.reload(wait_until="networkidle")
            expect(page.locator("#upstreamTimeoutSeconds")).to_have_value("125")

        def quota_error_retry():
            dialog = open_credential("demo-muse_code-01.json")
            expect(dialog.locator("[data-management-quota]")).to_contain_text("88%")
            pattern = "**/api/credentials/quota/demo-muse_code-01.json?*"

            def fail(route):
                route.fulfill(status=503, json={"detail": "DEMO quota unavailable"})

            context.route(pattern, fail)
            dialog.locator('[data-management-load="quota"]').click()
            expect(dialog.locator("[data-management-quota]")).to_contain_text(
                "DEMO quota unavailable"
            )
            expect(dialog.locator("[data-management-quota]")).not_to_contain_text("88%")
            expect(dialog.locator("[data-management-models]")).to_contain_text("muse-code/")
            context.unroute(pattern, fail)
            dialog.locator('[data-management-load="quota"]').click()
            expect(dialog.locator("[data-management-quota]")).to_contain_text("88%")
            dialog.locator("[data-dialog-close]").click()

        def provider_quota_presets():
            from demo_catalog import catalog

            for provider, number, cards in (
                ("google_antigravity", 1, len(catalog("google_antigravity")[0])),
                ("grok", 2, 3),
                ("kiro", 2, 3),
            ):
                dialog = open_credential(f"demo-{provider}-{number:02}.json")
                quota = dialog.locator("[data-management-quota]")
                expect(quota.locator(".modal-quota-card")).to_have_count(cards)
                if provider == "google_antigravity":
                    for model in catalog(provider)[0]:
                        expect(quota).to_contain_text(model)
                    expect(quota).not_to_contain_text("Hạn mức 5 giờ")
                if provider == "kiro":
                    expect(quota).to_contain_text("Credits")
                    expect(quota).to_contain_text("Dùng thử")
                    expect(quota).to_contain_text("WELCOME")
                if provider == "grok":
                    expect(quota).to_contain_text("coding")
                page.screenshot(path=str(output / f"quota-{provider}.png"))
                page.locator(".credential-management-modal [data-dialog-close]").click()

        try:
            run("all-provider-filters-and-deep-link", provider_filters)
            run("provider-summary-readable-at-four-widths", dashboard_layout)
            if not regressions_only:
                for name, action in (
                    ("credential-edit-toggle-cancel-delete", credential_edit_toggle_delete),
                    ("pagination-selection-filter-empty", pagination_selection),
                    ("key-create-edit-rotate-revoke", key_lifecycle),
                    ("identity-create", identity_create),
                    ("model-quality-settings-persist", model_quality_settings),
                    ("quota-error-retry-independent-sections", quota_error_retry),
                    ("provider-specific-quota-presets", provider_quota_presets),
                ):
                    run(name, action)
        finally:
            (output / "report.json").write_text(
                json.dumps({"results": results, "errors": errors}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            browser.close()
    assert results and all(result["passed"] for result in results) and not errors, "See report.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", default="before")
    parser.add_argument("--regressions-only", action="store_true")
    parser.add_argument("--only", nargs="+")
    args = parser.parse_args()
    main(args.stage, args.regressions_only, args.only)
