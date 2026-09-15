"""Model routing UI checks using synthetic catalog and route APIs."""

import json
from pathlib import Path

from browser_smoke import PASSWORD, _model_catalog, disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    state = {"mode": "empty", "selected": [], "configured": False, "save_error": False}

    def catalog(route):
        if state["mode"] == "error":
            route.fulfill(status=503, json={"detail": "Synthetic catalog failure"})
            return
        data = _model_catalog(state["configured"])
        if state["mode"] in ("empty", "missing"):
            data["catalog"] = []
        else:
            data["catalog"] = [
                {"model_id": name, "providers": [provider], "routable_providers": [provider], "available": True}
                for name, provider in (("gpt-fixture", "openai"), ("claude-fixture", "anthropic"))
            ]
            data["catalog"].append({
                "model_id": "unavailable-model-with-a-long-identifier-for-responsive-layout-testing",
                "providers": ["openai"], "routable_providers": [], "available": False,
            })
        data["pool"]["selected_models"] = state["selected"]
        valid = bool(state["selected"]) and state["mode"] == "populated"
        data["validation"] = {"valid": valid, "status": "ready" if valid else "unavailable"}
        if state["mode"] == "missing":
            data["blacklist"] = [{"model_id": "gpt-fixture", "provider_id": "openai", "credential_name": "synthetic.json", "last_seen_at": 1789380000}]
        route.fulfill(json=data)

    def route_api(route):
        selected = json.loads(route.request.post_data or "{}").get("selected_models", [])
        if route.request.url.endswith("/validate"):
            route.fulfill(json={"validation": {"valid": bool(selected), "status": "ready" if selected else "draft"}})
        elif state["save_error"]:
            route.fulfill(status=503, json={"detail": "Synthetic save failure"})
        else:
            state["selected"] = selected
            state["configured"] = True
            route.fulfill(json={"pool": {"selected_models": selected, "configured": True, "enabled": True, "revision": "fixture-r2"}})

    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.route("https://**", lambda route: route.abort())
        context.route("**/api/model-catalog**", catalog)
        context.route("**/api/model-routes/polaris**", route_api)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        screenshots = ROOT / "temp/models-ui"
        screenshots.mkdir(parents=True, exist_ok=True)
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.goto(base + "/models", wait_until="networkidle")
            expect(page.locator("#modelFirstRun")).to_be_visible()
            expect(page.locator("#modelRoutingPolicyPanel")).to_be_hidden()
            expect(page.locator("#modelFirstRun h2")).to_have_text("Chưa có mô hình")
            page.evaluate("AppState.lang = 'en'; applyLanguage()")
            expect(page.locator("#modelFirstRun h2")).to_have_text("No models yet")
            page.evaluate("AppState.lang = 'vi'; applyLanguage()")
            for mode in ("empty", "populated", "missing"):
                state["mode"] = mode
                if mode == "missing":
                    state["configured"] = True
                    state["selected"] = ["saved-model-with-a-long-identifier-that-is-no-longer-discovered-by-the-provider"]
                page.locator("#refreshModelCatalogBtn").click()
                expect(page.locator("#refreshModelCatalogBtn")).to_be_enabled()
                if mode == "populated":
                    expect(page.locator("#modelRoutingPolicyPanel")).to_be_visible()
                    expect(page.locator("#modelCatalogList input")).to_have_count(3)
                    expect(page.locator("#modelCatalogList input").last).to_be_disabled()
                    page.locator('[data-model-id="gpt-fixture"]').check()
                    page.locator('[data-model-id="claude-fixture"]').check()
                    page.locator("#selectedModelList .selected-model-item").nth(1).locator("button").first.click()
                    expect(page.locator("#selectedModelList strong").first).to_have_text("claude-fixture")
                    page.locator("#modelCatalogSearch").fill("no-such-model")
                    expect(page.locator("#modelCatalogList .model-empty-state")).to_be_visible()
                    expect(page.locator("#modelFirstRun")).to_be_hidden()
                    page.locator("#modelCatalogSearch").fill("")
                    state["save_error"] = True
                    page.locator("#saveModelPoolBtn").click()
                    expect(page.locator("#saveModelPoolBtn")).to_be_enabled()
                    expect(page.locator("#selectedModelList strong")).to_have_count(2)
                    expect(page.locator("#testModelRouteBtn")).to_be_disabled()
                    state["save_error"] = False
                    page.locator("#saveModelPoolBtn").click()
                    expect(page.locator("#testModelRouteBtn")).to_be_enabled()
                    assert state["selected"] == ["claude-fixture", "gpt-fixture"]
                elif mode == "missing":
                    expect(page.locator("#modelRoutingPolicyPanel")).to_be_visible()
                    expect(page.locator("#modelFirstRun")).to_be_hidden()
                    expect(page.locator("#deleteModelRouteBtn")).to_be_visible()
                    expect(page.locator("#modelBlacklistList .model-blacklist-item")).to_be_visible()
                    expect(page.locator("#testModelRouteBtn")).to_be_disabled()
                for width, theme in ((320, "light"), (360, "light"), (768, "light"), (1024, "light"), (1440, "light"), (1440, "dark")):
                    page.set_viewport_size({"width": width, "height": 1000})
                    page.emulate_media(color_scheme=theme)
                    page.mouse.move(0, 0)
                    assert not page.locator("body").evaluate("el => el.scrollWidth > innerWidth"), (mode, width)
                    assert not page.locator("#modelsTab").evaluate("el => el.scrollWidth > el.clientWidth"), (mode, width)
                    page.screenshot(path=str(screenshots / f"{mode}-{width}-{theme}.png"), full_page=True, animations="disabled")
            state["mode"] = "error"
            page.locator("#refreshModelCatalogBtn").click()
            expect(page.locator("#modelCatalogState")).to_be_visible()
            expect(page.locator("#modelPoolWorkspace")).to_be_visible()
            state["mode"] = "populated"
            page.locator("#modelCatalogState button").click()
            expect(page.locator("#modelCatalogState")).to_be_hidden()
            expect(page.locator("#testModelRouteBtn")).to_be_enabled()
            page.locator("#testModelRouteBtn").click()
            expect(page).to_have_url(base + "/playground?model=polaris&source=models")
            expect(page.locator("#playgroundModel")).to_have_value("polaris")
            assert not errors, errors
            print("PASS: Empty/existing/missing models, selection/order/search, failed/successful save, error/retry, Playground handoff, en/vi, 320–1440px light/dark")
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
