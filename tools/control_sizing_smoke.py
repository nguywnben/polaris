"""Verify compact 32px controls and the readable 36px-minimum sidebar exception."""

from pathlib import Path

from browser_smoke import disposable_runtime
from playwright.sync_api import expect, sync_playwright
from provider_ownership_smoke import _complete_setup, _install_network_guard

ROOT = Path(__file__).resolve().parents[1]
CONTROL_SELECTOR = """
button:not(.provider-selector-button):not(.upload-area):not(.endpoint-code-card):not(.credential-model-item),
a.btn, input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="file"]):not([type="range"]):not([type="color"]),
select:not([multiple]):not([size])
"""
ROUTES = (
    "dashboard",
    "providers",
    "credentials",
    "models",
    "ai-quality",
    "playground",
    "access",
    "identity",
    "activity",
    "config",
    "about",
)


FAILURES = []


def measure(page, label, width):
    expected = 32
    results = page.locator(
        CONTROL_SELECTOR
    ).evaluate_all("""elements => elements.filter(el => {
        const rect = el.getBoundingClientRect();
        return rect.width && rect.height && getComputedStyle(el).visibility !== 'hidden';
    }).map(el => ({id: el.id, tag: el.tagName, classes: el.className,
        height: el.getBoundingClientRect().height, navigation: el.matches('.sidebar-menu .tab'),
        overflow: el.matches('button, a.btn') && (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1)}))""")
    wrong = [
        item
        for item in results
        if (item["height"] < 35.5 if item["navigation"] else abs(item["height"] - expected) > 1)
        or item["overflow"]
    ]
    if wrong:
        FAILURES.append((label, width, wrong))
    if not page.evaluate("document.documentElement.scrollWidth <= innerWidth"):
        FAILURES.append((label, width, "page overflow"))
    return len(results)


def main():
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors, external = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        _install_network_guard(page, external)
        captures = ROOT / "temp/control-sizing"
        captures.mkdir(parents=True, exist_ok=True)
        try:
            _complete_setup(page, base)
            page.evaluate("navigate('/access', false)")
            reference = page.locator("#virtualKeySearch")
            expect(reference).to_be_visible()
            assert abs(reference.bounding_box()["height"] - 32) < 1
            checked = 0
            for route in ROUTES:
                page.evaluate("route => navigate('/' + route, false)", route)
                expect(page.locator(".tab-content.active")).to_be_visible()
                for width in (320, 768, 1024, 1440):
                    page.set_viewport_size({"width": width, "height": 1000})
                    for theme in ("light", "dark"):
                        page.evaluate("theme => PolarisTheme.setPreference(theme)", theme)
                        page.evaluate(
                            "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
                        )
                        checked += measure(page, route + "/" + theme, width)
                        if route in ("dashboard", "access", "config") and width in (320, 1440):
                            page.screenshot(path=str(captures / f"{route}-{theme}-{width}.png"))
            # Every provider form, including advanced controls, uses the same scale.
            page.evaluate("navigate('/providers', false)")
            providers = page.evaluate("Object.keys(PROVIDER_WORKSPACES)")
            for provider in providers:
                page.evaluate("provider => selectProviderWorkspace(provider)", provider)
                page.locator(".provider-workspace:not(.hidden) details").evaluate_all(
                    "els => els.forEach(el => el.open = true)"
                )
                for width in (360, 1440):
                    page.set_viewport_size({"width": width, "height": 1000})
                    checked += measure(page, provider, width)
            # A normal dialog and long translated controls retain readable text.
            page.evaluate(
                "showMessageModal(t('credentials.manage'), t('modal.models_intro'), 'info')"
            )
            expect(page.locator('[role="dialog"]')).to_be_visible()
            checked += measure(page, "dialog", 1440)
            page.keyboard.press("Escape")
            for locale in page.evaluate("Object.keys(CREDENTIAL_MANAGEMENT_COPY)"):
                page.evaluate("locale => {setLanguage(locale, false); applyLanguage();}", locale)
                for route in ("access", "config", "identity"):
                    page.evaluate("route => navigate('/' + route, false)", route)
                    page.set_viewport_size({"width": 320, "height": 1000})
                    checked += measure(page, route + "/" + locale, 320)
            assert not errors, errors
            assert not external, external
            assert not FAILURES, FAILURES
            print(
                f"PASS: {checked} control measurements, eleven pages, {len(providers)} providers, four widths, themes and 15 locales"
            )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
