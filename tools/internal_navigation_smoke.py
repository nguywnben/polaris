"""Prove internal links and route handoffs keep one console document alive.

Uses a fresh loopback runtime and synthetic model data, never operator credentials
or an external provider. Document requests, URL state and visible panels are
checked independently so a correct destination cannot hide a full-page reload.
"""

from urllib.parse import urlsplit

from browser_smoke import PASSWORD, _model_catalog, disposable_runtime
from playwright.sync_api import expect, sync_playwright


def main():
    state = {"configured": False}
    failures = []

    def catalog(route):
        data = _model_catalog(state["configured"])
        if not state["configured"]:
            data["catalog"] = []
            data["provider_catalogs"] = []
        route.fulfill(json=data)

    with disposable_runtime() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(locale="en-US", viewport={"width": 1440, "height": 1000})
        # Only the disposable app origin is reachable, including plain HTTP URLs.
        context.route(
            "**/*",
            lambda route: (
                route.continue_() if route.request.url.startswith(base + "/") else route.abort()
            ),
        )
        context.route("**/api/model-catalog**", catalog)
        context.route(
            "**/api/model-routes/polaris/validate",
            lambda route: route.fulfill(
                json={
                    "validation": {"valid": True, "status": "ready", "issues": []},
                }
            ),
        )
        page = context.new_page()
        errors = []
        documents = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request",
            lambda request: (
                documents.append(request.url) if request.resource_type == "document" else None
            ),
        )

        def check_navigation(name, action, destination, panel):
            before = len(documents)
            action()
            expect(page).to_have_url(base + destination)
            expect(page.locator(panel)).to_be_visible()
            if len(documents) != before:
                failures.append(f"{name}: reloaded document {documents[before:]}")
            print(f"CHECK: {name}; document requests = {len(documents) - before}", flush=True)

        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")

            check_navigation(
                "sidebar to settings",
                lambda: page.locator('.tab[data-tab="config"]').click(),
                "/config",
                "#configTab",
            )
            check_navigation(
                "settings internal routing link",
                lambda: page.locator('#configTab a[href="/models"]').click(),
                "/models",
                "#modelsTab",
            )
            check_navigation(
                "back to settings for keyboard link", page.go_back, "/config", "#configTab"
            )
            settings_link = page.locator('#configTab a[href="/models"]')
            expect(settings_link).to_have_attribute("href", "/models")
            expect(settings_link).not_to_have_attribute("role", "button")
            settings_link.focus()
            check_navigation(
                "Enter activates internal routing link",
                lambda: settings_link.press("Enter"),
                "/models",
                "#modelsTab",
            )
            expect(page.locator("#modelFirstRun")).to_be_visible()
            check_navigation(
                "empty models add credentials",
                lambda: page.locator('#modelFirstRun [data-tab="providers"]').click(),
                "/providers",
                "#providersTab",
            )
            check_navigation("back from providers", page.go_back, "/models", "#modelsTab")
            check_navigation("forward to providers", page.go_forward, "/providers", "#providersTab")
            check_navigation("back to empty models", page.go_back, "/models", "#modelsTab")
            check_navigation(
                "empty models manage credentials",
                lambda: page.locator('#modelFirstRun [data-tab="pool"]').click(),
                "/pool",
                "#poolTab",
            )
            check_navigation("back from credential pool", page.go_back, "/models", "#modelsTab")

            state["configured"] = True
            page.locator("#refreshModelCatalogBtn").click()
            expect(page.locator("#testModelRouteBtn")).to_be_enabled()
            handoff = "/playground?model=polaris&source=models"
            check_navigation(
                "model Playground handoff",
                lambda: page.locator("#testModelRouteBtn").click(),
                handoff,
                "#playgroundTab",
            )
            expect(page.locator("#playgroundModel")).to_have_value("polaris")
            check_navigation("back from Playground handoff", page.go_back, "/models", "#modelsTab")
            check_navigation(
                "forward restores Playground query", page.go_forward, handoff, "#playgroundTab"
            )
            expect(page.locator("#playgroundModel")).to_have_value("polaris")
            check_navigation(
                "leave query route using sidebar",
                lambda: page.locator('.tab[data-tab="providers"]').click(),
                "/providers",
                "#providersTab",
            )
            assert not urlsplit(page.url).query, "Playground query leaked to another page"
            check_navigation("back restores query route", page.go_back, handoff, "#playgroundTab")
            # An already initialized/cached Playground must accept another handoff
            # without throwing away the user's in-memory message draft.
            page.locator("#playgroundModel").fill("different-fixture-model")
            draft = "Keep this local draft while switching between console pages."
            page.locator("#playgroundMessages textarea").first.fill(draft)
            check_navigation(
                "leave cached Playground for models",
                lambda: page.locator('.tab[data-tab="models"]').click(),
                "/models",
                "#modelsTab",
            )
            check_navigation(
                "handoff updates cached Playground",
                lambda: page.locator("#testModelRouteBtn").click(),
                handoff,
                "#playgroundTab",
            )
            expect(page.locator("#playgroundModel")).to_have_value("polaris")
            expect(page.locator("#playgroundMessages textarea").first).to_have_value(draft)
            assert not errors, errors
            assert not failures, "\n".join(failures)
            print(
                "PASS: Internal links, empty-model CTAs, query handoff, back/forward use one document"
            )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
