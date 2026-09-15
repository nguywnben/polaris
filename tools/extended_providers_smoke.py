"""Exercise all additional provider forms without external account calls."""

import io
import json
import sys
import zipfile
from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime, install_fixtures
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("kimi", "kiro", "cloudflare", "nvidia", "opencode", "poolside", "kimchi", "kilo")


def verify_import(page, workspace, base, provider):
    """Exercise the real multipart route and isolated storage, not a mocked POST."""
    panel = workspace.locator(".extended-provider-import")
    input_file = panel.locator('input[type="file"]')
    pending = panel.locator(".file-list").locator("..")
    payload = {"provider": provider, "api_key": "synthetic-import-only-key"}
    if provider == "cloudflare":
        payload["account_id"] = "a" * 32
    if provider == "opencode":
        payload["plan"] = "go"
    if provider == "kiro":
        payload["region"] = "eu-central-1"
    path = f"/api/providers/extended/{provider}/credentials/import"
    for zipped in (False, True):
        content = json.dumps(payload).encode()
        if zipped:
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as stream:
                stream.writestr("credential.json", content)
            content = archive.getvalue()
        if zipped:
            transfer = page.evaluate_handle(
                """bytes => {
                const transfer = new DataTransfer();
                transfer.items.add(new File([new Uint8Array(bytes)], 'credential.zip', {type: 'application/zip'}));
                return transfer;
            }""",
                list(content),
            )
            panel.locator(".upload-area").dispatch_event("drop", {"dataTransfer": transfer})
            transfer.dispose()
        else:
            input_file.set_input_files(
                {"name": "credential.json", "mimeType": "application/json", "buffer": content}
            )
        with page.expect_response(lambda response: response.url.endswith(path)) as result:
            pending.locator("button").filter(has_text="Nhập").click()
        response = result.value
        assert response.ok, response.text()
        data = response.json()
        assert data["error_count"] == 0, data
        assert data["uploaded_count"] + data.get("skipped_count", 0) == 1, data
        assert data["skipped_count"] == int(zipped), data
        assert "synthetic-import-only-key" not in json.dumps(data)
        expect(pending).to_be_hidden()
        expect(panel).to_have_attribute("aria-busy", "false")
        assert page.url == base + "/providers"
    with page.expect_download() as download:
        panel.locator('[data-i18n="provider.ext.template"]').click()
    sample = json.loads(Path(download.value.path()).read_text())
    assert sample["provider"] == provider and sample["api_key"] == "<YOUR_API_KEY>"
    # A wrong provider must not enter this workspace's pool, and remains retryable.
    payload["provider"] = "nvidia" if provider != "nvidia" else "kimi"
    input_file.set_input_files(
        {
            "name": "wrong.json",
            "mimeType": "application/json",
            "buffer": json.dumps(payload).encode(),
        }
    )
    with page.expect_response(lambda response: response.url.endswith(path)) as result:
        pending.locator("button").filter(has_text="Nhập").click()
    failure = result.value.json()
    assert failure["error_count"] == 1
    assert "Credential belongs to a different provider." not in failure["results"][0]["message"]
    expect(pending).to_be_visible()
    expect(panel).to_have_attribute("aria-busy", "false")
    pending.locator("button").filter(has_text="Xóa").last.click()
    expect(pending).to_be_hidden()


def main():
    with disposable_runtime() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.route("https://**", lambda route: route.abort())
        page = context.new_page()
        install_fixtures(page)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        saved = []
        attempted = set()

        def add_credential(route):
            payload = route.request.post_data_json
            assert payload["api_key"] == "fixture-key-not-a-real-secret"
            if route.request.url not in attempted:
                attempted.add(route.request.url)
                route.fulfill(
                    status=401,
                    content_type="application/json",
                    body=json.dumps({"detail": "Synthetic rejected key."}),
                )
                return
            saved.append((route.request.url, payload))
            route.fulfill(
                status=201,
                content_type="application/json",
                body=json.dumps(
                    {
                        "success": True,
                        "credential_saved": True,
                        "connection_test_required": True,
                        "filename": "fixture.json",
                        "model_count": 2,
                    }
                ),
            )

        page.route("**/api/providers/extended/*/credentials", add_credential)
        page.goto(base + "/setup", wait_until="networkidle")
        page.locator("#setupPassword").fill(PASSWORD)
        page.locator("#setupPasswordConfirm").fill(PASSWORD)
        page.locator("#setupSubmitButton").click()
        expect(page).to_have_url(base + "/dashboard")
        page.goto(base + "/providers", wait_until="networkidle")
        expect(page.locator('#providerCatalog [role="tab"]')).to_have_count(17)
        shots = ROOT / "temp" / "extended-providers-ui"
        shots.mkdir(parents=True, exist_ok=True)
        for provider in PROVIDERS:
            page.locator("#providerCatalogSearch").fill(provider)
            selector = page.locator(f"#providerSelector-{provider}")
            selector.click()
            workspace = page.locator(f"#providerWorkspace-{provider}")
            expect(workspace).to_be_visible()
            expect(workspace.locator(".provider-tools-grid > .tool-panel")).to_have_count(2)
            expect(workspace.locator('input[type="file"]')).to_have_count(1)
            expect(workspace.locator(".upload-area")).to_be_visible()
            expect(workspace.locator('[type="password"]')).not_to_be_focused()
            toggle = workspace.locator(".setup-secret-toggle")
            expect(toggle).to_be_hidden()
            key = workspace.locator('[name="api_key"]')
            key.fill("fixture-key-not-a-real-secret")
            expect(toggle).to_be_visible()
            toggle.click()
            expect(key).to_have_attribute("type", "text")
            toggle.click()
            if provider == "cloudflare":
                workspace.locator('[name="account_id"]').fill("a" * 32)
            workspace.locator("summary").click()
            if provider == "opencode":
                workspace.locator('[name="plan"]').select_option("go")
                expect(workspace.locator('[name="base_url"]')).to_have_attribute(
                    "placeholder", "https://opencode.ai/zen/go/v1"
                )
            # External advanced fields remain associated with the add form.
            values = workspace.locator("form").evaluate(
                "(form) => Object.fromEntries(new FormData(form))"
            )
            assert ("region" if provider == "kiro" else "base_url") in values
            if provider == "kilo":
                workspace.locator('[name="organization_id"]').fill(
                    "00000000-0000-0000-0000-000000000001"
                )
            workspace.locator('[data-i18n="provider.ext.reset_connection"]').click()
            if provider == "kilo":
                expect(workspace.locator('[name="organization_id"]')).to_have_value("")
            expect(key).to_have_value("fixture-key-not-a-real-secret")
            for width, theme in (
                (1440, "light"),
                (1440, "dark"),
                (768, "light"),
                (768, "dark"),
                (320, "light"),
                (320, "dark"),
            ):
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("(theme) => PolarisTheme.setPreference(theme)", theme)
                expect(page.locator("html")).not_to_have_class("theme-switching")
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
                    provider,
                    width,
                    theme,
                )
                if provider == "kimchi":
                    for logo in page.locator('img[src$="/kimchi-logo.png"]').all():
                        expect(logo).to_have_css("border-radius", "50%")
                    for frame in page.locator(".extended-logo-kimchi").all():
                        expect(frame).to_have_css("background-color", "rgba(0, 0, 0, 0)")
                if "--capture" in sys.argv and provider in (
                    "kimi",
                    "kiro",
                    "cloudflare",
                    "opencode",
                    "kimchi",
                ):
                    page.screenshot(
                        path=str(shots / f"{provider}-{width}-{theme}.png"), full_page=True
                    )
            with page.expect_response(
                lambda response: response.url.endswith(f"/extended/{provider}/credentials")
            ):
                workspace.locator('[type="submit"]').click()
            expect(workspace.locator('[type="submit"]')).to_be_enabled()
            expect(key).to_have_value("fixture-key-not-a-real-secret")
            expect(key).not_to_be_focused()
            workspace.locator('[type="submit"]').click()
            expect(key).to_have_value("")
            expect(workspace.locator("[data-extended-saved]")).to_have_count(0)
            page.set_viewport_size({"width": 1440, "height": 1000})
            verify_import(page, workspace, base, provider)
        assert len(saved) == 8, saved
        # Open the actual pool editor for a credential saved by the import route.
        page.locator('#providerWorkspace-kilo [data-tab="pool"]').click()
        for provider in PROVIDERS:
            name = page.evaluate("id => EXTENDED_PROVIDER_UI[id].name", provider)
            imported = page.locator(".cred-card").filter(
                has=page.locator(".cred-provider-name", has_text=name)
            )
            expect(imported).to_have_count(1)
            expect(imported.locator(".status-badge", has_text="API key")).to_have_count(1)
        card = (
            page.locator(".cred-card")
            .filter(has=page.locator(".cred-provider-name", has_text="OpenCode"))
            .first
        )
        expect(card).to_be_visible()
        card.locator(".cred-actions-secondary > summary").click()
        card.locator('[data-credential-command="edit"]').click()
        editor = page.locator("[data-credential-edit-form]")
        expect(editor).to_be_visible()
        expect(editor.locator('[name="plan"]')).to_have_value("go")
        expect(editor.locator('[name="api_key"]')).to_have_value("")
        expect(editor.locator('[name="api_key"]')).not_to_be_focused()
        editor.locator('[name="plan"]').select_option("zen")
        expect(editor.locator('[name="base_url"]')).to_have_value("https://opencode.ai/zen/v1")
        editor.locator('[name="plan"]').select_option("go")
        expect(editor.locator('[name="base_url"]')).to_have_value("https://opencode.ai/zen/go/v1")
        editor.locator("[data-credential-edit-cancel]").click()
        expect(editor).to_have_count(0)
        assert not errors, errors
        context.close()
        browser.close()
    print(
        "Extended providers: 8 forms, 48 responsive/theme cases, 24 real JSON/ZIP/rejection imports, no page errors."
    )


if __name__ == "__main__":
    main()
