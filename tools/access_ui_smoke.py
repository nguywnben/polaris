"""Access UI verification with isolated storage and synthetic keys only."""

from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    state = {"error": False, "records": []}

    def keys(route):
        if state["error"]:
            route.fulfill(status=503, json={"detail": "Synthetic unavailable"})
        else:
            route.fulfill(json={"success": True, "data": state["records"]})

    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.route("https://**", lambda route: route.abort())
        context.route("**/api/auth/keys", lambda route: route.fulfill(json={
            "success": True, "api_key": "sk-polaris-synthetic-not-a-real-key", "managed_by_env": True,
        }))
        context.route("**/api/virtual-keys", keys)
        context.add_init_script("Object.defineProperty(navigator, 'clipboard', {value: {writeText: async text => { window.copiedText = text; }}})")
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        output = ROOT / "temp/access-ui"
        output.mkdir(parents=True, exist_ok=True)
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.goto(base + "/access", wait_until="networkidle")
            expect(page.locator(".virtual-key-pristine-copy")).to_be_visible()
            expect(page.locator('[data-ui-action="virtual-key-create"]:visible')).to_have_count(1)
            expect(page.locator("#regenerateApiKeyBtn")).to_be_disabled()
            protocol_box = page.locator("#accessProtocol").bounding_box()
            format_box = page.locator("#accessClientFormat").bounding_box()
            assert abs(protocol_box["y"] - format_box["y"]) < 2
            eye_box = page.locator("#toggleApiKeyVisibilityBtn").bounding_box()
            input_box = page.locator("#apiKey").bounding_box()
            assert input_box["x"] < eye_box["x"] < input_box["x"] + input_box["width"]
            page.locator("#toggleApiKeyVisibilityBtn").click()
            expect(page.locator("#apiKey")).to_have_attribute("type", "text")
            page.locator("#toggleApiKeyVisibilityBtn").click()
            expect(page.locator("#apiKey")).to_have_attribute("type", "password")
            page.locator("#openaiEndpointUrl").click()
            assert page.evaluate("window.copiedText") == base + "/v1"
            for protocol in ("openai_chat", "openai_responses", "anthropic", "gemini"):
                page.locator("#accessProtocol").select_option(protocol)
                for format_name in ("curl", "powershell", "python", "node"):
                    page.locator("#accessClientFormat").select_option(format_name)
                    page.locator("#copyAccessClientExample").click()
                    copied = page.evaluate("window.copiedText")
                    assert "<YOUR_POLARIS_VIRTUAL_KEY>" in copied and "synthetic" not in copied
            page.locator("#accessClientFormat").select_option("curl")
            page.locator("#accessProtocol").select_option("openai_chat")
            state["records"] = [{"id": "fixture", "name": "Synthetic client", "key_preview": "sk-polaris-…fixture", "status": "active", "enabled": True, "revision": 1, "scopes": ["inference:openai"], "allowed_models": ["polaris"]}]
            page.locator('[data-ui-action="virtual-key-refresh"]').click()
            expect(page.locator(".virtual-key-card")).to_have_count(1)
            page.locator("#virtualKeySearch").fill("not-found")
            expect(page.locator(".virtual-key-filtered-copy")).to_be_visible()
            state["records"] = []
            page.locator('[data-ui-action="virtual-key-refresh"]').click()
            expect(page.locator("#virtualKeySearch")).to_be_visible()
            page.locator("#virtualKeySearch").fill("")
            state["error"] = True
            page.locator('[data-ui-action="virtual-key-refresh"]').click()
            expect(page.locator("#virtualKeyState")).to_be_visible()
            state["error"] = False
            page.locator("#virtualKeyState button").click()
            expect(page.locator("#virtualKeyState")).to_be_hidden()
            for locale in ("en", "vi"):
                page.evaluate("lang => { AppState.lang = lang; applyLanguage(); }", locale)
                assert "access.empty_title" not in page.locator("#virtualKeyEmptyState").inner_text()
            for width in (1440, 1024, 768, 360, 320):
                page.set_viewport_size({"width": width, "height": 1000})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
                page.evaluate("window.scrollTo(0,0)")
                page.mouse.move(2, 2)
                if width in (1440, 360):
                    page.screenshot(path=str(output / f"access-{width}.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.locator('[data-ui-action="virtual-key-create"]').click()
            expect(page.locator("#virtualKeyForm")).to_be_visible()
            read = page.locator('[name="scopes"][value="management:read"]')
            write = page.locator('[name="scopes"][value="management:write"]')
            write.check()
            expect(read).to_be_checked()
            read.uncheck()
            expect(write).not_to_be_checked()
            page.locator('[name="name"]').fill("Synthetic draft")
            page.screenshot(path=str(output / "modal-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 360, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(output / "modal-mobile.png"), full_page=True)
            page.keyboard.press("Escape")
            expect(page.locator("#virtualKeyForm")).to_have_count(0)
            page.emulate_media(color_scheme="dark")
            page.screenshot(path=str(output / "access-dark-mobile.png"), full_page=True)
            assert not errors, errors
            print("PASS: access empty/filter/error, secret visibility, URL/example copy, 16 examples, modal scopes, 5 widths, en/vi, dark; no real keys changed")
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
