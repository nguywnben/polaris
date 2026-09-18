"""Verify header sizing and Identity refresh feedback in a disposable runtime."""

from pathlib import Path

from browser_smoke import disposable_runtime
from playwright.sync_api import expect, sync_playwright
from provider_ownership_smoke import _complete_setup, _install_network_guard

HEADER_BUTTONS = (
    ".tab-content.active :is(.page-header, .activity-view-header, .virtual-key-header) "
    ".page-actions .btn:visible"
)
ROUTES = {
    "credentials": "credentialsTab",
    "models": "modelsTab",
    "ai-quality": "qualityTab",
    "access": "accessTab",
    "identity": "identityTab",
    "activity": "activityTab",
    "about": "aboutTab",
}


def measure_header_buttons(page):
    # Read one DOM snapshot: loading actions can disappear after navigation.
    return page.locator(HEADER_BUTTONS).evaluate_all("""buttons => buttons.map(button => ({
        height: button.getBoundingClientRect().height,
        text: button.textContent,
        fits: button.scrollWidth <= button.clientWidth + 1
    }))""")


def main():
    output = Path(__file__).resolve().parents[1] / "temp/header-actions"
    output.mkdir(parents=True, exist_ok=True)
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors, external = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        _install_network_guard(page, external)
        try:
            _complete_setup(page, base)
            checked = 0
            for route, tab in ROUTES.items():
                page.evaluate("route => navigate('/' + route, false)", route)
                expect(page.locator(f"#{tab}")).to_be_visible()
                # Audit every visible top-right action, including all Activity views.
                views = ("traces", "audit", "runtime") if route == "activity" else (None,)
                for view in views:
                    if view:
                        page.locator(f'[data-activity-view="{view}"]').click()
                    for theme in ("light", "dark"):
                        page.evaluate(
                            "theme => document.documentElement.dataset.theme = theme", theme
                        )
                        for width in (320, 768, 1024, 1440):
                            page.set_viewport_size({"width": width, "height": 1000})
                            page.evaluate(
                                "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
                            )
                            buttons = measure_header_buttons(page)
                            assert buttons, f"No header actions: {route}/{view}"
                            for button in buttons:
                                height = button["height"]
                                expected = 32
                                assert abs(height - expected) < 1, (
                                    route,
                                    view,
                                    theme,
                                    width,
                                    button["text"],
                                    height,
                                )
                                assert button["fits"]
                                checked += 1
                            assert page.evaluate(
                                "document.documentElement.scrollWidth <= innerWidth"
                            ), (route, view, theme, width, "overflow")
                            if route == "identity" and width in (320, 1440):
                                page.screenshot(path=str(output / f"identity-{theme}-{width}.png"))

                    # Long translations must stay on one line without clipping on phones.
                    page.set_viewport_size({"width": 320, "height": 1000})
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
                        "pt-BR",
                        "ru",
                        "th",
                        "tr",
                        "vi",
                    ):
                        page.evaluate(
                            "locale => { setLanguage(locale, false); applyLanguage(); }", locale
                        )
                        buttons = measure_header_buttons(page)
                        assert buttons, (route, locale)
                        for button in buttons:
                            assert abs(button["height"] - 32) < 1, (route, locale)
                            assert button["fits"], (
                                route,
                                locale,
                            )
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth"
                        ), (route, locale)

            page.evaluate("navigate('/identity', false)")
            refresh = page.locator("#identityRefreshButton")
            expect(refresh).to_be_enabled()
            expect(refresh).to_have_text("Làm mới")
            expect(page.locator("#identityPageStatus")).to_be_empty()
            refresh.click()
            expect(page.locator("#statusSection .success")).to_contain_text("Đã làm mới")
            expect(page.locator("#identityPageStatus")).to_be_empty()
            expect(refresh).to_be_enabled()
            assert not page.evaluate("document.activeElement.matches('input, textarea, select')"), (
                "Toast moved focus to a field"
            )
            page.route(
                "**/api/identity/sessions?*", lambda route: route.fulfill(status=503, json={})
            )
            refresh.click()
            expect(page.locator("#statusSection .error")).to_be_visible()
            expect(page.locator("#identitySessionStatus")).not_to_be_empty()
            expect(page.locator("#identityPageStatus")).to_be_empty()
            expect(refresh).to_be_enabled()
            page.route("**/api/identity/session", lambda route: route.fulfill(status=503, json={}))
            refresh.click()
            expect(page.locator("#statusSection .error")).to_be_visible()
            expect(refresh).to_be_enabled()
            expect(page.locator("#identityPageStatus")).to_be_empty()
            assert not errors, errors
            assert not external, external
            print(
                f"PASS: {checked} header measurements; seven pages, all Activity views, "
                "four widths, light/dark, 15 locale labels, refresh success/failure and unchanged field focus"
            )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
