"""Opening a Polaris modal never focuses a form control, even transiently."""

from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright


def main():
    failures = []
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(reduced_motion="reduce")
        context.route("https://**", lambda route: route.abort())
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/setup", wait_until="networkidle")
        page.locator("#setupPassword").fill(PASSWORD)
        page.locator("#setupPasswordConfirm").fill(PASSWORD)
        page.locator("#setupSubmitButton").click()
        expect(page).to_have_url(base + "/dashboard")
        cases = [
            ("identity", "/identity", "openIdentityCreateDialog()", "#identityCreateDialog"),
            ("prompt", "/access", "void showPromptModal('Test')", ".message-modal"),
            (
                "model",
                "/access",
                "void showModelTestModal('Test', {options: [{value:'test', label:'Test'}]})",
                ".message-modal",
            ),
            ("key-create", "/access", "openVirtualKeyForm()", ".message-modal"),
            (
                "key-edit",
                "/access",
                "openVirtualKeyForm({id:'test', name:'Test', enabled:true})",
                ".message-modal",
            ),
            (
                "key-secret",
                "/access",
                "showVirtualKeySecret('synthetic-test-value', 'access.create_key_title')",
                ".message-modal",
            ),
            ("credential", "/pool", "void showCredentialEditModal('focus-test')", ".message-modal"),
        ]
        for width, theme in ((1440, "light"), (360, "dark")):
            page.set_viewport_size({"width": width, "height": 900})
            page.emulate_media(color_scheme=theme)
            for name, route, action, selector in cases:
                page.goto(base + route, wait_until="networkidle")
                if name == "credential":
                    page.route(
                        "**/api/credentials/configuration/focus-test.json?mode=provider",
                        lambda route: route.fulfill(
                            json={
                                "editable": True,
                                "editable_fields": ["credential_label", "base_url", "api_key"],
                                "credential_label": "Test",
                                "base_url": "https://api.example.com",
                            }
                        ),
                    )
                    page.evaluate(
                        "AppState.credentialCardIndex['focus-test'] = {filename:'focus-test.json', managerType:'primary', providerName:'Test'}"
                    )
                page.evaluate("""() => {
                    window.__openingFieldFocus = [];
                    document.addEventListener('focusin', event => {
                        if (event.target.matches('input, textarea, select, [contenteditable="true"]'))
                            window.__openingFieldFocus.push(event.target.tagName);
                    });
                    const trigger = document.createElement('button');
                    trigger.id = 'focusTestTrigger'; trigger.textContent = 'Test';
                    document.body.appendChild(trigger); trigger.focus();
                }""")
                page.evaluate(action)
                modal = page.locator(selector)
                expect(modal).to_be_visible()
                page.wait_for_timeout(80)
                focused_fields = page.evaluate("window.__openingFieldFocus")
                if focused_fields:
                    failures.append(f"{width}/{name}: opening focused {focused_fields}")
                    print(failures[-1], flush=True)
                assert modal.evaluate("el => el.contains(document.activeElement)"), name
                if name == "identity":
                    output = Path(__file__).resolve().parents[1] / "temp/modal-initial-focus"
                    output.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(output / f"{width}-{theme}.png"))
                # Tab enters controls; Shift+Tab from initial focus stays inside.
                initial = page.evaluate_handle("document.activeElement")
                page.keyboard.press("Shift+Tab")
                if not modal.evaluate("el => el.contains(document.activeElement)"):
                    failures.append(f"{width}/{name}: Shift+Tab escaped the modal")
                page.evaluate("el => el.focus()", initial)
                page.keyboard.press("Tab")
                assert modal.evaluate("el => el.contains(document.activeElement)"), name
                page.keyboard.press("Escape")
                expect(modal).not_to_be_visible()
                expect(page.locator("#focusTestTrigger")).to_be_focused()
        context.close()
        browser.close()
    assert not errors, errors
    assert not failures, failures
    print(
        "PASS: 7 modal entry paths at desktop/mobile; no transient field focus; keyboard/return focus preserved"
    )


if __name__ == "__main__":
    main()
