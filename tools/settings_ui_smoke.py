"""Settings UI with a disposable backend; every settings write is intercepted."""

import json
from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    state = {"fail_load": False, "fail_save": True, "saved": {}, "writes": 0, "resets": []}

    def config_get(route):
        if state["fail_load"]:
            route.fulfill(status=503, json={"detail": "Synthetic unavailable"})
            return
        response = route.fetch()
        payload = response.json()
        payload["config"].update(routing_strategy="priority", preferred_provider="codex")
        payload["config"].update(state["saved"])
        route.fulfill(json=payload)

    def config_save(route):
        state["writes"] += 1
        submitted = json.loads(route.request.post_data)["config"]
        assert not {"routing_strategy", "preferred_provider"} & submitted.keys()
        if state["fail_save"]:
            route.fulfill(status=503, json={"detail": "Synthetic save failure"})
        else:
            state["saved"] = submitted
            route.fulfill(json={"success": True})

    def config_reset(route):
        state["resets"].append(route.request.url)
        assert route.request.url.endswith("/api/config/reset?scope=system")
        assert route.request.method == "POST"
        route.fulfill(status=400, json={"detail": "Synthetic reset rejection"})

    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            locale="vi-VN", viewport={"width": 1440, "height": 1000}, reduced_motion="reduce"
        )
        context.route("https://**", lambda route: route.abort())
        context.route("**/api/config/get", config_get)
        context.route("**/api/config/save", config_save)
        context.route(
            "**/api/config/access",
            lambda route: route.fulfill(
                status=400, json={"detail": "Synthetic password rejection"}
            ),
        )
        context.route("**/api/config/reset*", config_reset)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        output = ROOT / "temp/settings-ui"
        output.mkdir(parents=True, exist_ok=True)
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.goto(base + "/config", wait_until="networkidle")
            expect(page.locator("#configForm")).to_be_visible()
            expect(page.locator("#host")).to_be_disabled()
            expect(page.locator("#configForm details")).to_have_count(0)
            expect(page.locator("p#routingStrategy")).not_to_be_empty()
            expect(page.locator("p#preferredProvider")).to_contain_text("Codex")
            expect(page.locator("select#routingStrategy, select#preferredProvider")).to_have_count(
                0
            )
            expect(page.locator('#configForm a[href="/models"]')).to_be_visible()
            routing_summary = page.locator("#routingStrategy").inner_text()
            for name in (
                "currentConsolePassword",
                "newPanelPassword",
                "confirmPanelPassword",
                "codeAssistClientSecret",
            ):
                field = page.locator("#" + name)
                eye = page.locator("#" + name + "Toggle")
                expect(eye).to_be_hidden()
                field.fill("Synthetic-only-value-2026")
                eye.click()
                expect(field).to_have_attribute("type", "text")
                field.fill("")
                expect(eye).to_be_hidden()
                expect(field).to_have_attribute("type", "password")
            page.locator("#upstreamTimeoutSeconds").fill("1")
            page.locator('[data-ui-action="save-config"]').click()
            assert state["writes"] == 0
            page.locator("#upstreamTimeoutSeconds").fill("120")
            page.locator('[data-ui-action="save-config"]').click()
            expect(page.locator("#upstreamTimeoutSeconds")).to_have_value("120")
            expect(page.get_by_text("Synthetic save failure", exact=False)).to_be_visible()
            assert state["writes"] == 1
            state["fail_save"] = False
            with page.expect_response("**/api/config/get") as refreshed:
                page.locator('[data-ui-action="save-config"]').click()
            assert refreshed.value.json()["config"]["upstream_timeout_seconds"] == 120
            expect(page.locator("#configForm")).to_be_visible()
            assert (
                "host" not in state["saved"] and "code_assist_client_secret" not in state["saved"]
            )
            assert not {"routing_strategy", "preferred_provider"} & state["saved"].keys()
            expect(page.locator("#routingStrategy")).to_have_text(routing_summary)
            expect(page.locator("#preferredProvider")).to_contain_text("Codex")
            page.locator('[data-ui-action="reset-config"]').click()
            page.locator("[data-dialog-confirm]").click()
            expect(page.get_by_text("Synthetic reset rejection", exact=False)).to_be_visible()
            assert len(state["resets"]) == 1
            expect(page.locator("#routingStrategy")).to_have_text(routing_summary)
            for name in ("currentConsolePassword", "newPanelPassword", "confirmPanelPassword"):
                page.locator("#" + name).fill("Synthetic-only-value-2026")
            page.locator("#updateAccessCredentialsBtn").click()
            expect(page.locator("#updateAccessCredentialsBtn")).to_be_enabled()
            expect(page.locator("#newPanelPassword")).to_have_value("Synthetic-only-value-2026")
            for name in ("currentConsolePassword", "newPanelPassword", "confirmPanelPassword"):
                page.locator("#" + name).fill("")
            for theme in ("light", "dark"):
                page.locator("#themePreference").select_option(theme)
                for width in (1440, 1024, 768, 360, 320):
                    page.set_viewport_size({"width": width, "height": 1000})
                    page.evaluate("window.scrollTo(0,0)")
                    page.mouse.move(2, 2)
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                        theme,
                        width,
                    )
                    bar = page.locator(".settings-save-bar").bounding_box()
                    assert 0 <= bar["y"] < 1000, (width, bar)
                    if width in (1440, 360):
                        page.screenshot(
                            path=str(output / f"settings-{width}-{theme}.png"),
                            full_page=True,
                            animations="disabled",
                        )
            page.evaluate("AppState.lang = 'en'; applyLanguage()")
            expect(page.locator('[data-ui-action="save-config"]')).to_have_text(
                "Save configuration"
            )
            state["fail_load"] = True
            page.reload(wait_until="networkidle")
            expect(page.locator("#configState")).to_be_visible()
            expect(page.locator("#configForm")).to_be_hidden()
            state["fail_load"] = False
            page.locator("#configState button").click()
            expect(page.locator("#configForm")).to_be_visible()
            assert not errors, errors
            (output / "result.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "page_errors": errors,
                        "save_requests": state["writes"],
                        "routing_read_only": True,
                        "routing_keys_submitted": False,
                        "reset_scope": "system",
                        "reset_requests": len(state["resets"]),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(
                "PASS: 4 secret toggles, validation, failed/successful synthetic saves, environment locks, readonly routing, scoped reset, password draft retention, load/retry, en/vi, 5 widths light/dark"
            )
            print(f"Evidence: {output}")
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
