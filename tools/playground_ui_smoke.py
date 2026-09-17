"""Exercise Playground layout and request states without calling any provider."""

import base64
import json
from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.route("https://**", lambda route: route.abort())
        state = {"mode": "success", "requests": 0, "pending": None}
        metadata = {
            "outcome": "succeeded",
            "status_code": 200,
            "request_id": "req-ui-fixture",
            "duration_ms": 240,
            "route": {"selected_provider": "fixture", "selected_model": "polaris"},
            "usage": {"input_tokens": 12, "output_tokens": 8},
            "quality": {"profile": "balanced"},
        }

        def respond(route):
            state["requests"] += 1
            if state["mode"] == "pending":
                state["pending"] = route
            elif state["mode"] == "error":
                route.fulfill(
                    status=503, json={"error": {"message": "Synthetic provider unavailable"}}
                )
            elif state["mode"] == "stream":
                route.fulfill(
                    content_type="text/event-stream",
                    body='data: {"text":"Stream fixture"}\n\ndata: [DONE]\n\n',
                )
            else:
                route.fulfill(
                    headers={
                        "x-polaris-playground-metadata": base64.b64encode(
                            json.dumps(metadata).encode()
                        ).decode()
                    },
                    json={
                        "choices": [
                            {
                                "message": {
                                    "content": "<img src=x onerror=alert(1)> Fixture response"
                                }
                            }
                        ]
                    },
                )

        context.route("**/api/playground/runs", respond)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        screenshots = ROOT / "temp/playground-ui"
        screenshots.mkdir(parents=True, exist_ok=True)
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.goto(base + "/playground", wait_until="networkidle")
            guidance = page.locator("#playgroundCatalogState")
            expect(guidance).to_contain_text("Chưa có mô hình")
            guidance.locator("button").click()
            expect(page).to_have_url(base + "/models")
            expect(page.locator("#modelFirstRun")).to_be_visible()
            held_catalog = []
            page.route("**/api/model-catalog", lambda route: held_catalog.append(route))
            page.goto(base + "/playground", wait_until="domcontentloaded")
            expect(guidance.locator(".region-skeleton")).to_be_visible()
            expect(guidance).to_have_attribute("aria-busy", "true")
            held_catalog.pop().fulfill(status=503, json={"detail": "Synthetic unavailable"})
            expect(guidance.locator("[role=alert]")).to_be_visible()
            expect(guidance).not_to_contain_text("Chưa có mô hình")
            expect(guidance).to_have_attribute("aria-busy", "false")
            page.unroute("**/api/model-catalog")
            guidance.locator("button").click()
            expect(guidance).to_contain_text("Chưa có mô hình")
            expect(page.locator("#playgroundRun")).to_be_enabled()
            assert state["requests"] == 0, "Readiness checks must not send inference"
            expect(page.locator("#playgroundMessageCount")).to_have_text("1 / 32")
            expect(
                page.locator(".playground-messages-heading #playgroundMessageCount")
            ).to_be_visible()
            expect(page.locator("#playgroundOutputLimit")).to_be_visible()
            expect(page.locator("#playgroundCancel")).to_be_disabled()
            page.locator("#playgroundRun").click()
            assert state["requests"] == 0, "An empty message must not call the provider"
            page.locator("[data-playground-content]").fill(
                "Hello, this is a disposable UI fixture."
            )
            expect(page.locator("#playgroundValidation")).to_be_hidden()
            page.locator("#playgroundAddMessage").click()
            expect(page.locator("[data-playground-content]").nth(1)).to_be_focused()
            page.locator("[data-playground-content]").nth(1).fill("Synthetic reply")
            page.locator('[data-ui-action="playground-remove-message"]').nth(1).click()
            expect(page.locator("#playgroundMessageCount")).to_have_text("1 / 32")
            expect(page.locator("[data-playground-content]")).to_have_value(
                "Hello, this is a disposable UI fixture."
            )
            assert (
                page.locator("[data-playground-content]").evaluate(
                    "el => getComputedStyle(el).fontWeight"
                )
                == "400"
            )
            page.locator("#playgroundModel").focus()
            page.locator('label[for="playgroundTimeout"]').click()
            expect(page.locator("#playgroundTimeout")).not_to_be_focused()
            for protocol in ("openai_chat", "openai_responses", "anthropic_messages", "gemini"):
                page.locator("#playgroundProtocol").select_option(protocol)
                expect(page.locator("#playgroundProtocolHint")).not_to_be_empty()
            page.locator(".playground-parameters > summary").click()
            page.locator("#playgroundProtocol").select_option("anthropic_messages")
            expect(page.locator("#playgroundTemperature")).to_have_attribute("max", "1")
            page.locator("#playgroundProtocol").select_option("openai_chat")
            expect(page.locator("#playgroundTemperature")).to_have_attribute("max", "2")
            page.locator(".playground-example-card > summary").click()
            for example_format in ("curl", "powershell", "python", "node"):
                page.locator("#playgroundExampleFormat").select_option(example_format)
                expect(page.locator("#playgroundExample")).to_contain_text("YOUR_POLARIS_KEY")

            def check_layout(name):
                for width, theme in (
                    (320, "light"),
                    (360, "light"),
                    (768, "light"),
                    (1024, "light"),
                    (1440, "light"),
                    (1440, "dark"),
                ):
                    page.set_viewport_size({"width": width, "height": 1000})
                    page.emulate_media(color_scheme=theme)
                    page.mouse.move(0, 0)
                    assert not page.locator("body").evaluate("el => el.scrollWidth > innerWidth"), (
                        name,
                        width,
                    )
                    assert not page.locator("#playgroundTab").evaluate(
                        "el => el.scrollWidth > el.clientWidth"
                    ), (name, width)
                    if width <= 1080:
                        composer = page.locator("#playgroundForm").bounding_box()
                        results = page.locator(".playground-results").bounding_box()
                        assert results["y"] >= composer["y"] + composer["height"], (name, width)
                    page.screenshot(
                        path=str(screenshots / f"{name}-{width}-{theme}.png"),
                        full_page=True,
                        animations="disabled",
                    )

            check_layout("empty-expanded")
            page.locator(".playground-parameters > summary").click()
            page.locator(".playground-example-card > summary").click()
            page.emulate_media(color_scheme="light")
            page.screenshot(
                path=str(screenshots / "empty-desktop.png"), full_page=True, animations="disabled"
            )
            state["mode"] = "pending"
            page.locator("#playgroundRun").click()
            expect(page.locator("#playgroundRun")).to_have_attribute("aria-busy", "true")
            expect(page.locator("#playgroundRun")).to_be_disabled()
            expect(page.locator("#playgroundCancel")).to_be_enabled()
            expect(page.locator("#playgroundModel")).to_be_disabled()
            expect(page.locator("#playgroundRun")).to_have_text(
                page.evaluate("t('playground.running')")
            )
            page.locator("#playgroundCancel").click()
            expect(page.locator("#playgroundOutcome")).to_have_text(
                page.evaluate("t('playground.cancelled')")
            )
            expect(page.locator("#playgroundRun")).to_be_enabled()
            if state["pending"]:
                state["pending"].abort()
            state["mode"] = "success"
            page.locator("#playgroundRun").click()
            expect(page.locator("#playgroundOutcome")).to_have_class("status-badge success")
            expect(page.locator("#playgroundRun")).to_have_text(
                page.evaluate("t('playground.run')")
            )
            expect(page.locator("#playgroundOutput")).to_contain_text("<img")
            expect(page.locator("#playgroundOutput img")).to_have_count(0)
            expect(page.locator("#playgroundMetadataRequestId")).to_have_text("req-ui-fixture")
            check_layout("result")
            state["mode"] = "error"
            page.locator("#playgroundRun").click()
            expect(page.locator("#playgroundError")).to_have_text("Synthetic provider unavailable")
            expect(page.locator("#playgroundRun")).to_be_enabled()
            state["mode"] = "stream"
            page.locator("#playgroundStream").check()
            page.locator("#playgroundRun").click()
            expect(page.locator("#playgroundOutput")).to_contain_text("Stream fixture")
            expect(page.locator("#playgroundOutcome")).to_have_class("status-badge success")
            expect(page.locator("#playgroundError")).to_be_hidden()
            assert not errors, errors
            print(
                "PASS: Playground states, protocols, safe output, expanded controls, light/dark, 320–1440px"
            )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
