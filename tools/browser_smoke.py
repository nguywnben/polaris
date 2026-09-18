"""Run the required Chromium smoke across Polaris's nine critical journeys.

The harness starts a fresh loopback-only runtime with disposable storage. Provider and
inference responses are fulfilled inside the isolated browser context, so the smoke never
contacts a real provider or exposes operator credentials.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import Page, Route, expect, sync_playwright
from runtime_isolation import isolated_runtime_environment

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "Polaris-Browser-Smoke-2026"
PROVIDER_SECRET = "browser-smoke-provider-secret"
REQUEST_ID = "req-browser-smoke-001"
JOURNEYS = (
    "install-setup-dashboard",
    "provider-validation-discovery",
    "model-route-and-responses",
    "ai-quality-compression-off",
    "playground-and-safe-example",
    "virtual-key-lifecycle",
    "request-activity-correlation",
    "backup-update-rollback-guidance",
    "optional-team-login-local-recovery",
)


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_until_ready(base_url: str, process: subprocess.Popen[str], log_path: Path) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = log_path.read_text(encoding="utf-8", errors="replace")
            raise RuntimeError(f"Disposable runtime exited early.\n{output[-4000:]}")
        try:
            with urlopen(f"{base_url}/ready", timeout=1) as response:  # noqa: S310
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.2)
    raise RuntimeError("Disposable runtime did not become ready within 30 seconds.")


def _require_fresh_setup(base_url: str) -> None:
    with urlopen(f"{base_url}/api/auth/setup/status", timeout=5) as response:  # noqa: S310
        payload = json.load(response)
    if payload.get("setup_required") is not True:
        raise RuntimeError(f"Disposable runtime is not fresh: {payload!r}")


def _stop_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@contextmanager
def disposable_runtime():
    scratch = ROOT / "temp" / "browser-smoke"
    scratch.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    runtime = scratch / f"runtime-{os.getpid()}-{port}"
    runtime.mkdir()
    try:
        environment = isolated_runtime_environment(runtime, port)
        log_path = runtime / "server-output.log"
        with log_path.open("w", encoding="utf-8") as log_output:
            process = subprocess.Popen(
                [sys.executable, "backend/main.py"],
                cwd=ROOT,
                env=environment,
                stdout=log_output,
                stderr=subprocess.STDOUT,
                text=True,
            )
            base_url = f"http://127.0.0.1:{port}"
            try:
                _wait_until_ready(base_url, process, log_path)
                _require_fresh_setup(base_url)
                yield base_url
            finally:
                _stop_process_tree(process)
    finally:
        shutil.rmtree(runtime, ignore_errors=True)


def _json(route: Route, payload: dict, *, status: int = 200) -> None:
    route.fulfill(
        status=status,
        content_type="application/json",
        body=json.dumps(payload, separators=(",", ":")),
    )


def _model_catalog(configured: bool) -> dict:
    selected = ["fixture-model"] if configured else []
    validation = {
        "valid": bool(selected),
        "status": "ready" if selected else "empty",
        "issues": [],
        "available_count": len(selected),
    }
    return {
        "schema_version": "model-routing.v1",
        "catalog": [
            {
                "model_id": "fixture-model",
                "providers": ["ollama"],
                "routable_providers": ["ollama"],
                "blacklisted_providers": [],
                "available": True,
            }
        ],
        "provider_catalogs": [
            {
                "provider_id": "ollama",
                "routing_provider_id": "ollama",
                "provider_name": "Ollama",
                "models": [{"model_id": "fixture-model", "available": True}],
            }
        ],
        "pool": {
            "alias": "polaris",
            "strategy": "priority_fallback",
            "selected_models": selected,
            "enabled": True,
            "configured": configured,
            "revision": "browser-smoke-r1" if configured else "",
        },
        "validation": validation,
        "routing_policy": {
            "strategy": "balanced",
            "preferred_provider": "",
            "strategy_locked": False,
            "preferred_provider_locked": False,
        },
        "blacklist": [],
    }


def _playground_metadata(stream: bool) -> dict:
    return {
        "schema_version": "playground-metadata.v1",
        "request_id": REQUEST_ID,
        "protocol": "openai_chat",
        "requested_model": "polaris",
        "outcome": "succeeded",
        "status_code": 200,
        "duration_ms": 12,
        "route": {
            "selected_provider": "ollama",
            "selected_model": "fixture-model",
            "attempts": 1,
            "fallbacks": 0,
        },
        "usage": {"input_tokens": 4, "output_tokens": 3},
        "quality": {
            "profile": "custom",
            "policy_revision": 2,
            "compression_action": "disabled",
            "estimated_tokens_before": 4,
            "estimated_tokens_after": 4,
        },
        "stream": stream,
    }


def _trace_page() -> dict:
    decision = {
        "sequence": 1,
        "elapsed_ms": 3,
        "category": "routing",
        "action": "selected",
        "result": "succeeded",
        "reason": "healthy_candidate",
        "provider": "ollama",
        "model": "fixture-model",
        "attempt": 1,
        "status_code": 200,
        "latency_ms": 3,
        "candidate_count": 1,
        "original_tokens": 4,
        "final_tokens": 4,
        "input_tokens": 4,
        "output_tokens": 3,
        "cached_tokens": 0,
        "reasoning_tokens": 0,
        "cost_usd": 0.000007,
    }
    return {
        "traces": [
            {
                "schema_version": 1,
                "trace_id": "1" * 32,
                "request_id": REQUEST_ID,
                "protocol": "openai_chat",
                "started_at": "2026-09-11T00:00:00Z",
                "completed_at": "2026-09-11T00:00:00.012Z",
                "outcome": "succeeded",
                "status_code": 200,
                "duration_ms": 12,
                "requested_model": "polaris",
                "selected_provider": "ollama",
                "input_tokens": 4,
                "output_tokens": 3,
                "total_tokens": 7,
                "cost_usd": 0.000007,
                "decisions": [decision],
                "decisions_truncated": False,
            }
        ],
        "page_size": 25,
        "has_more": False,
        "next_cursor": None,
    }


def install_fixtures(page: Page) -> None:
    state = {"route_configured": False}
    page.route(
        "https://fonts.googleapis.com/**",
        lambda route: route.fulfill(status=200, content_type="text/css", body=""),
    )
    page.route(
        "https://fonts.gstatic.com/**",
        lambda route: route.fulfill(status=200, content_type="font/woff2", body=""),
    )

    def route_api(route: Route) -> None:
        request = route.request
        path = request.url.split("?", 1)[0]
        if path.endswith("/api/providers/ollama/credentials") and request.method == "POST":
            body = json.loads(request.post_data or "{}")
            if body.get("api_key") != PROVIDER_SECRET:
                _json(route, {"detail": "Synthetic credential was not submitted."}, status=422)
                return
            _json(
                route,
                {
                    "message": "Synthetic connection validated.",
                    "credential_action": "created",
                    "model_count": 1,
                },
            )
            return
        if path.endswith("/api/model-catalog"):
            _json(route, _model_catalog(state["route_configured"]))
            return
        if path.endswith("/api/model-routes/polaris/validate"):
            _json(
                route,
                {
                    "schema_version": "model-routing.v1",
                    "alias": "polaris",
                    "validation": {
                        "valid": True,
                        "status": "ready",
                        "issues": [],
                        "available_count": 1,
                    },
                },
            )
            return
        if path.endswith("/api/model-routes/polaris") and request.method in {"POST", "PATCH"}:
            state["route_configured"] = True
            _json(
                route,
                {"code": "model_route_created", "pool": _model_catalog(True)["pool"]},
                status=201,
            )
            return
        if path.endswith("/api/playground/runs"):
            body = json.loads(request.post_data or "{}")
            stream = body.get("stream") is True
            metadata = _playground_metadata(stream)
            if stream:
                source = (
                    'data: {"choices":[{"delta":{"content":"stream fixture"}}]}\n\n'
                    f"event: polaris.playground.metadata\ndata: {json.dumps(metadata)}\n\n"
                )
                route.fulfill(status=200, content_type="text/event-stream", body=source)
            else:
                encoded = (
                    base64.urlsafe_b64encode(json.dumps(metadata).encode()).decode().rstrip("=")
                )
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    headers={"x-polaris-playground-metadata": encoded},
                    body=json.dumps({"choices": [{"message": {"content": "fixture answer"}}]}),
                )
            return
        if path.endswith("/api/traces"):
            _json(route, _trace_page())
            return
        route.fallback()

    for pattern in (
        "**/api/providers/ollama/credentials",
        "**/api/model-catalog*",
        "**/api/model-routes/polaris",
        "**/api/model-routes/polaris/validate",
        "**/api/playground/runs",
        "**/api/traces?*",
    ):
        page.route(pattern, route_api)


def _open_tab(page: Page, name: str, target: str) -> None:
    tab = page.locator(f'[data-ui-action="switch-tab"][data-tab="{name}"]').first
    expect(tab).to_be_visible()
    tab.click()
    expect(page.locator(target)).to_be_visible()


def _assert_accessible_page(page: Page, expected_title: str | None = None) -> None:
    visible_headings = page.locator(".tab-content.active h1:visible")
    expect(visible_headings).to_have_count(1)
    if expected_title is not None:
        expect(visible_headings).to_contain_text(expected_title)
    unlabeled = page.locator(
        '.tab-content.active input:not([type="hidden"]), '
        ".tab-content.active select, .tab-content.active textarea"
    ).evaluate_all(
        """controls => controls.filter(control =>
            control.getClientRects().length > 0
            && control.getAttribute('aria-hidden') !== 'true'
            && !(control.labels && control.labels.length)
            && !control.getAttribute('aria-label')
            && !control.getAttribute('aria-labelledby')
        ).map(control => control.id || control.name || control.outerHTML.slice(0, 120))"""
    )
    if unlabeled:
        raise AssertionError(f"Active page has unlabeled controls: {unlabeled!r}")


def _complete(completed: list[str], index: int) -> None:
    journey = JOURNEYS[index]
    completed.append(journey)
    print(f"[browser-smoke] passed: {journey}", flush=True)


def _verify_responsive_routes(page: Page) -> None:
    routes = (
        ("/dashboard", "#dashboardTab"),
        ("/playground", "#playgroundTab"),
        ("/providers", "#providersTab"),
        ("/credentials", "#credentialsTab"),
        ("/models", "#modelsTab"),
        ("/ai-quality", "#qualityTab"),
        ("/access", "#accessTab"),
        ("/activity", "#activityTab"),
        ("/config", "#configTab"),
        ("/identity", "#identityTab"),
        ("/about", "#aboutTab"),
    )
    for width in (360, 768, 1024, 1440):
        page.set_viewport_size({"width": width, "height": 900})
        for path, selector in routes:
            page.evaluate("path => navigate(path, false)", path)
            expect(page.locator(selector)).to_be_visible()
            _assert_accessible_page(page)
            overflow = page.evaluate(
                "document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            if overflow > 1:
                raise AssertionError(f"{path} overflows horizontally by {overflow}px at {width}px.")
    print("[browser-smoke] responsive/accessibility sweep: 11 routes x 4 widths", flush=True)


def _verify_keyboard_navigation(page: Page) -> None:
    page.set_viewport_size({"width": 1024, "height": 900})
    page.evaluate("navigate('/dashboard', false)")
    playground_tab = page.locator(
        '#primaryNavigation [data-ui-action="switch-tab"][data-tab="playground"]'
    )
    playground_tab.focus()
    page.keyboard.press("Enter")
    expect(page.locator("#playgroundTab")).to_be_visible()
    expect(playground_tab).to_have_attribute("aria-current", "page")

    page.evaluate("navigate('/providers', false)")
    first_provider = page.locator("#providerSelectorGoogleAntigravity")
    next_provider = page.locator("#providerSelectorGoogleAiStudio")
    first_provider.focus()
    page.keyboard.press("ArrowRight")
    expect(next_provider).to_be_focused()
    expect(next_provider).to_have_attribute("aria-selected", "true")
    print("[browser-smoke] keyboard navigation: sidebar and provider selector", flush=True)


def run_journeys(page: Page, base_url: str, expected_dashboard_title: str) -> list[str]:
    completed: list[str] = []

    page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")
    try:
        expect(page.locator("#setupSection")).to_be_visible(timeout=15_000)
    except AssertionError as error:
        diagnostics = page.evaluate(
            """async () => ({
                readyState: document.readyState,
                pathname: location.pathname,
                setupDisplay: getComputedStyle(document.querySelector('#setupSection')).display,
                loginDisplay: getComputedStyle(document.querySelector('#loginSection')).display,
                mainDisplay: getComputedStyle(document.querySelector('#mainSection')).display,
                initializeConsoleType: typeof initializeConsole,
                appState: typeof AppState === 'object' ? {
                    setupRequired: AppState.setupRequired,
                    authenticated: AppState.authenticated
                } : null
            })"""
        )
        raise AssertionError(f"Setup view did not open: {diagnostics}") from error
    expect(page.locator("#setupOwnerFields")).to_be_enabled(timeout=10_000)
    page.locator("#setupPassword").fill(PASSWORD)
    page.locator("#setupPasswordConfirm").fill(PASSWORD)
    page.locator("#setupSubmitButton").click()
    expect(page).to_have_url(f"{base_url}/dashboard")
    expect(page.locator("#dashboardTab")).to_be_visible()
    expect(page.locator("#dashboardTab h1")).to_contain_text(expected_dashboard_title)
    _complete(completed, 0)

    _open_tab(page, "providers", "#providersTab")
    if not page.locator("#providerSelectorOllama").is_visible():
        page.locator("#providerCatalogNextBtn").click()
    page.locator("#providerSelectorOllama").click()
    page.locator("#ollamaBaseUrl").fill("http://127.0.0.1:11434")
    page.locator("#ollamaApiKey").fill(PROVIDER_SECRET)
    page.locator("#addOllamaBtn").click()
    expect(page.locator("#ollamaSaveResult")).to_be_visible()
    expect(page.locator("#ollamaSaveResultText")).to_contain_text("1")
    _complete(completed, 1)

    _open_tab(page, "models", "#modelsTab")
    catalog_model = page.locator('#modelCatalogList input[data-model-id="fixture-model"]')
    expect(catalog_model).to_be_visible()
    catalog_model.check()
    page.locator("#saveModelPoolBtn").click()
    expect(page.locator("#modelPoolStatus")).to_have_class(
        re.compile(r"\bsuccess\b"), timeout=15_000
    )
    _complete(completed, 2)

    _open_tab(page, "quality", "#qualityTab")
    expect(page.locator("#qualityForm")).to_be_visible()
    page.locator('input[name="qualityProfile"][value="custom"]').check()
    compression = page.locator("#tokenCompressionEnabled")
    compression.uncheck()
    page.locator("#qualitySaveButton").click()
    expect(page.locator("#qualitySaveButton")).to_be_enabled()
    expect(compression).not_to_be_checked()
    _complete(completed, 3)

    _open_tab(page, "playground", "#playgroundTab")
    prompt = page.locator('[data-playground-content="0"]')
    prompt.fill("Return a deterministic fixture response.")
    page.locator("#playgroundRun").click()
    expect(page.locator("#playgroundOutput")).to_contain_text("fixture answer")
    expect(page.locator("#playgroundMetadataRequestId")).to_have_text(REQUEST_ID)
    example = page.locator("#playgroundExample")
    expect(example).to_contain_text("YOUR_POLARIS_KEY")
    expect(example).not_to_contain_text(PROVIDER_SECRET)
    page.locator("#playgroundStream").check()
    page.locator("#playgroundRun").click()
    expect(page.locator("#playgroundOutput")).to_contain_text("stream fixture")
    _complete(completed, 4)

    _open_tab(page, "access", "#accessTab")
    page.locator(
        '#virtualKeySection .virtual-key-header [data-ui-action="virtual-key-create"]'
    ).click()
    key_form = page.locator("#virtualKeyForm")
    expect(key_form).to_be_visible()
    key_form.locator('[name="name"]').fill("Browser smoke key")
    key_form.locator('[type="submit"]').click()
    secret = page.locator("#virtualKeySecret").input_value()
    if not secret.startswith("sk-"):
        raise AssertionError("Virtual key creation did not return the expected secret shape.")
    status = page.evaluate(
        """async (key) => (await fetch('/v1/models', {
            headers: {Authorization: `Bearer ${key}`}
        })).status""",
        secret,
    )
    if status == 401:
        raise AssertionError("A newly-created virtual key was rejected as unauthenticated.")
    page.locator("[data-virtual-key-secret-close]").click()
    key_card = page.locator("#virtualKeyList .virtual-key-card", has_text="Browser smoke key")
    expect(key_card).to_be_visible()
    key_card.locator('[data-ui-action="virtual-key-rotate"]').click()
    page.locator("[data-dialog-confirm]").click()
    expect(page.locator("#virtualKeySecret")).to_be_visible()
    page.locator("[data-virtual-key-secret-close]").click()
    key_card.locator('[data-ui-action="virtual-key-revoke"]').click()
    page.locator("[data-dialog-confirm]").click()
    expect(key_card.locator(".virtual-key-status")).to_have_class(re.compile(r"\brevoked\b"))
    _complete(completed, 5)

    _open_tab(page, "activity", "#activityTab")
    page.locator("#activityRequestId").fill(REQUEST_ID)
    page.locator("#activityFilterForm").evaluate("form => form.requestSubmit()")
    trace_card = page.locator("#traceList .trace-card")
    expect(trace_card).to_contain_text(REQUEST_ID)
    expect(trace_card).to_contain_text("ollama")
    expect(trace_card).to_contain_text("7")
    body_text = page.locator("body").inner_text()
    if PROVIDER_SECRET in body_text or secret in body_text:
        raise AssertionError("A transient credential leaked into the Activity workspace.")
    _complete(completed, 6)

    _open_tab(page, "about", "#aboutTab")
    expect(page.locator("#backupGuideLink")).to_have_attribute(
        "href", re.compile(r"backup-and-restore")
    )
    expect(page.locator("#updateGuideLink")).to_have_attribute("href", re.compile(r"updating"))
    expect(page.locator("#aboutSupportTiers")).not_to_be_empty()
    _complete(completed, 7)

    page.goto(f"{base_url}/identity", wait_until="domcontentloaded")
    expect(page.locator("#identityTab")).to_be_visible()
    expect(page.locator("#identityRecoveryBadge")).to_have_class(re.compile(r"\bsuccess\b"))
    expect(page.locator("#identityModeNotice")).to_have_attribute("data-readiness", "disabled")
    _complete(completed, 8)

    _verify_responsive_routes(page)
    _verify_keyboard_navigation(page)
    return completed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expect-dashboard-title",
        default="Polaris",
        help="Assertion override used only to prove that a frontend regression fails the gate.",
    )
    args = parser.parse_args()
    try:
        with disposable_runtime() as base_url, sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            console_errors: list[str] = []

            def record_console_error(message) -> None:
                if message.type != "error":
                    return
                console_errors.append(message.text)
                print(f"[browser-console] {message.text}", file=sys.stderr, flush=True)

            def record_page_error(error) -> None:
                console_errors.append(str(error))
                print(f"[browser-pageerror] {error}", file=sys.stderr, flush=True)

            page.on(
                "console",
                record_console_error,
            )
            page.on("pageerror", record_page_error)
            install_fixtures(page)
            completed = run_journeys(page, base_url, args.expect_dashboard_title)
            context.close()
            browser.close()
            if console_errors:
                raise AssertionError("Browser console errors:\n- " + "\n- ".join(console_errors))
            if tuple(completed) != JOURNEYS:
                raise AssertionError(f"Incomplete journey coverage: {completed!r}")
    except Exception as exc:
        print(f"Browser smoke failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    print(f"Browser smoke passed: {len(JOURNEYS)}/{len(JOURNEYS)} critical journeys.")
    for journey in JOURNEYS:
        print(f"- {journey}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
