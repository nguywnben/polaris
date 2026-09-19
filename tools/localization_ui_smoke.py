"""Bounded 15-locale UI matrix on disposable storage; never use real credentials."""

import argparse
from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
LOCALES = (
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
    "vi",
)
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
FIELD_AUDIT = """() => {
    const types = new Set(['text', 'password', 'search', 'email', 'url', 'tel', 'number']);
    return [...document.querySelectorAll('input,textarea')]
        .filter(el => el.tagName === 'TEXTAREA' || types.has(el.type))
        .filter(el => !el.placeholder.trim() || Number(getComputedStyle(el, '::placeholder').fontWeight) !== 400)
        .map(el => el.id || el.name || el.className);
}"""


def select_locale(page, locale):
    page.evaluate("locale => { setLanguage(locale, true); applyLanguage(); }", locale)
    expect(page.locator("html")).to_have_attribute("lang", locale)


def check_layout(page, label):
    for width, theme in ((1440, "light"), (360, "dark")):
        page.set_viewport_size({"width": width, "height": 1000})
        page.emulate_media(color_scheme=theme)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (label, width)
        assert page.evaluate(FIELD_AUDIT) == [], (label, width, page.evaluate(FIELD_AUDIT))


def main(locales=LOCALES):
    with disposable_runtime() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000}, reduced_motion="reduce"
        )
        context.route("https://**", lambda route: route.abort())
        errors = []
        context.on(
            "page", lambda page: page.on("pageerror", lambda error: errors.append(str(error)))
        )
        page = context.new_page()
        output = ROOT / "temp/localization-ui"
        output.mkdir(parents=True, exist_ok=True)
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            for locale in locales:
                select_locale(page, locale)
                check_layout(page, (locale, "setup"))
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            for locale in locales:
                select_locale(page, locale)
                for route in ROUTES:
                    page.goto(f"{base}/{route}", wait_until="networkidle")
                    expect(page.locator("html")).to_have_attribute("lang", locale)
                    check_layout(page, (locale, route))
                    unresolved = page.locator("[data-i18n]").evaluate_all(
                        "els => els.filter(el => el.textContent.trim() === el.dataset.i18n).map(el => el.dataset.i18n)"
                    )
                    assert not unresolved, (locale, route, unresolved)
                    if route == "access":
                        page.locator('[data-ui-action="virtual-key-create"]').first.click()
                        expect(page.locator(".virtual-key-form-modal")).to_be_visible()
                        check_layout(page, (locale, "virtual-key-dialog"))
                        page.locator("[data-virtual-key-cancel]").click()
                    if (locale, route) in (("de", "config"), ("ja", "providers"), ("vi", "config")):
                        page.screenshot(
                            path=str(output / f"{locale}-{route}-mobile.png"),
                            full_page=True,
                            animations="disabled",
                        )
                        page.set_viewport_size({"width": 1440, "height": 1000})
                        page.emulate_media(color_scheme="light")
                        page.screenshot(
                            path=str(output / f"{locale}-{route}-desktop.png"),
                            full_page=True,
                            animations="disabled",
                        )
                    if route == "providers":
                        # Switching away and back must not cache a previous language's placeholder.
                        select_locale(page, "en")
                        select_locale(page, locale)
                        mismatched = page.locator("[data-i18n-placeholder]").evaluate_all(
                            "els => els.filter(el => el.placeholder !== t(el.dataset.i18nPlaceholder)).map(el => el.id)"
                        )
                        assert not mismatched, (locale, "placeholder switching", mismatched)
                        wrong_copy = page.evaluate("""() => {
                            const keys = new Map(Object.entries(PROVIDER_EXACT_COPY).map(([key, pair]) => [pair[0], 'provider.copy.' + key]));
                            const failures = [];
                            for (const workspace of document.querySelectorAll('.provider-workspace')) {
                                const walker = document.createTreeWalker(workspace, NodeFilter.SHOW_TEXT);
                                let node;
                                while ((node = walker.nextNode())) {
                                    const original = AUTO_TRANSLATED_TEXT.get(node);
                                    const key = original && keys.get(original.source);
                                    if (key && node.textContent.trim() !== t(key)) failures.push(key);
                                }
                            }
                            return failures;
                        }""")
                        assert not wrong_copy, (locale, "provider instructions", wrong_copy)
                print(f"PASS: {locale}: 11 console pages and virtual-key dialog", flush=True)
            # A separate signed-out context exercises the real password-only login page.
            guest = browser.new_context(reduced_motion="reduce")
            guest.route("https://**", lambda route: route.abort())
            guest_page = guest.new_page()
            guest_page.on("pageerror", lambda error: errors.append(str(error)))
            guest_page.goto(base + "/login", wait_until="networkidle")
            for locale in locales:
                select_locale(guest_page, locale)
                check_layout(guest_page, (locale, "login"))
                guest.set_extra_http_headers({"Accept-Language": locale})
                response = guest.request.get(base + "/callback")
                assert response.status == 400
                assert f'lang="{locale}"' in response.text(), locale
                assert response.headers.get("cache-control") == "no-store"
            guest.close()
            assert not errors, errors
            print(
                f"PASS: {len(locales)} locales, 14 surfaces, 360/1440px, light/dark, nonblank normal-weight placeholders; no page errors"
            )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--locales", nargs="+", choices=LOCALES, default=LOCALES)
    main(parser.parse_args().locales)
