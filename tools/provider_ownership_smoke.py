"""Smoke provider/settings ownership in an isolated Chromium and runtime.

The test uses the disposable localhost runtime from ``browser_smoke.py``. It
blocks every non-local browser request, never starts an OAuth/provider action,
and stores screenshots only as local review evidence.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from urllib.parse import urlparse

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import Page, Route, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WIDTHS = (360, 768, 1024, 1440)
THEMES = ("light", "dark")
PROVIDERS = (
    ("google_antigravity", "providerSelectorGoogleAntigravity", "providerWorkspaceGoogleAntigravity"),
    ("google_ai_studio", "providerSelectorGoogleAiStudio", "providerWorkspaceGoogleAiStudio"),
    ("grok", "providerSelectorGrok", "providerWorkspaceGrok"),
    ("xai_console", "providerSelectorXaiConsole", "providerWorkspaceXaiConsole"),
    ("codex", "providerSelectorCodex", "providerWorkspaceCodex"),
    ("openai_platform", "providerSelectorOpenAiPlatform", "providerWorkspaceOpenAiPlatform"),
    ("claude_code", "providerSelectorClaudeCode", "providerWorkspaceClaudeCode"),
    ("claude_platform", "providerSelectorClaudePlatform", "providerWorkspaceClaudePlatform"),
    ("ollama", "providerSelectorOllama", "providerWorkspaceOllama"),
)


def _install_network_guard(page: Page, unexpected_external: list[str]) -> None:
    def guard(route: Route) -> None:
        parsed = urlparse(route.request.url)
        if parsed.hostname in {"127.0.0.1", "localhost"}:
            route.fallback()
            return
        if parsed.hostname == "fonts.googleapis.com":
            route.fulfill(status=200, content_type="text/css", body="")
            return
        if parsed.hostname == "fonts.gstatic.com":
            route.fulfill(status=200, content_type="font/woff2", body="")
            return
        unexpected_external.append(route.request.url)
        route.abort("blockedbyclient")

    page.route("**/*", guard)


def _complete_setup(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")
    expect(page.locator("#setupSection")).to_be_visible(timeout=15_000)
    expect(page.locator("#setupOwnerFields")).to_be_enabled(timeout=10_000)
    page.locator("#setupPassword").fill(PASSWORD)
    page.locator("#setupPasswordConfirm").fill(PASSWORD)
    page.locator("#setupSubmitButton").click()
    expect(page.locator("#dashboardTab")).to_be_visible(timeout=15_000)
    expect(page.locator("#statusSection")).to_be_hidden(timeout=10_000)


def _assert_no_overflow(page: Page, surface: str, width: int, theme: str) -> None:
    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    if overflow > 1:
        raise AssertionError(
            f"{surface} overflows horizontally by {overflow}px at {width}px ({theme})."
        )
    protruding = page.locator(".tab-content.active").evaluate(
        """surface => [...surface.querySelectorAll('*')].filter(element => {
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            if (!rect.width || !rect.height || style.visibility === 'hidden') return false;
            if (style.position === 'fixed' || style.position === 'absolute') return false;
            return rect.left < -1 || rect.right > innerWidth + 1;
        }).slice(0, 12).map(element => ({
            tag: element.tagName.toLowerCase(), id: element.id,
            className: String(element.className).slice(0, 100),
            left: Math.round(element.getBoundingClientRect().left),
            right: Math.round(element.getBoundingClientRect().right)
        }))"""
    )
    if protruding:
        raise AssertionError(
            f"{surface} has visible elements outside the viewport at {width}px ({theme}): "
            f"{protruding!r}"
        )


def _assert_surface_hygiene(page: Page, surface: str, width: int, theme: str) -> None:
    autofocus = page.locator(".tab-content.active [autofocus]").count()
    if autofocus:
        raise AssertionError(f"{surface} contains {autofocus} autofocus control(s).")
    invalid_events = page.evaluate("window.__providerOwnershipInvalidEvents")
    if invalid_events:
        raise AssertionError(
            f"{surface} triggered browser-native validation at {width}px ({theme}): "
            f"{invalid_events!r}"
        )
    _assert_no_overflow(page, surface, width, theme)


def _open_providers(page: Page) -> None:
    page.evaluate("navigate('/providers', false)")
    expect(page.locator("#providersTab")).to_be_visible()


def _select_all_providers(page: Page) -> None:
    credit_owner = page.locator("#antigravityCreditSettings").evaluate(
        "section => section.closest('.provider-workspace')?.id || null"
    )
    if credit_owner != "providerWorkspaceGoogleAntigravity":
        raise AssertionError(
            "Antigravity credit controls belong inside the Antigravity workspace; "
            f"actual owner: {credit_owner!r}."
        )
    for _provider_id, selector_id, workspace_id in PROVIDERS:
        selector = page.locator(f"#{selector_id}")
        if not selector.is_visible():
            if selector_id == "providerSelectorOllama":
                page.locator("#providerCatalogNextBtn").click()
            else:
                page.locator("#providerCatalogPrevBtn").click()
        expect(selector).to_be_visible()
        selector.click()
        expect(selector).to_have_attribute("aria-selected", "true")
        expect(page.locator(f"#{workspace_id}")).to_be_visible()

    page.locator("#providerCatalogPrevBtn").click()
    page.locator("#providerSelectorGoogleAntigravity").click()
    expect(page.locator("#providerWorkspaceGoogleAntigravity")).to_be_visible()


def _open_google_settings(page: Page) -> None:
    shared = page.locator('[data-google-settings="shared"]')
    compatibility = page.locator('[data-google-settings="compatibility"]')
    if not shared.evaluate("details => details.open"):
        shared.locator("summary").click()
    if not compatibility.evaluate("details => details.open"):
        compatibility.locator("summary").click()
    expect(shared).to_have_attribute("open", "")
    expect(compatibility).to_have_attribute("open", "")
    expect(page.locator("#googleSharedSettingsForm")).to_be_visible()
    expect(page.locator("#googleCompatibilitySettingsForm")).to_be_visible()
    expect(page.locator("#googleSharedSettingsForm")).to_have_attribute("novalidate", "")
    expect(page.locator("#googleCompatibilitySettingsForm")).to_have_attribute("novalidate", "")
    page.wait_for_function(
        """() => [...document.querySelectorAll('[data-google-scope]')]
            .every(form => !form.inert && !form.hasAttribute('aria-busy'))""",
        timeout=10_000,
    )


def _verify_settings_ownership(page: Page) -> None:
    page.evaluate("navigate('/config', false)")
    settings = page.locator("#configTab")
    expect(settings).to_be_visible()
    expect(settings.locator("#switchCredentialEnabled")).to_be_visible()
    expect(settings.locator("#streamToNonstream")).to_be_visible()
    if settings.locator(
        "#codeAssistEndpoint, #codeAssistClientId, #codeAssistClientSecret, "
        "[data-google-config], [data-google-settings]"
    ).count():
        raise AssertionError("Settings still owns Google/Code Assist controls.")
    if "Code Assist" in settings.inner_text():
        raise AssertionError("Settings still renders Code Assist copy.")
    save_bar = settings.locator(".settings-save-bar")
    save_bar_layout = save_bar.evaluate(
        """bar => {
            const barRect = bar.getBoundingClientRect();
            const overlaps = [...document.querySelectorAll('#configTab .config-group')]
                .filter(group => {
                    const rect = group.getBoundingClientRect();
                    return rect.bottom > barRect.top && rect.top < barRect.bottom
                        && rect.right > barRect.left && rect.left < barRect.right;
                })
                .map(group => group.querySelector('h2')?.textContent?.trim() || group.className);
            return {position: getComputedStyle(bar).position, overlaps};
        }"""
    )
    if save_bar_layout["position"] in {"absolute", "fixed", "sticky"}:
        raise AssertionError(f"Settings save bar is overlay-positioned: {save_bar_layout!r}")
    if save_bar_layout["overlaps"]:
        raise AssertionError(f"Settings save bar overlaps content: {save_bar_layout!r}")


def _capture_matrix(page: Page, output_dir: Path) -> None:
    for theme in THEMES:
        page.evaluate("theme => window.PolarisTheme.setPreference(theme)", theme)
        expect(page.locator("html")).to_have_attribute("data-theme", theme)
        for width in WIDTHS:
            page.set_viewport_size({"width": width, "height": 1000})
            _open_providers(page)
            _select_all_providers(page)
            _open_google_settings(page)
            _assert_surface_hygiene(page, "Providers", width, theme)
            page.screenshot(
                path=output_dir / f"providers-{theme}-{width}.png",
                full_page=True,
            )

            _verify_settings_ownership(page)
            _assert_surface_hygiene(page, "Settings", width, theme)
            page.screenshot(
                path=output_dir / f"settings-{theme}-{width}.png",
                full_page=True,
            )
            print(
                f"[provider-ownership-smoke] passed: {theme} {width}px",
                flush=True,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "temp" / "provider-ownership-smoke",
        help="Directory for the 16 local review screenshots.",
    )
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    console_errors: list[str] = []
    unexpected_external: list[str] = []
    try:
        with disposable_runtime() as base_url, sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                reduced_motion="reduce",
            )
            page = context.new_page()
            page.add_init_script(
                """window.__providerOwnershipInvalidEvents = [];
                document.addEventListener('invalid', event => {
                    window.__providerOwnershipInvalidEvents.push(
                        event.target.id || event.target.name || event.target.tagName
                    );
                }, true);"""
            )
            page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.on("pageerror", lambda error: console_errors.append(str(error)))
            _install_network_guard(page, unexpected_external)
            _complete_setup(page, base_url)
            _capture_matrix(page, output_dir)
            context.close()
            browser.close()

        if console_errors:
            raise AssertionError("Browser errors:\n- " + "\n- ".join(console_errors))
        if unexpected_external:
            raise AssertionError(
                "Unexpected external browser requests were blocked:\n- "
                + "\n- ".join(sorted(set(unexpected_external)))
            )
    except Exception as exc:
        print(f"Provider ownership smoke failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    print(f"Provider ownership smoke passed. Screenshots: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
