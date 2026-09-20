"""Isolated overview states, navigation, and responsive layout with synthetic traffic."""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def verify_health_status_indicator(page):
    indicator = page.locator("#providerHealthGrid .health-status").first
    expect(page.locator("#providerHealthGrid .health-badge")).to_have_count(0)
    expect(indicator.locator(".health-status-indicator")).to_have_attribute(
        "aria-label", "Hoạt động tốt"
    )
    expect(indicator.locator('[role="tooltip"]')).to_have_count(0)
    expect(indicator.locator("button.health-status-trigger")).to_have_count(0)
    dot = indicator.locator(".health-status-dot")
    bounds = dot.bounding_box()
    assert bounds["width"] == bounds["height"] == 8, bounds
    assert dot.evaluate("el => getComputedStyle(el).backgroundColor") == page.locator(
        ".health-pill.healthy .status-dot"
    ).evaluate("el => getComputedStyle(el).backgroundColor")


def main():
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.route("https://**", lambda route: route.abort())
        state = {"mode": "empty"}
        usage_requests = []
        provider_totals = [
            {
                "provider": "openai",
                "credential_type": "api_key",
                "credentials": 120,
                "calls": 120,
                "successful_calls": 118,
                "failed_calls": 2,
                "total_tokens": 12000,
                "in_cooldown": False,
            }
        ]

        def aggregate(route):
            if state["mode"] == "error":
                route.fulfill(status=503, json={"detail": "Synthetic unavailable"})
                return
            busy = state["mode"] == "populated"
            route.fulfill(
                json={
                    "success": True,
                    "data": {
                        "total_upstream_attempts": 132 if busy else 0,
                        "successful_upstream_attempts": 130 if busy else 0,
                        "failed_upstream_attempts": 2 if busy else 0,
                        "total_files": 120 if busy else (0 if state["mode"] == "empty" else 2),
                        "active_files": 120 if busy else (0 if state["mode"] == "empty" else 2),
                        "disabled_files": 0,
                        "total_cost_usd": 0.034 if busy else 0,
                        "total_tokens": 13200 if busy else 0,
                        "input_tokens": 7920 if busy else 0,
                        "output_tokens": 5280 if busy else 0,
                        "timeline": [
                            {
                                "timestamp": 1789401600 + i * 3600,
                                "requests": i if busy else 0,
                                "successful_requests": i if busy else 0,
                            }
                            for i in range(24)
                        ],
                    },
                }
            )

        def health(route):
            if state["mode"] == "error":
                route.fulfill(status=503, json={"detail": "Synthetic unavailable"})
                return
            busy = state["mode"] == "populated"
            route.fulfill(
                json={
                    "status": "warning" if busy else "no_data",
                    "red": {
                        "requests": 120 if busy else 0,
                        "errors": 2 if busy else 0,
                        "requests_per_minute": 8 if busy else 0,
                        "error_rate": 2 / 120 if busy else 0,
                        "p95_duration_ms": 234 if busy else 0,
                    },
                    "exhaustion": {},
                    "routes": [
                        {
                            "route": "polaris-with-a-long-model-route-name",
                            "requests": 120,
                            "error_rate": 2 / 120,
                            "p95_duration_ms": 234,
                            "status": "warning",
                        }
                    ]
                    if busy
                    else [],
                }
            )

        def stats(route):
            query = parse_qs(urlsplit(route.request.url).query)
            group = query.get("group", ["all"])[0]
            offset = int(query.get("offset", ["0"])[0])
            page_size = int(query.get("page_size", ["100"])[0])
            busy = state["mode"] == "populated"
            rows = {}
            for kind, count in (("current", 120), ("historical", 12)):
                if not busy or group not in ("all", kind):
                    continue
                for index in range(1, count + 1):
                    failed = kind == "current" and index > 118
                    rows[f"{kind}-{index:03}.json"] = {
                        "provider": "openai",
                        "credential_type": "api_key",
                        "credential_label": f"{kind}-{index:03}",
                        "is_historical": kind == "historical",
                        "calls": 1,
                        "successful_calls": 0 if failed else 1,
                        "failed_calls": 1 if failed else 0,
                        "total_tokens": 100,
                        "input_tokens": 60,
                        "output_tokens": 40,
                    }
            usage_requests.append({"group": group, "offset": offset, "page_size": page_size})
            route.fulfill(
                json={
                    "success": True,
                    "period": {"value": query.get("period", ["1d"])[0]},
                    "data": dict(sorted(rows.items())[offset : offset + page_size]),
                    "group": group,
                    "offset": offset,
                    "page_size": page_size,
                    "total_items": len(rows),
                    "has_more": offset + page_size < len(rows),
                    "provider_totals": provider_totals if busy else [],
                    "provider_inventory": [
                        {"provider": "openai", "credential_type": "api_key", "credentials": 1},
                        {"provider": "muse_code", "credential_type": "oauth", "credentials": 1},
                    ]
                    if state["mode"] == "idle"
                    else [],
                }
            )

        def traces(route):
            if state["mode"] == "error":
                route.fulfill(status=503, json={"detail": "Synthetic unavailable"})
                return
            route.fulfill(
                json={
                    "traces": [
                        {
                            "request_id": "req-synthetic-overview-001",
                            "requested_model": "polaris",
                            "selected_provider": "openai",
                            "outcome": "success",
                            "duration_ms": 234,
                            "started_at": "2026-09-14T14:00:00Z",
                            "cost_usd": 0.034,
                        }
                    ]
                    if state["mode"] == "populated"
                    else []
                }
            )

        context.route("**/api/usage/aggregated?*", aggregate)
        context.route("**/api/usage/stats/page?*", stats)
        context.route("**/api/observability/health?*", health)
        context.route("**/api/traces?*", traces)
        page = context.new_page()
        errors = []
        overflows = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        screenshots = ROOT / "temp/dashboard-ui"
        screenshots.mkdir(parents=True, exist_ok=True)
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            expect(page.locator("#operationalHealthEmpty")).to_be_visible()
            expect(page.locator("#dashboardStartAction")).to_have_attribute("data-tab", "providers")
            expect(page.locator("#operationalHealthMetrics")).to_be_hidden()
            expect(page.locator("#dashboardP95Latency")).to_have_text("—")
            for mode in ("empty", "populated"):
                state["mode"] = mode
                page.reload(wait_until="networkidle")
                expect(page.locator("#dashboardStats")).to_have_attribute("aria-busy", "false")
                expect(page.locator("#operationalHealthCard")).to_have_attribute(
                    "aria-busy", "false"
                )
                if mode == "populated":
                    expect(page.locator("#dashboardFirstRun")).to_be_hidden()
                    expect(page.locator("#sloErrorRate")).to_have_text("1,7%")
                    expect(page.locator("#sloP95")).to_have_text("234 ms")
                    expect(page.locator("#sloRouteRows tr")).to_have_count(1)
                    expect(
                        page.locator("#recentActivityList .dashboard-activity-item")
                    ).to_have_count(1)
                    expect(page.locator("#trafficChartCard")).to_be_visible()
                    expect(page.locator("#usageList tr")).to_have_count(10)
                    expect(page.locator("#historicalUsageList tr")).to_have_count(10)
                    details = page.locator("#usageBreakdownDetails")
                    expect(details).to_be_visible()
                    expect(details).not_to_have_attribute("open", "")
                    details.locator("summary").click()
                    expect(details).to_have_attribute("open", "")
                    summary = page.locator("#usageProviderSummary")
                    expect(summary.locator(".usage-provider-metrics dd").first).to_have_text("120")
                    full_summary = summary.inner_text()
                    for page_number in range(2, 12):
                        page.locator("#usageNextPageBtn").click()
                        expect(
                            page.locator("#usageList .usage-credential-name").first
                        ).to_have_text(f"current-{(page_number - 1) * 10 + 1:03}")
                        expect(summary).to_have_text(full_summary, use_inner_text=True)
                    expect(page.locator("#usageList .usage-credential-name").first).to_have_text(
                        "current-101"
                    )
                    page.locator("#historicalUsageNextPageBtn").click()
                    expect(page.locator("#historicalUsageList tr")).to_have_count(2)
                    expect(
                        page.locator("#historicalUsageList .usage-credential-name").first
                    ).to_have_text("historical-011")
                    expect(page.locator("#usageList .usage-credential-name").first).to_have_text(
                        "current-101"
                    )
                    expect(summary).to_have_text(full_summary, use_inner_text=True)
                    assert any(
                        item["group"] == "current" and item["offset"] == 100
                        for item in usage_requests
                    )
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
                    page.locator("#dashboardTab .page-title").click()
                    page.mouse.move(0, 0)
                    if width <= 960:
                        card_widths = page.locator("#dashboardTab .dashboard-grid").evaluate("""el => {
                            const width = el.getBoundingClientRect().width;
                            return [...el.children].filter(x => x.getBoundingClientRect().width)
                                .map(x => Math.abs(x.getBoundingClientRect().width - width));
                        }""")
                        assert all(delta <= 1 for delta in card_widths), (mode, width, card_widths)
                    if page.locator("#dashboardTab").evaluate(
                        "el => el.scrollWidth > el.clientWidth"
                    ):
                        overflows.append(
                            (
                                mode,
                                width,
                                page.locator("#dashboardTab").evaluate("""el =>
                            [...el.querySelectorAll('*')].filter(x => x.getBoundingClientRect().width &&
                                x.getBoundingClientRect().right > el.getBoundingClientRect().right + 1)
                            .slice(0, 12).map(x => [x.id, x.className, Math.round(x.getBoundingClientRect().right)])"""),
                            )
                        )
                    if page.locator("body").evaluate("el => el.scrollWidth > innerWidth"):
                        overflows.append((mode, width, "body"))
                    page.screenshot(
                        path=str(screenshots / f"{mode}-{width}-{theme}.png"),
                        full_page=True,
                        animations="disabled",
                    )
                    if mode == "populated":
                        verify_health_status_indicator(page)
                        for index in (0, 11, 23):
                            bar = page.locator(".timeline-bar-col").nth(index)
                            page.keyboard.press("Tab")
                            bar.focus()
                            expect(bar.locator(".timeline-tooltip")).to_be_visible()
                            tooltip_box = bar.locator(".timeline-tooltip").bounding_box()
                            assert tooltip_box["width"] >= 100 and tooltip_box["height"] < 200, (
                                tooltip_box
                            )
                            assert not page.locator("#dashboardTab").evaluate(
                                "el => el.scrollWidth > el.clientWidth"
                            ), (width, index)
            touch_context = browser.new_context(
                locale="vi-VN",
                viewport={"width": 360, "height": 800},
                has_touch=True,
                is_mobile=True,
            )
            touch_context.route("https://**", lambda route: route.abort())
            touch_context.route("**/api/usage/aggregated?*", aggregate)
            touch_context.route("**/api/usage/stats/page?*", stats)
            touch_context.route("**/api/observability/health?*", health)
            touch_context.route("**/api/traces?*", traces)
            touch_page = touch_context.new_page()
            touch_page.on("pageerror", lambda error: errors.append(str(error)))
            touch_page.goto(base + "/login", wait_until="networkidle")
            touch_page.locator("#loginPassword").fill(PASSWORD)
            touch_page.locator("#loginSubmitButton").click()
            touch_indicator = touch_page.locator("#providerHealthGrid .health-status").first
            expect(touch_indicator.locator(".health-status-indicator")).to_have_attribute(
                "aria-label", "Hoạt động tốt"
            )
            expect(touch_indicator.locator('[role="tooltip"]')).to_have_count(0)
            touch_context.close()
            state["mode"] = "idle"
            page.locator("#usagePeriodSelect").select_option("7d")
            expect(page.locator("#dashboardFirstRun")).to_be_visible()
            expect(page.locator("#dashboardStartAction")).to_have_attribute(
                "data-tab", "playground"
            )
            expect(page.locator("#totalApiCallsLabel")).to_contain_text("7")
            expect(page.locator("#providerHealthGrid .provider-health-item")).to_have_count(2)
            expect(page.locator("#providerHealthGrid .status-idle")).to_have_count(2)
            expect(page.locator("#providerHealthGrid")).to_contain_text("Muse Code")
            expect(page.locator("#providerHealthGrid")).not_to_contain_text("0%")
            idle_indicator = page.locator("#providerHealthGrid .health-status").first
            expect(idle_indicator.locator("button")).to_have_accessible_description(
                "Sẵn sàng / Chờ"
            )
            assert idle_indicator.locator(".health-status-dot").evaluate(
                "el => getComputedStyle(el).backgroundColor"
            ) == page.locator(".health-pill.warning .status-dot").evaluate(
                "el => getComputedStyle(el).backgroundColor"
            )
            state["mode"] = "error"
            page.locator("#usagePeriodSelect").select_option("30d")
            expect(page.locator("#dashboardUsageState")).to_be_visible()
            expect(page.locator("#operationalHealthEmpty")).to_be_visible()
            expect(page.locator("#operationalHealthMetrics")).to_be_hidden()
            expect(page.locator("#operationalHealthEmpty")).not_to_contain_text("khoảng thời gian")
            state["mode"] = "empty"
            page.locator("#usagePeriodSelect").select_option("1d")
            expect(page.locator("#dashboardUsageState")).to_be_hidden()
            expect(page.locator("#providerHealthGrid .provider-health-item")).to_have_count(0)
            page.locator("#dashboardStartAction").press("Enter")
            expect(page).to_have_url(base + "/providers")
            assert not errors, errors
            assert not overflows, overflows
            (screenshots / "result.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "current_rows": 120,
                        "historical_rows": 12,
                        "visited_current_row": 101,
                        "provider_calls_on_every_page": 120,
                        "historical_page_independent": True,
                        "page_errors": errors,
                        "overflows": overflows,
                        "health_status_hints": "disabled; status remains accessible",
                        "usage_requests": usage_requests,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(
                "PASS: overview empty/populated/idle/error/recovery, row101 server pagination, "
                "independent history and complete provider totals, period and keyboard navigation; "
                "health dots without hover/focus/click tooltips; 320–1440px, light/dark"
            )
            print(f"Evidence: {screenshots}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
