"""Regression checks for consistent provider onboarding, with disposable data only."""

import json
import sys
from pathlib import Path

from browser_smoke import PASSWORD, ROOT, disposable_runtime, install_fixtures
from playwright.sync_api import expect, sync_playwright


def main():
    with disposable_runtime() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.grant_permissions(["clipboard-read", "clipboard-write"])
        context.route("https://**", lambda route: route.abort())
        page = context.new_page()
        install_fixtures(page)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/setup", wait_until="networkidle")
        page.locator("#setupPassword").fill(PASSWORD)
        page.locator("#setupPasswordConfirm").fill(PASSWORD)
        page.locator("#setupSubmitButton").click()
        expect(page).to_have_url(base + "/dashboard")
        page.goto(base + "/providers", wait_until="networkidle")
        verify_examples(page)
        for provider in ("openai_platform", "xai_console", "kimi", "poolside"):
            page.locator("#providerCatalogSearch").fill(provider)
            selector = page.locator(f'#providerCatalog [data-provider="{provider}"]')
            selector.click()
            workspace = page.locator("#" + selector.get_attribute("aria-controls"))
            expect(workspace.get_by_role("button", name="Thêm khóa", exact=True)).to_be_visible()
            key = workspace.locator('input[data-secret-lifetime="submit"], input[name="api_key"]')
            expect(key).to_have_attribute("placeholder", "Dán khóa API của bạn")
            expect(workspace.locator(".upload-title")).to_have_text("Thả tệp khóa API vào đây")
            assert workspace.locator(".provider-import-panel > .page-actions").count() == 0
        if "--quick" not in sys.argv:
            verify_kiro_browser(page)
            verify_kiro(page)
            verify_layout(page)
        verify_kiro_routes(page)
        assert not errors, errors
        browser.close()
    print("Provider workspace consistency passed.")


def verify_examples(page):
    providers = [
        "google_antigravity",
        "google_ai_studio",
        "grok",
        "xai_console",
        "codex",
        "openai_platform",
        "claude_code",
        "claude_platform",
        "ollama",
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
    ]
    shots = ROOT / "temp" / "provider-examples"
    shots.mkdir(parents=True, exist_ok=True)
    for index, provider in enumerate(providers):
        page.locator("#providerCatalogSearch").fill(provider)
        selector = page.locator(f'#providerCatalog [data-provider="{provider}"]')
        selector.click()
        workspace = page.locator("#" + selector.get_attribute("aria-controls"))
        button = workspace.locator(f'.provider-import-heading [data-provider-example="{provider}"]')
        expect(button).to_have_count(1)
        expect(button).to_have_text("Tải tệp JSON mẫu")
        # Typed values must never appear in the downloaded example.
        workspace.locator('input[type="password"]').evaluate_all(
            "inputs => inputs.forEach(input => {input.value = 'FORM_SECRET_DO_NOT_EXPORT';})"
        )
        with page.expect_download() as downloaded:
            button.focus()
            button.press("Enter")
        result = downloaded.value
        assert result.suggested_filename == f"{provider}-example.json"
        content = Path(result.path()).read_text(encoding="utf-8")
        assert "FORM_SECRET_DO_NOT_EXPORT" not in content
        assert json.loads(content)["provider"] == provider
        workspace.locator('input[type="password"]').evaluate_all(
            "inputs => inputs.forEach(input => {input.value = '';})"
        )
        page.set_viewport_size({"width": 320 if index % 2 else 1440, "height": 1000})
        page.evaluate(
            "theme => PolarisTheme.setPreference(theme)", "dark" if index % 2 else "light"
        )
        expect(page.locator("html")).not_to_have_class("theme-switching")
        expect(button).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), provider
        if provider in {"google_antigravity", "openai_platform"}:
            workspace.screenshot(path=str(shots / f"{provider}.png"))
    page.evaluate("enhanceProviderWorkspaces()")
    expect(page.locator("[data-provider-example]")).to_have_count(22)
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.evaluate("PolarisTheme.setPreference('light')")


def verify_kiro_routes(page):
    """Real local routing/auth/CSRF and callback capture, without vendor calls."""

    def request(action, payload):
        return page.evaluate(
            """async ({action, payload}) => {
            const response = await fetch(`/api/providers/kiro/browser/${action}`, {
                method: 'POST', headers: getAuthHeaders(), body: JSON.stringify(payload)
            });
            return {status: response.status, body: await response.json()};
        }""",
            {"action": action, "payload": payload},
        )

    origin = page.evaluate("location.origin")
    started = request("start", {"callback_origin": origin})
    assert started["status"] == 200, started
    flow = started["body"]["flow_id"]
    assert request("complete", {"flow_id": flow})["body"]["status"] == "pending"
    callback = page.context.new_page()
    callback.goto(origin + f"/oauth/callback?state={flow}&code=synthetic&login_option=google")
    expect(callback).to_have_url(origin + "/callback?kiro=received")
    expect(callback.locator(".login-copy")).to_contain_text("tab Polaris")
    assert "synthetic" not in callback.content()
    callback.close()
    assert request("cancel", {"flow_id": flow})["status"] == 200
    assert request("complete", {"flow_id": flow})["status"] == 409


def verify_kiro(page):
    calls = []

    def respond(route):
        action = route.request.url.rsplit("/", 1)[-1]
        calls.append(action)
        payload = {"status": "cancelled"}
        if action == "start":
            payload = {
                "flow_id": "synthetic",
                "user_code": "TEST-CODE",
                "interval": 0,
                "expires_in": 300,
                "verification_uri": "https://app.kiro.dev/device",
            }
        if action == "complete":
            payload = {"status": "pending", "interval": 0}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("**/api/providers/kiro/oauth/*", respond)
    page.locator("#providerCatalogSearch").fill("kiro")
    page.locator("#providerSelector-kiro").click()
    workspace = page.locator("#providerWorkspace-kiro")
    workspace.locator("#kiroAwsLogin > summary").click()
    form = workspace.locator("#kiroOAuthForm")
    form.locator('[type="submit"]').click()
    pending = workspace.locator("#kiroAwsLogin .provider-device-flow")
    expect(pending).to_be_visible()
    expect(form).to_be_hidden()
    expect(pending.locator(".provider-device-code")).to_have_text("TEST-CODE")
    expect(pending.locator('[data-i18n="btn_cancel"]')).to_have_text("Hủy")
    expect(pending.locator('[data-i18n="provider.ui.open_login"]')).to_have_attribute(
        "href", "https://app.kiro.dev/device"
    )
    expect(pending.locator('[data-i18n="provider.ui.copy_code"]')).to_be_visible()
    pending.locator('[data-i18n="provider.ui.copy_code"]').click()
    assert page.evaluate("navigator.clipboard.readText()") == "TEST-CODE"
    expect(pending.locator(".provider-device-expiry")).to_contain_text("Hết hạn lúc")
    expect(workspace.locator("#extended-kiro-oauth-region")).to_be_disabled()
    shots = ROOT / "temp" / "provider-workspace-consistency"
    shots.mkdir(parents=True, exist_ok=True)
    for width, theme in ((1440, "light"), (320, "dark")):
        page.set_viewport_size({"width": width, "height": 1000})
        page.evaluate("theme => PolarisTheme.setPreference(theme)", theme)
        expect(page.locator("html")).not_to_have_class("theme-switching")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        workspace.screenshot(path=str(shots / f"kiro-pending-{width}-{theme}.png"))
    pending.locator('[data-i18n="runtime.check_authorization"]').click()
    expect(pending).to_be_visible()
    pending.locator('[data-i18n="btn_cancel"]').click()
    expect(pending).to_be_hidden()
    expect(form).to_be_visible()
    expect(form.locator('[type="submit"]')).to_be_focused()
    expect(workspace.locator("#extended-kiro-oauth-region")).to_be_enabled()
    assert calls == ["start", "complete", "cancel"]
    expect(workspace.locator(':scope > details[data-disclosure-kind="settings"]')).to_have_count(1)
    expect(form.locator('[name="region"]')).to_have_count(0)
    workspace.locator(".extended-provider-advanced > summary").click()
    page.set_viewport_size({"width": 1440, "height": 1000})
    workspace.screenshot(path=str(shots / "kiro-settings-1440-dark.png"))
    workspace.locator(".extended-provider-advanced > summary").click()
    workspace.locator("#kiroAwsLogin > summary").click()


def verify_kiro_browser(page):
    calls = []
    state = {"accepted": False, "invalid": True}

    def respond(route):
        action = route.request.url.rsplit("/", 1)[-1]
        calls.append(action)
        payload = {"status": "cancelled"}
        status = 200
        if action == "start":
            payload = {
                "flow_id": "synthetic",
                "expires_in": 600,
                "authorization_url": "https://app.kiro.dev/signin?state=synthetic",
            }
        elif action == "complete":
            payload = (
                {"status": "complete", "credential_saved": True}
                if state["accepted"]
                else {"status": "pending"}
            )
        elif action == "callback":
            if state["invalid"]:
                status = 400
            else:
                state["accepted"] = True
            payload = {"status": "received"}
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

    page.route("**/api/providers/kiro/browser/*", respond)
    # Simulate a blocked popup: the visible sign-in link must still work.
    page.evaluate("window.open = () => null")
    page.locator("#providerCatalogSearch").fill("kiro")
    page.locator("#providerSelector-kiro").click()
    workspace = page.locator("#providerWorkspace-kiro")
    form = workspace.locator("#kiroBrowserForm")
    pending = workspace.locator(".provider-browser-pending")
    expect(workspace.locator("#kiroOAuthForm")).to_be_hidden()
    form.locator("button").click()
    expect(pending).to_be_visible()
    expect(pending).to_be_focused()
    expect(pending.locator("a")).to_have_attribute(
        "href", "https://app.kiro.dev/signin?state=synthetic"
    )
    expect(pending.locator(".provider-device-code")).to_have_count(0)
    expect(pending.locator('[data-i18n="runtime.check_authorization"]')).to_have_count(0)
    pending.locator("summary").click()
    callback = pending.locator('input[name="callback_url"]')
    callback.fill("http://localhost:4283/oauth/callback?code=test&state=synthetic")
    pending.locator('button[type="submit"]').click()
    expect(callback).to_have_value("http://localhost:4283/oauth/callback?code=test&state=synthetic")
    expect(pending.locator('button[type="submit"]')).to_be_enabled()
    shots = ROOT / "temp" / "provider-workspace-consistency"
    shots.mkdir(parents=True, exist_ok=True)
    for width, theme in (
        (1440, "light"),
        (1024, "dark"),
        (768, "light"),
        (360, "dark"),
        (320, "dark"),
    ):
        page.set_viewport_size({"width": width, "height": 1000})
        page.evaluate("theme => PolarisTheme.setPreference(theme)", theme)
        expect(page.locator("html")).not_to_have_class("theme-switching")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        workspace.screenshot(path=str(shots / f"kiro-browser-{width}-{theme}.png"))
    state["invalid"] = False
    pending.locator('button[type="submit"]').click()
    expect(pending).to_be_hidden(timeout=10000)
    expect(callback).to_have_value("")
    assert "complete" in calls and calls.count("callback") == 2
    state["accepted"] = False
    form.locator("button").click()
    expect(pending).to_be_visible()
    pending.locator('[data-i18n="btn_cancel"]').click()
    expect(pending).to_be_hidden()
    assert calls[-1] == "cancel"
    page.unroute("**/api/providers/kiro/browser/*", respond)


def verify_layout(page):
    shots = ROOT / "temp" / "provider-workspace-consistency"
    shots.mkdir(parents=True, exist_ok=True)
    for provider in (
        "google_antigravity",
        "claude_code",
        "openai_platform",
        "kimi",
        "poolside",
        "kiro",
    ):
        page.locator("#providerCatalogSearch").fill(provider)
        selector = page.locator(f'#providerCatalog [data-provider="{provider}"]')
        selector.click()
        workspace = page.locator("#" + selector.get_attribute("aria-controls"))
        for width, theme in ((1440, "light"), (1440, "dark"), (768, "light"), (320, "dark")):
            page.set_viewport_size({"width": width, "height": 1000})
            page.evaluate("theme => PolarisTheme.setPreference(theme)", theme)
            expect(page.locator("html")).not_to_have_class("theme-switching")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                provider,
                width,
            )
            workspace.screenshot(path=str(shots / f"{provider}-{width}-{theme}.png"))


if __name__ == "__main__":
    main()
