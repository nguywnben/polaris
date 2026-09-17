"""Exercise all additional provider forms without external account calls."""

import io
import json
import sys
import zipfile
from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime, install_fixtures
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = (
    "kimi",
    "kiro",
    "cloudflare",
    "nvidia",
    "opencode",
    "poolside",
    "kimchi",
    "kilo",
    "meta",
    "groq",
    "deepseek",
    "mistral",
    "cerebras",
)
CATALOG_COUNT = 9 + len(PROVIDERS) + 1  # Muse Code has its own OAuth-only smoke test.


def verify_catalog_layout(page, widths=(1440, 1201, 1024, 768, 360, 320)):
    search = page.locator("#providerCatalogSearch")
    for width in widths:
        page.set_viewport_size({"width": width, "height": 1000})
        search.fill("")
        while page.locator("#providerCatalogPrevBtn").is_enabled():
            page.locator("#providerCatalogPrevBtn").click()
        page.wait_for_timeout(100)
        dimensions = []
        for _ in range(3):
            dimensions.extend(
                page.locator('#providerCatalog [role="tab"]:visible').evaluate_all(
                    """cards => cards.map(card => {
                    const r = card.getBoundingClientRect();
                    const p = card.querySelector('.provider-summary p');
                    const footer = card.querySelector('.provider-capabilities');
                    return [r.width, r.height, p.getBoundingClientRect().top - r.top,
                        footer.getBoundingClientRect().top - r.top,
                        card.scrollHeight <= card.clientHeight + 1 && p.scrollHeight <= p.clientHeight + 1];
                })"""
                )
            )
            if not page.locator("#providerCatalogNextBtn").is_enabled():
                break
            page.locator("#providerCatalogNextBtn").click()
        assert len(dimensions) == CATALOG_COUNT, dimensions
        assert all(d[4] for d in dimensions), (width, dimensions)
        if width > 600:
            for coordinate in (0, 1, 2, 3):
                assert (
                    max(d[coordinate] for d in dimensions) - min(d[coordinate] for d in dimensions)
                    <= 1
                ), (width, dimensions)
            search.fill("kimchi")
            expect(page.locator('#providerCatalog [role="tab"]:visible')).to_have_count(1)
            assert (
                abs(
                    page.locator("#providerSelector-kimchi").bounding_box()["height"]
                    - dimensions[0][1]
                )
                <= 1
            )
        else:
            assert page.locator("#providerCatalog").evaluate(
                "catalog => [...catalog.querySelectorAll('p')].every(p => !p.clientHeight || p.scrollHeight <= p.clientHeight + 1)"
            )
    search.fill("")
    page.set_viewport_size({"width": 1440, "height": 1000})


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
    assert sample["provider"] == provider
    if provider == "kiro":
        assert (
            sample["credential_type"] == "oauth"
            and sample["refresh_token"] == "<YOUR_REFRESH_TOKEN>"
        )
        assert "api_key" not in sample
    else:
        assert sample["api_key"] == "<YOUR_API_KEY>"
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


def verify_kiro_device_ui(page, workspace):
    """Exercise device form states without signing in to a real provider."""
    calls = []

    def device_api(route):
        action = route.request.url.rsplit("/", 1)[-1]
        calls.append((action, route.request.post_data_json))
        result = {"status": "cancelled"}
        if action == "start":
            result = {
                "flow_id": "kiro_synthetic",
                "verification_uri": "https://app.kiro.dev/device",
                "user_code": "TEST-CODE",
                "interval": 0,
                "expires_in": 300,
            }
        elif action == "complete":
            result = {"status": "complete", "credential_saved": True}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(result))

    page.route("**/api/providers/kiro/oauth/*", device_api)
    workspace.locator("#kiroAwsLogin > summary").click()
    form = workspace.locator("#kiroOAuthForm")
    panel = form.locator("..")
    pending = panel.locator(".provider-upload-section")
    for method in ("builder-id", "identity-center"):
        form.locator('[name="method"]').select_option(method)
        if method in ("builder-id", "identity-center"):
            workspace.locator(".extended-provider-advanced > summary").click()
            expect(workspace.locator('[name="token_region"]')).to_be_visible()
            workspace.locator(".extended-provider-advanced > summary").click()
        else:
            expect(workspace.locator('[name="token_region"]')).to_be_hidden()
        if method == "identity-center":
            form.locator('[name="start_url"]').fill("https://example.awsapps.com/start")
        form.locator('[type="submit"]').click()
        expect(pending).to_be_visible()
        expect(pending.locator(".provider-device-code")).to_have_text("TEST-CODE")
        expect(pending.locator("a")).to_have_attribute("target", "_blank")
        assert calls[-1][1]["method"] == method
        expect(workspace.locator('[name="token_region"]')).not_to_be_focused()
        if method == "identity-center":
            pending.locator('[data-i18n="runtime.check_authorization"]').click()
        else:
            pending.locator('[data-i18n="btn_cancel"]').click()
        expect(pending).to_be_hidden()
    assert [action for action, _ in calls].count("start") == 2
    assert [action for action, _ in calls].count("complete") == 1
    form.locator('[name="method"]').select_option("builder-id")
    page.unroute("**/api/providers/kiro/oauth/*", device_api)


def main():
    with disposable_runtime() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.route("https://**", lambda route: route.abort())
        context.route(
            "**/api/credentials/quota/**",
            lambda route: route.fulfill(
                json={
                    "success": True,
                    "quota_type": "account_rate_limits",
                    "quota_status": "unavailable",
                    "windows": [],
                }
            ),
        )
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
        expect(page.locator('#providerCatalog [role="tab"]')).to_have_count(CATALOG_COUNT)
        verify_catalog_layout(page)
        for locale in (
            "en",
            "zh-CN",
            "zh-TW",
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
        ):
            with page.expect_navigation(wait_until="networkidle"):
                page.evaluate("locale => changeLanguage(locale)", locale)
            verify_catalog_layout(page, widths=(1440, 1201, 320))
            # Generated forms must resolve the same copy as legacy HTML in every locale.
            assert page.evaluate("""() => [...document.querySelectorAll(
                '.provider-workspace [data-i18n], .provider-workspace [data-i18n-placeholder]'
            )].every(el => {
                const key = el.dataset.i18n || el.dataset.i18nPlaceholder;
                return t(key) && t(key) !== key;
            })""")
            # The removed onboarding notice must not return on locale changes.
            expect(
                page.locator('[data-i18n="provider.ext.meta_contributor_notice"]')
            ).to_have_count(0)
            expect(
                page.locator('[aria-describedby="extended-meta-contributor-notice"]')
            ).to_have_count(0)
        with page.expect_navigation(wait_until="networkidle"):
            page.evaluate("changeLanguage('vi')")
        page.evaluate("PolarisTheme.setPreference('dark')")
        verify_catalog_layout(page, widths=(1440, 768, 320))
        if "--capture" in sys.argv:
            catalog_shots = ROOT / "temp" / "provider-card-layout"
            catalog_shots.mkdir(parents=True, exist_ok=True)
            for width, theme in ((1440, "light"), (1440, "dark"), (320, "light"), (320, "dark")):
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => PolarisTheme.setPreference(theme)", theme)
                while page.locator("#providerCatalogPrevBtn").is_enabled():
                    page.locator("#providerCatalogPrevBtn").click()
                expect(page.locator("html")).not_to_have_class("theme-switching")
                page.locator("#providerCatalog").screenshot(
                    path=str(catalog_shots / f"{width}-{theme}.png")
                )
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.evaluate("PolarisTheme.setPreference('light')")
        shots = ROOT / "temp" / "extended-providers-ui"
        shots.mkdir(parents=True, exist_ok=True)
        for provider in PROVIDERS:
            page.locator("#providerCatalogSearch").fill(provider)
            selector = page.locator(f"#providerSelector-{provider}")
            selector.click()
            workspace = page.locator(f"#providerWorkspace-{provider}")
            expect(workspace).to_be_visible()
            expect(workspace.locator(".provider-tools-grid > *")).to_have_count(2)
            form = workspace.locator(f"#extended-{provider}-credential-form")
            if provider == "kiro":
                expect(workspace.locator("#kiroBrowserForm")).to_be_visible()
                verify_kiro_device_ui(page, workspace)
                workspace.locator("summary", has_text="API Key").click()
            expect(form).to_be_hidden()
            workspace.locator(".provider-key-entry-button").click()
            expect(form).to_be_visible()
            expect(workspace.locator('[data-i18n="provider.ext.open_pool"]')).to_have_count(0)
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
            workspace.locator(".extended-provider-advanced > summary").click()
            for advanced_input in workspace.locator(".extended-provider-advanced input").all():
                expect(advanced_input).to_have_attribute("placeholder")
            if provider == "meta":
                expect(workspace.locator('[name="base_url"]')).to_have_value(
                    "https://api.meta.ai/v1"
                )
                expect(workspace.locator('[name="base_url"]')).to_have_attribute("placeholder")
                expect(
                    workspace.locator(
                        '[name="account_id"], [name="organization_id"], [name="plan"], [name="region"]'
                    )
                ).to_have_count(0)
                expect(
                    workspace.locator('[data-i18n="provider.ext.meta_contributor_notice"]')
                ).to_have_count(0)
            if provider == "opencode":
                workspace.locator('[name="plan"]').select_option("go")
                expect(workspace.locator('[name="base_url"]')).to_have_value(
                    "https://opencode.ai/zen/go/v1"
                )
                expect(workspace.locator('[name="base_url"]')).to_have_attribute("placeholder")
            # External advanced fields remain associated with the add form.
            values = form.evaluate("(form) => Object.fromEntries(new FormData(form))")
            assert ("region" if provider == "kiro" else "base_url") in values
            if provider == "kilo":
                workspace.locator('[name="organization_id"]').fill(
                    "00000000-0000-0000-0000-000000000001"
                )
            if provider == "meta":
                expect(workspace.locator('[name="base_url"]')).to_have_attribute("readonly", "")
                expect(workspace.locator('[name="base_url"]')).to_have_value(
                    "https://api.meta.ai/v1"
                )
                expect(
                    workspace.locator('[data-i18n="provider.ext.reset_connection"]')
                ).to_have_count(0)
            else:
                workspace.locator('[data-i18n="provider.ext.reset_connection"]').click()
            if provider == "kilo":
                expect(workspace.locator('[name="organization_id"]')).to_have_value("")
            expect(key).to_have_value("fixture-key-not-a-real-secret")
            for width, theme in (
                (1440, "light"),
                (1440, "dark"),
                (768, "light"),
                (768, "dark"),
                (1024, "light"),
                (1024, "dark"),
                (360, "light"),
                (360, "dark"),
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
                    for logo in page.locator('img[src$="/kimchi.png"]').all():
                        expect(logo).to_have_css("border-radius", "50%")
                    for frame in page.locator(".extended-logo-kimchi").all():
                        expect(frame).to_have_css("background-color", "rgba(0, 0, 0, 0)")
                if "--capture" in sys.argv and provider in (
                    "kimi",
                    "kiro",
                    "cloudflare",
                    "opencode",
                    "kimchi",
                    "meta",
                    "groq",
                    "deepseek",
                    "mistral",
                    "cerebras",
                ):
                    page.screenshot(
                        path=str(shots / f"{provider}-{width}-{theme}.png"), full_page=True
                    )
            with page.expect_response(
                lambda response: response.url.endswith(f"/extended/{provider}/credentials")
            ):
                form.locator('[type="submit"]').click()
            expect(form.locator('[type="submit"]')).to_be_enabled()
            expect(key).to_have_value("fixture-key-not-a-real-secret")
            expect(key).not_to_be_focused()
            form.locator('[type="submit"]').click()
            expect(key).to_have_value("")
            expect(form).to_be_hidden()
            expect(workspace.locator(f"#extended-{provider}SaveResult")).to_be_visible()
            expect(workspace.locator("[data-extended-saved]")).to_have_count(0)
            page.set_viewport_size({"width": 1440, "height": 1000})
            verify_import(page, workspace, base, provider)
        assert len(saved) == len(PROVIDERS), saved
        # Open the actual pool editor for a credential saved by the import route.
        page.locator('#primaryNavigation [data-tab="credentials"]').click()
        for provider in PROVIDERS:
            imported = (
                page.locator(".credential-provider-group")
                .filter(has=page.locator(f"#credentialProviderGroup-{provider}"))
                .locator(".cred-card")
            )
            expect(imported).to_have_count(1)
            key_label = page.evaluate("t('credentials.workspace.api_key')")
            expect(imported.locator(".status-badge", has_text=key_label)).to_have_count(1)
        card = (
            page.locator(".credential-provider-group")
            .filter(has=page.locator("#credentialProviderGroup-opencode"))
            .locator(".cred-card")
            .first
        )
        expect(card).to_be_visible()
        card.locator('[data-credential-command="manage"]').click()
        expect(page.locator('[role="dialog"]')).to_have_count(1)
        editor = page.locator("[data-credential-edit-form]")
        expect(editor).to_be_visible()
        expect(editor.locator('[name="plan"]')).to_have_value("go")
        expect(editor.locator('[name="api_key"]')).to_have_value("")
        expect(editor.locator('[name="api_key"]')).not_to_be_focused()
        editor.locator('[name="plan"]').select_option("zen")
        expect(editor.locator('[name="base_url"]')).to_have_value("https://opencode.ai/zen/v1")
        editor.locator('[name="plan"]').select_option("go")
        expect(editor.locator('[name="base_url"]')).to_have_value("https://opencode.ai/zen/go/v1")
        editor.locator('[name="plan"]').select_option("zen")
        editor.locator("[data-credential-edit-cancel]").click()
        expect(editor.locator('[name="plan"]')).to_have_value("go")
        expect(editor.locator('[name="base_url"]')).to_have_value("https://opencode.ai/zen/go/v1")
        expect(editor).to_be_visible()
        page.locator('[role="dialog"] [data-dialog-close]').click()
        expect(editor).to_have_count(0)
        meta_group = page.locator(".credential-provider-group").filter(
            has=page.locator("#credentialProviderGroup-meta")
        )
        expect(meta_group.locator('img[src$="/meta-model-api.png"]')).to_have_count(1)
        meta_group.locator('[data-credential-command="manage"]').click()
        expect(page.locator('[role="dialog"]')).to_have_count(1)
        meta_editor = page.locator("[data-credential-edit-form]")
        expect(meta_editor).to_be_visible()
        expect(meta_editor.locator('[name="base_url"]')).to_have_count(0)
        expect(meta_editor.locator('[name="api_key"]')).to_have_value("")
        expect(meta_editor.locator('[name="api_key"]')).not_to_be_focused()
        expect(
            meta_editor.locator(
                '[name="account_id"], [name="organization_id"], [name="plan"], [name="region"]'
            )
        ).to_have_count(0)
        meta_editor.locator("[data-credential-edit-cancel]").click()
        expect(meta_editor).to_be_visible()
        page.locator('[role="dialog"] [data-dialog-close]').click()
        expect(meta_editor).to_have_count(0)
        assert not errors, errors
        context.close()
        browser.close()
    print(
        f"Provider catalog: {CATALOG_COUNT} cards, 15 locales, pagination/search and responsive layout passed. "
        f"Extended providers: {len(PROVIDERS)} forms, {len(PROVIDERS) * 10} responsive/theme cases, "
        f"{len(PROVIDERS) * 3} real JSON/ZIP/rejection imports, Meta pool editor, no page errors."
    )


if __name__ == "__main__":
    main()
