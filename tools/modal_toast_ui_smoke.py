"""Toast layering and non-intrusive validation on a disposable Chromium runtime."""

from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    failures = []
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(reduced_motion="reduce")
        context.route("https://**", lambda route: route.abort())
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.goto(base + "/identity", wait_until="networkidle")
            duplicate_close = page.locator('#identityCreateDialog .icon-button').count()
            if duplicate_close:
                failures.append("Create Identity has both Cancel and an X button")
            for width, theme in ((1440, "light"), (360, "dark")):
                page.set_viewport_size({"width": width, "height": 900})
                page.emulate_media(color_scheme=theme)
                # Exercise every shipped native modal, including toast-before-modal ordering.
                for dialog_id in ("identityCreateDialog", "identityConfirmDialog", "auditDetailDialog", "traceDetailDialog"):
                    route = "/activity?view=audit" if dialog_id == "auditDetailDialog" else "/activity" if dialog_id == "traceDetailDialog" else "/identity"
                    page.goto(base + route, wait_until="networkidle")
                    page.evaluate("showStatus('Synthetic notification', 'info')")
                    page.evaluate("id => document.getElementById(id).showModal()", dialog_id)
                    page.wait_for_timeout(40)
                    expect(page.locator(f"#{dialog_id}")).to_be_visible()
                    if not page.evaluate("document.getElementById('statusSection').matches(':popover-open')"):
                        failures.append(f"{width}/{dialog_id}: opening a modal covered the existing toast")
                    page.evaluate("""id => {
                        const button = document.getElementById(id).querySelector('button');
                        button.focus(); window.__toastFocus = document.activeElement;
                        showStatus('Synthetic error notification', 'error');
                    }""", dialog_id)
                    expect(page.locator("#statusSection .error")).to_be_visible()
                    if not page.evaluate("document.getElementById('statusSection').matches(':popover-open')"):
                        failures.append(f"{width}/{dialog_id}: toast is not in the top layer")
                    if not page.evaluate("document.activeElement === window.__toastFocus"):
                        failures.append(f"{width}/{dialog_id}: toast moved focus")
                    if not page.evaluate("id => document.getElementById(id).contains(document.getElementById('statusSection'))", dialog_id):
                        failures.append(f"{width}/{dialog_id}: live region is outside the active modal")
                    if dialog_id == "identityCreateDialog":
                        output = ROOT / "temp/modal-toast-ui"
                        output.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(output / f"{width}-{theme}.png"))
                    page.evaluate("id => document.getElementById(id).close()", dialog_id)
                # Shared validation covers static and dynamically mounted form controls.
                page.evaluate("""() => {
                    const modal = document.createElement('div'); modal.id = 'toastTestModal';
                    modal.className = 'message-modal-overlay';
                    modal.innerHTML = '<div class="message-modal" role="dialog" aria-modal="true" aria-label="Test"><button id="toastTestAction">Test</button><input id="toastTestInput" required placeholder="Test"><textarea id="toastTestTextarea" required placeholder="Test"></textarea><select id="toastTestSelect" required><option value="">Choose</option><option value="one">One</option></select></div>';
                    void mountModal(modal);
                }""")
                for field_id in ("toastTestInput", "toastTestTextarea", "toastTestSelect"):
                    page.locator("#toastTestAction").click()
                    page.evaluate("id => document.getElementById(id).reportValidity()", field_id)
                    page.wait_for_timeout(40)
                    if not page.locator("#toastTestAction").evaluate("el => document.activeElement === el"):
                        failures.append(f"{width}/{field_id}: validation toast focused the field")
                    expect(page.locator(f"#{field_id}")).to_have_attribute("aria-invalid", "true")
                    page.locator(f"#{field_id}").focus()
                    page.evaluate("showStatus('Synthetic success', 'success')")
                    expect(page.locator(f"#{field_id}")).to_be_focused()
                page.locator("#toastTestAction").click()
                page.keyboard.press("Tab")
                expect(page.locator("#toastTestInput")).to_be_focused()
                page.evaluate("void unmountModal(document.getElementById('toastTestModal'))")
            # A missing toast host must not fall back to a focus-stealing message modal.
            page.evaluate("document.getElementById('statusSection').remove(); showStatus('Synthetic notice', 'success')")
            if page.locator(".message-modal-overlay").count():
                failures.append("Missing host created a message modal instead of a toast")
            expect(page.locator("#statusSection .success")).to_be_visible()
            expect(page.locator("#statusSection .status")).to_have_count(0, timeout=6500)
            assert not page.evaluate("document.getElementById('statusSection').matches(':popover-open')")
            assert not errors, errors
            assert not failures, failures
            print("PASS: all native modals, custom modal, 3 control types, both themes/widths; toast preserves focus")
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
