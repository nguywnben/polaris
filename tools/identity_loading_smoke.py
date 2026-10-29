"""Bounded identity loading/refresh regression in a disposable local Chromium runtime."""

import json
import time
from pathlib import Path
from urllib.parse import urlsplit

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright

FACT_ROWS = {
    "identityPrincipalSummary": 6,
    "identityOidcSummary": 8,
    "identityRecoverySummary": 3,
}
REGIONS = [*FACT_ROWS, "identityList", "identitySessionList"]


class RequestGate:
    """Hold real local responses until each observable loading stage is measured."""

    def __init__(self, page):
        self.page = page
        self.pending = {}
        self.hold = True
        self.session_status = 200

    def route(self, route):
        path = urlsplit(route.request.url).path.rsplit("/", 1)[-1]
        if self.hold:
            self.pending.setdefault(path, []).append(route)
        else:
            self.respond(route)

    def respond(self, route):
        path = urlsplit(route.request.url).path.rsplit("/", 1)[-1]
        if path == "sessions" and self.session_status != 200:
            route.fulfill(status=self.session_status, json={"detail": "Synthetic failure"})
        else:
            route.continue_()

    def release(self, path):
        deadline = time.monotonic() + 5
        while path not in self.pending and time.monotonic() < deadline:
            self.page.wait_for_timeout(20)
        assert path in self.pending, f"Expected held identity request: {path}"
        for route in self.pending.pop(path):
            self.respond(route)

    def release_remaining(self):
        self.hold = False
        for routes in list(self.pending.values()):
            for route in routes:
                self.respond(route)
        self.pending.clear()


def geometry(page):
    return page.locator("#identityTab").evaluate(
        """root => Object.fromEntries([
            'identityPrincipalSummary', 'identityOidcSummary', 'identityRecoverySummary',
            'identityInventoryHeading'
        ].map(id => {
            const node = root.querySelector('#' + id);
            const rect = node.getBoundingClientRect();
            return [id, {
                top: rect.top + window.scrollY, height: rect.height,
                rows: Array.from(node.children).filter(child => child.matches('div')).map(row => ({
                    top: row.getBoundingClientRect().top + window.scrollY,
                    facts: row.querySelectorAll('dt').length === 1
                        && row.querySelectorAll('dd').length === 1
                }))
            }];
        }))"""
    )


def main():
    output = Path(__file__).resolve().parents[1] / "temp/identity-loading"
    output.mkdir(parents=True, exist_ok=True)
    failures = []
    measurements = {}

    def check(condition, message):
        if not condition:
            failures.append(message)

    with disposable_runtime() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        # All runtime/provider state is disposable; no external font or provider requests.
        context.route("https://**", lambda route: route.abort())
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        gate = RequestGate(page)
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.wait_for_load_state("networkidle")
            context.route("**/api/identity/**", gate.route)

            for width in [1440, 360]:
                page.set_viewport_size({"width": width, "height": 1000})
                gate.hold = True
                gate.session_status = 200
                page.goto(base + "/identity", wait_until="domcontentloaded")
                expect(page.locator("#identityRefreshButton")).to_be_disabled()
                expect(page.locator("#identityPrincipalSummary")).to_have_attribute(
                    "aria-busy", "true"
                )
                # Wait for the held request, so measurements cannot race page initialization.
                deadline = time.monotonic() + 5
                while "session" not in gate.pending and time.monotonic() < deadline:
                    page.wait_for_timeout(20)
                assert "session" in gate.pending
                loading = geometry(page)
                for region, count in FACT_ROWS.items():
                    rows = loading[region]["rows"]
                    check(
                        len(rows) == count and all(row["facts"] for row in rows),
                        f"{width}: {region} loading needs {count} label/value fact rows; got {rows}",
                    )
                check(
                    page.locator("html").evaluate("el => el.scrollWidth <= window.innerWidth"),
                    f"{width}: horizontal overflow while loading",
                )
                page.screenshot(path=str(output / f"loading-{width}.png"), full_page=True)

                gate.release("session")
                expect(page.locator("#identityPrincipalSummary")).to_have_attribute(
                    "aria-busy", "false"
                )
                principal_only = geometry(page)
                gate.release("oidc-policy")
                expect(page.locator("#identityOidcSummary")).to_have_attribute("aria-busy", "false")
                oidc_loaded = geometry(page)
                gate.release("recovery")
                gate.release("identities")
                gate.release("sessions")
                expect(page.locator("#identityRefreshButton")).to_be_enabled()
                gate.hold = False
                loaded = geometry(page)
                measurements[str(width)] = {
                    "loading": loading,
                    "principal_only": principal_only,
                    "oidc_loaded": oidc_loaded,
                    "loaded": loaded,
                }
                if width == 1440:
                    # Stable fact geometry matters; variable identity/session list heights do not.
                    for stage_name, stage in [
                        ("principal_only", principal_only),
                        ("oidc_loaded", oidc_loaded),
                        ("loaded", loaded),
                    ]:
                        for region in loading:
                            delta = abs(stage[region]["top"] - loading[region]["top"])
                            check(delta <= 8, f"{region} moved {delta:.1f}px at {stage_name}")
                    for region in ["identityPrincipalSummary", "identityOidcSummary"]:
                        delta = abs(loaded[region]["height"] - loading[region]["height"])
                        check(delta <= 8, f"{region} height changed {delta:.1f}px")
                for region in REGIONS:
                    expect(page.locator("#" + region)).to_have_attribute("aria-busy", "false")
                expect(
                    page.locator("#identitySessionList article[data-session-reference]")
                ).to_have_count(1)
                page.screenshot(path=str(output / f"loaded-{width}.png"), full_page=True)

                # Open native disclosure with the keyboard and preserve the user's choice.
                disclosure = page.locator(".identity-permissions")
                summary = disclosure.locator("summary")
                summary.focus()
                summary.press("Enter")
                expect(disclosure).to_have_attribute("open", "")
                gate.hold = True
                refresh = page.locator("#identityRefreshButton")
                refresh.focus()
                refresh.press("Enter")
                expect(refresh).to_be_disabled()
                check(
                    disclosure.evaluate("el => el.open"), f"{width}: refresh collapsed permissions"
                )
                gate.release("session")
                gate.release_remaining()
                expect(refresh).to_be_enabled()
                check(
                    disclosure.evaluate("el => el.open"),
                    f"{width}: successful refresh collapsed permissions",
                )
                # Native keyboard activation must still close/reopen the refreshed disclosure.
                if disclosure.evaluate("el => el.open"):
                    summary.focus()
                    summary.press("Space")
                    expect(disclosure).not_to_have_attribute("open", "")
                    summary.press("Enter")
                    expect(disclosure).to_have_attribute("open", "")

                sessions = page.locator("#identitySessionList")
                previous_content = sessions.inner_text()
                previous_reference = sessions.locator(
                    "article[data-session-reference]"
                ).first.get_attribute("data-session-reference")
                gate.session_status = 503
                refresh.click()
                expect(page.locator("#identitySessionStatus")).not_to_be_empty()
                expect(refresh).to_be_enabled()
                expect(sessions).to_have_attribute("aria-busy", "false")
                check(
                    sessions.inner_text() == previous_content,
                    f"{width}: transient 503 discarded last successful session content",
                )
                check(
                    sessions.locator("article[data-session-reference]").count() == 1,
                    f"{width}: transient 503 removed the existing session row",
                )
                expect(page.locator("#identitySessionStatus")).to_have_attribute("role", "status")
                page.screenshot(path=str(output / f"transient-error-{width}.png"), full_page=True)

                # Restore success before testing authorization loss, so stale data really exists.
                gate.session_status = 200
                refresh.click()
                expect(sessions.locator("article[data-session-reference]")).to_have_count(1)
                expect(refresh).to_be_enabled()
                gate.session_status = 403
                refresh.click()
                expect(page.locator("#identitySessionStatus")).not_to_be_empty()
                expect(refresh).to_be_enabled()
                expect(sessions).to_have_attribute("aria-busy", "false")
                check(
                    sessions.locator("article[data-session-reference]").count() == 0
                    and previous_reference not in sessions.inner_text(),
                    f"{width}: 403 retained protected session content",
                )
                check(
                    page.locator("html").evaluate("el => el.scrollWidth <= window.innerWidth"),
                    f"{width}: horizontal overflow after refresh",
                )

            gate.session_status = 200
            page.locator("#identityRefreshButton").click()
            expect(
                page.locator("#identitySessionList article[data-session-reference]")
            ).to_have_count(1)
            expect(page.locator("#identityRefreshButton")).to_be_enabled()
            gate.session_status = 401
            gate.hold = True
            page.locator("#identityRefreshButton").click()
            gate.release("session")
            expect(page.locator("#identityPrincipalSummary")).to_have_attribute(
                "aria-busy", "false"
            )
            for endpoint, region in [
                ("identities", "identityList"),
                ("oidc-policy", "identityOidcSummary"),
                ("recovery", "identityRecoverySummary"),
            ]:
                gate.release(endpoint)
                expect(page.locator("#" + region)).to_have_attribute("aria-busy", "false")
            gate.release("sessions")
            gate.hold = False
            expect(page).to_have_url(base + "/login")
            expect(page.locator("#loginForm")).to_be_visible()
            check(
                page.locator("#identitySessionList article[data-session-reference]").count() == 0,
                "401 retained protected session content after sign-out",
            )
            check(not errors, f"Unexpected browser exceptions: {errors}")
            print(json.dumps(measurements, indent=2))
            assert not failures, "\n".join(failures)
            print(
                "PASS: staged facts, desktop geometry, mobile, keyboard, refresh, 503, 403 and 401"
            )
        finally:
            gate.release_remaining()
            # Sign-out aborts sibling requests; do not wait indefinitely on their route handlers.
            context.unroute_all(behavior="ignoreErrors")
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
