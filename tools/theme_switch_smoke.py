"""Check atomic theme changes without disabling normal interaction transitions."""

import argparse
import subprocess
from pathlib import Path

from browser_smoke import disposable_runtime
from playwright.sync_api import expect, sync_playwright
from provider_ownership_smoke import _complete_setup, _install_network_guard

SNAPSHOT = """() => [...document.querySelectorAll('body, .tab-content.active *')]
    .filter(el => el.getBoundingClientRect().width && el.getBoundingClientRect().height)
    .map(el => {
        const css = getComputedStyle(el);
        return [el.tagName, el.id, css.backgroundColor, css.color, css.borderTopColor,
            css.boxShadow, getComputedStyle(el, '::before').backgroundColor,
            getComputedStyle(el, '::after').backgroundColor];
    })"""
SWITCH = """async theme => {
    PolarisTheme.setPreference(theme);
    await new Promise(requestAnimationFrame);
    const pending = document.getAnimations().filter(animation =>
        animation instanceof CSSTransition &&
        /color|background|border|shadow|filter/i.test(animation.transitionProperty));
    return pending.map(animation => ({
        target: animation.effect.target.id || animation.effect.target.tagName,
        property: animation.transitionProperty
    }));
}"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline-ref", help="Replay a committed theme script to reproduce regressions"
    )
    args = parser.parse_args()
    baseline = None
    if args.baseline_ref:
        baseline = subprocess.check_output(
            ["git", "show", f"{args.baseline_ref}:frontend/js/core/theme.js"],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
        )
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors, external = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        _install_network_guard(page, external)
        if baseline is not None:
            page.route(
                "**/frontend/theme.js?*",
                lambda route: route.fulfill(content_type="application/javascript", body=baseline),
            )
        try:
            _complete_setup(page, base)
            for route in (
                "config",
                "ai-quality",
                "providers",
                "access",
                "playground",
                "dashboard",
                "credentials",
                "models",
                "identity",
                "activity",
                "about",
            ):
                page.goto(base + "/" + route, wait_until="networkidle")
                for width in (320, 768, 1024, 1440):
                    page.set_viewport_size({"width": width, "height": 1000})
                    for theme in ("dark", "light"):
                        pending = page.evaluate(SWITCH, theme)
                        assert not pending, (route, width, theme, pending)
                        first_frame = page.evaluate(SNAPSHOT)
                        # The old implementation takes 140-150ms to settle.
                        page.wait_for_timeout(180)
                        settled = page.evaluate(SNAPSHOT)
                        assert first_frame == settled, (
                            route,
                            width,
                            theme,
                            "late color change",
                            [
                                (before, after)
                                for before, after in zip(first_frame, settled)
                                if before != after
                            ][:5],
                            len(first_frame),
                            len(settled),
                        )
                        assert not page.evaluate(
                            "document.documentElement.classList.contains('theme-switching')"
                        )

            page.evaluate("navigate('/config', false)")
            expect(page.locator("#themePreference")).to_be_visible()
            page.locator("#themePreference").select_option("dark")
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            page.reload(wait_until="networkidle")
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            page.locator("#themePreference").select_option("system")
            for theme in ("dark", "light"):
                page.emulate_media(color_scheme=theme)
                expect(page.locator("html")).to_have_attribute("data-theme", theme)
            page.emulate_media(reduced_motion="reduce")
            assert not page.evaluate(SWITCH, "dark")
            page.evaluate("['light', 'dark', 'light', 'dark'].forEach(PolarisTheme.setPreference)")
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            page.wait_for_function(
                "!document.documentElement.classList.contains('theme-switching')"
            )
            page.emulate_media(reduced_motion="no-preference")
            duration = page.locator("#themePreference").evaluate(
                "el => getComputedStyle(el).transitionDuration"
            )
            assert "0.14s" in duration, "normal control transitions were permanently disabled"
            assert not errors, errors
            assert not external, external
            print(
                "PASS: 11 pages, four widths, both theme directions, frame-stable colors, "
                "persistence, system theme, reduced motion, rapid toggling and restored transitions"
            )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
