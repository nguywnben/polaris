"""Exercise setup presentation with synthetic secrets in an isolated browser/runtime."""

from __future__ import annotations

import json
from pathlib import Path

from browser_smoke import disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    screenshots = ROOT / "temp" / "setup-ui"
    screenshots.mkdir(parents=True, exist_ok=True)
    with disposable_runtime() as base_url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1100})
            context.add_init_script("""window.__invalidDefaults = [];
                document.addEventListener('invalid', event => {
                    setTimeout(() => window.__invalidDefaults.push(event.defaultPrevented), 0);
                }, true);
            """)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            # Avoid depending on a third-party font service for functional checks.
            context.route(
                "https://fonts.googleapis.com/**",
                lambda route: route.fulfill(body="", content_type="text/css"),
            )
            checks = {
                "data": {"status": "pass", "code": "data_writable"},
                "address": {"status": "pass", "code": "address_valid"},
                "transport": {"status": "pass", "code": "transport_local"},
                "setup_token": {"status": "pending", "code": "setup_token_required"},
                "owner": {"status": "pending", "code": "owner_creation_ready"},
            }
            state = {
                "state": "resumed",
                "next_action": "create_owner",
                "setup_required": True,
                "authenticated": False,
                "setup_token_required": True,
                "checks": checks,
                "base_url": base_url,
                "listener": "0.0.0.0:4283",
            }
            context.route("**/api/auth/setup/status", lambda route: route.fulfill(json=state))
            attempts = []
            pending_checks = []

            def preflight(route):
                attempts.append(route.request.post_data_json)
                if route.request.post_data_json.get("setup_token") == "synthetic-slow-token":
                    pending_checks.append(route)
                    return
                if route.request.post_data_json.get("setup_token") == "synthetic-wrong-token":
                    route.fulfill(status=403, json={"detail": "Synthetic invalid setup token"})
                    return
                checks["setup_token"] = {"status": "pass", "code": "setup_token_verified"}
                state.update(state="resumed", next_action="create_owner")
                route.fulfill(json=state)

            context.route("**/api/auth/setup/preflight", preflight)
            submissions = []

            def submit(route):
                submissions.append(route.request.post_data_json)
                route.fulfill(status=400, json={"detail": "Synthetic validation response"})

            context.route("**/api/auth/setup", submit)
            page.goto(base_url + "/setup", wait_until="networkidle")
            expect(page.locator("#setupTokenGroup")).to_be_visible()
            page.set_viewport_size({"width": 320, "height": 900})
            for value in ("", "synthetic-token", ""):
                page.locator("#setupToken").fill(value)
                padding = page.locator("#setupToken").evaluate("""el => {
                    const style = getComputedStyle(el);
                    return [style.paddingInlineStart, style.paddingInlineEnd];
                }""")
                if value:
                    expect(page.locator("#setupTokenToggle")).to_be_visible()
                    assert float(padding[1][:-2]) >= 40, padding
                else:
                    expect(page.locator("#setupTokenToggle")).to_be_hidden()
                    assert padding[0] == padding[1], (
                        "Empty input must not reserve space for the hidden eye button",
                        padding,
                    )
            placeholder_fits = page.locator("#setupToken").evaluate("""el => {
                const style = getComputedStyle(el);
                const canvas = document.createElement('canvas');
                const context = canvas.getContext('2d');
                context.font = style.font;
                return context.measureText(el.placeholder).width <= el.clientWidth
                    - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
            }""")
            assert placeholder_fits, "Setup placeholder must fit at 320px without clipping"
            clipped_locales = page.locator("#setupToken").evaluate("""el => {
                const style = getComputedStyle(el);
                const context = document.createElement('canvas').getContext('2d');
                context.font = style.font;
                const available = el.clientWidth - parseFloat(style.paddingLeft)
                    - parseFloat(style.paddingRight);
                return Object.entries(AUTH_LOCALE_TRANSLATIONS)
                    .filter(([, copy]) => context.measureText(copy.setup_token_placeholder).width > available)
                    .map(([locale]) => locale);
            }""")
            assert not clipped_locales, clipped_locales
            page.screenshot(path=str(screenshots / "setup-placeholder-320.png"), full_page=True)
            highlight = page.locator("#setupPreflightButton").evaluate(
                "el => getComputedStyle(el).webkitTapHighlightColor"
            )
            assert highlight == "rgba(128, 128, 128, 0.16)", highlight
            page.locator("#setupToken").focus()
            page.keyboard.press("Tab")
            expect(page.locator("#setupPreflightButton")).to_be_focused()
            assert (
                page.locator("#setupPreflightButton").evaluate(
                    "el => getComputedStyle(el).outlineStyle"
                )
                != "none"
            ), "Keyboard focus must remain visible"
            page.set_viewport_size({"width": 1440, "height": 1100})
            expect(page.locator("#setupPassword")).to_be_disabled()
            expect(page.locator("#setupPasswordConfirm")).to_be_disabled()
            expect(page.locator("#setupSubmitButton")).to_be_disabled()
            expect(page.locator("#setupPreflightAction")).to_be_visible()
            expect(page.locator("#setupPasswordToggle")).to_be_disabled()
            for field in ("setupToken", "setupPassword", "setupPasswordConfirm"):
                expect(page.locator(f"#{field}Toggle")).to_be_hidden()
            for empty_token in ("", "   "):
                page.locator("#setupToken").fill(empty_token)
                page.locator("#setupPreflightButton").click()
                expect(page.locator("#statusSection")).to_contain_text(
                    "Nhập mã thiết lập do người vận hành cấu hình, rồi chạy kiểm tra."
                )
                assert not attempts, "Empty tokens must be caught before a preflight request"
                expect(page.locator("#setupPassword")).to_be_disabled()
            page.locator("#setupToken").fill("synthetic-setup-token-for-ui-tests")
            token_button = page.locator("#setupTokenToggle")
            expect(token_button).to_have_accessible_name("Hiện nội dung")
            token_button.click()
            expect(page.locator("#setupToken")).to_have_attribute("type", "text")
            expect(token_button).to_have_attribute("aria-pressed", "true")
            assert (
                token_button.evaluate("el => getComputedStyle(el).backgroundColor")
                == "rgba(0, 0, 0, 0)"
            )
            token_button.press("Space")
            expect(page.locator("#setupToken")).to_have_attribute("type", "password")
            assert not attempts and not submissions, "Eye toggle must not send requests"
            token_button.click()
            page.locator("#setupToken").fill("")
            expect(token_button).to_be_hidden()
            expect(page.locator("#setupToken")).to_have_attribute("type", "password")
            page.locator("#setupToken").fill("synthetic-setup-token-for-ui-tests")
            expect(token_button).to_be_visible()
            page.locator("#setupToken").fill("synthetic-wrong-token")
            page.locator("#setupPreflightButton").click()
            expect(page.locator("#statusSection .error")).to_contain_text(
                "Synthetic invalid setup token"
            )
            expect(page.locator("#setupToken")).to_have_value("synthetic-wrong-token")
            expect(page.locator("#setupToken")).to_have_attribute("type", "password")
            expect(page.locator("#setupPassword")).to_be_disabled()
            page.locator("#setupToken").fill("synthetic-setup-token-for-ui-tests")
            page.locator("#setupPreflightButton").click()
            expect(page.locator("#setupPassword")).to_be_enabled()
            expect(page.locator("#setupPassword")).not_to_be_focused()
            expect(page.locator("#setupPreflightAction")).to_be_visible()
            expect(page.locator("#setupPreflightAction")).to_have_text(
                "Kiểm tra đã đạt. Hãy tạo mật khẩu chủ sở hữu."
            )
            expect(page.locator("#statusSection .success")).to_have_text(
                "Kiểm tra đã đạt. Hãy tạo mật khẩu chủ sở hữu."
            )
            assert len(attempts) == 2

            page.locator("#setupToken").fill("synthetic-slow-token")
            expect(page.locator("#setupPreflightAction")).to_have_text(
                "Nhập mã thiết lập do người vận hành cấu hình, rồi chạy kiểm tra."
            )
            page.locator("#setupPreflightButton").click()
            expect(page.locator("#setupPreflightButton")).to_be_disabled()
            page.locator("#setupToken").fill("synthetic-edited-while-checking")
            assert len(pending_checks) == 1
            pending_checks.pop().fulfill(json=state)
            expect(page.locator("#setupPreflightButton")).to_be_enabled()
            expect(page.locator("#setupPassword")).to_be_disabled()

            page.locator("#setupToken").fill("synthetic-wrong-token")
            expect(page.locator("#setupPassword")).to_be_disabled()
            expect(page.locator("#setupPasswordConfirm")).to_be_disabled()
            expect(page.locator("#setupSubmitButton")).to_be_disabled()
            page.locator("#setupPreflightButton").click()
            expect(page.locator("#statusSection .error")).to_contain_text(
                "Synthetic invalid setup token"
            )
            expect(page.locator("#setupPassword")).to_be_disabled()
            page.locator("#setupToken").fill("synthetic-setup-token-for-ui-tests")
            page.locator("#setupPreflightButton").click()
            expect(page.locator("#setupPassword")).to_be_enabled()

            rules = page.locator("[data-password-check]")
            expect(rules).to_have_count(4)
            expect(page.locator("#setupOwnerFields .password-checklist")).to_have_count(1)
            expect(page.locator("#setupPasswordRules [data-password-check]")).to_have_count(4)
            expect(page.locator('[data-password-check][data-met="true"]')).to_have_count(0)
            page.locator("#setupPassword").fill("aaaaaaaaaaaa")
            expect(page.locator('[data-password-check="length"]')).to_have_attribute(
                "data-met", "true"
            )
            expect(page.locator('[data-password-check="variety"]')).to_have_attribute(
                "data-met", "false"
            )
            page.locator("#setupPassword").fill("password1234")
            expect(page.locator('[data-password-check="uncommon"]')).to_have_attribute(
                "data-met", "false"
            )
            page.locator("#setupPasswordConfirm").fill("password1234")
            page.locator("#setupSubmitButton").click()
            assert not submissions, "Blocked common passwords must not be submitted"
            page.locator("#setupPassword").fill("correct horse battery staple")
            expect(page.locator('[data-password-check="match"]')).to_have_attribute(
                "data-met", "false"
            )
            page.locator("#setupPasswordConfirm").fill("correct horse battery staple")
            expect(page.locator('[data-password-check][data-met="true"]')).to_have_count(4)
            page.locator("#setupPassword").fill("another valid passphrase")
            page.locator("#setupSubmitButton").click()
            expect(page.locator("#setupPasswordConfirm")).to_have_attribute("aria-invalid", "true")
            page.locator("#setupPassword").fill("correct horse battery staple")
            expect(page.locator("#setupPasswordConfirm")).not_to_have_attribute(
                "aria-invalid", "true"
            )
            page.locator("#setupPassword").fill("")
            page.locator("#setupPasswordConfirm").fill("")
            expect(page.locator('[data-password-check][data-met="true"]')).to_have_count(0)

            page.locator("#setupSubmitButton").click()
            expect(page.locator("#statusSection .error")).to_contain_text(
                "Vui lòng nhập hoặc chọn giá trị"
            )
            expect(page.locator("#setupPassword")).to_have_attribute("aria-invalid", "true")
            error_border = page.locator("#setupPassword").evaluate(
                "el => getComputedStyle(el).borderTopColor"
            )
            assert not submissions, "Required fields must still block submission"
            assert page.evaluate(
                "window.__invalidDefaults.length > 0 && window.__invalidDefaults.every(Boolean)"
            )
            for field in ("setupPassword", "setupPasswordConfirm"):
                page.locator(f"#{field}").fill("short")
                expect(page.locator(f"#{field}")).not_to_have_attribute("aria-invalid", "true")
                page.wait_for_timeout(180)
                assert (
                    page.locator(f"#{field}").evaluate("el => getComputedStyle(el).borderTopColor")
                    != error_border
                )
            page.locator("#setupSubmitButton").click()
            expect(page.locator("#statusSection .error")).to_contain_text("ít nhất 12 ký tự")
            assert not submissions, "Minimum length must still block submission"

            for field in ("setupPassword", "setupPasswordConfirm"):
                page.locator(f"#{field}").fill("Synthetic-Password-2026")
                expect(page.locator(f"#{field}")).not_to_have_attribute("aria-invalid", "true")
                button = page.locator(f"#{field}Toggle")
                button.focus()
                button.press("Enter")
                expect(page.locator(f"#{field}")).to_have_attribute("type", "text")
                expect(page.locator("#setupToken")).to_have_attribute("type", "password")
                button.press("Space")
                expect(page.locator(f"#{field}")).to_have_attribute("type", "password")
            assert not submissions, "Keyboard eye toggle must not submit the form"

            # Independent toggles and label activation do not change visibility.
            page.locator("#setupPasswordToggle").click()
            expect(page.locator("#setupPasswordConfirm")).to_have_attribute("type", "password")
            page.locator("#setupPasswordLabel").click()
            expect(page.locator("#setupPassword")).not_to_be_focused()
            page.locator("#setupSubmitButton").click()
            expect(page.locator("#setupPassword")).to_have_value("")
            assert len(submissions) == 1
            for field in ("setupToken", "setupPassword", "setupPasswordConfirm"):
                expect(page.locator(f"#{field}")).to_have_value("")
                expect(page.locator(f"#{field}")).to_have_attribute("type", "password")
                expect(page.locator(f"#{field}Toggle")).to_have_attribute("aria-pressed", "false")
                expect(page.locator(f"#{field}Toggle")).to_be_hidden()

            # Reload to remove the synthetic error before the batched visual inspection.
            checks["transport"] = {"status": "warning", "code": "transport_insecure_allowed"}
            page.reload(wait_until="networkidle")
            expect(page.locator("#setupHttpWarning")).to_be_visible()
            expect(page.locator("#setupHttpWarning")).to_contain_text("HTTP không mã hóa")
            expect(page.locator("#setupCheckTransport")).to_have_attribute("data-status", "warning")
            expect(page.locator("#setupCheckTransport")).to_contain_text("Đã cho phép HTTP")
            expect(page.locator("#setupPassword")).to_be_disabled()
            page.locator("#setupToken").fill("synthetic-setup-token-for-ui-tests")
            page.locator("#setupPreflightButton").click()
            expect(page.locator("#setupPassword")).to_be_enabled()
            expect(page.locator("#setupHttpWarning")).to_be_visible()
            for width, theme in ((1440, "light"), (768, "light"), (320, "light"), (1440, "dark")):
                page.set_viewport_size({"width": width, "height": 1100})
                page.emulate_media(color_scheme=theme)
                for field in ("setupPassword", "setupPasswordConfirm"):
                    page.locator(f"#{field}").fill("Synthetic-Layout-Value")
                    control = page.locator(f"#{field}").bounding_box()
                    toggle = page.locator(f"#{field}Toggle").bounding_box()
                    assert control and toggle
                    assert toggle["x"] >= control["x"]
                    assert toggle["x"] + toggle["width"] <= control["x"] + control["width"] + 1
                    assert toggle["y"] >= control["y"], (field, width, control, toggle)
                    assert toggle["y"] + toggle["height"] <= control["y"] + control["height"] + 1
                    page.locator(f"#{field}").fill("")
                overflow = page.locator("#setupSection").evaluate(
                    "el => el.scrollWidth > el.clientWidth"
                )
                assert not overflow, f"Overflow at {width}px"
                check_button = page.locator("#setupPreflightButton").bounding_box()
                expected_height = 32  # Owner-approved compact control size at every breakpoint.
                assert abs(check_button["height"] - expected_height) <= 1, (
                    "Use shared button sizing, including mobile touch targets"
                )
                assert check_button["width"] < 150, "Check button must stay compact on mobile"
                checklist = page.locator("#setupPasswordRules").bounding_box()
                confirmation = page.locator("#setupPasswordConfirm").bounding_box()
                submit_button = page.locator("#setupSubmitButton").bounding_box()
                assert checklist["y"] >= confirmation["y"] + confirmation["height"]
                assert checklist["y"] + checklist["height"] <= submit_button["y"]
                page.locator("#setupPassword").fill("correct horse battery staple")
                page.locator("#setupPasswordConfirm").fill("correct horse battery staple")
                expect(page.locator('[data-password-check][data-met="true"]')).to_have_count(4)
                page.screenshot(
                    path=str(screenshots / f"setup-{width}-{theme}.png"), full_page=True
                )
            checks["transport"] = {"status": "fail", "code": "https_required"}
            state.update(state="invalid", next_action="use_https")
            page.reload(wait_until="networkidle")
            expect(page.locator("#setupPreflightAction")).to_contain_text(
                "SETUP_ALLOW_INSECURE_HTTP=true"
            )
            expect(page.locator("#setupHttpWarning")).to_be_visible()
            expect(page.locator("#setupPassword")).to_be_disabled()
            checks["transport"] = {"status": "pass", "code": "transport_secure"}
            state.update(state="fresh", next_action="enter_setup_token")
            page.reload(wait_until="networkidle")
            expect(page.locator("#setupHttpWarning")).to_be_hidden()
            assert not errors, errors
            print(
                json.dumps(
                    {
                        "result": "passed",
                        "viewports": [320, 768, 1440],
                        "themes": ["light", "dark"],
                        "page_errors": errors,
                        "screenshots": str(screenshots),
                    }
                )
            )
        finally:
            browser.close()


if __name__ == "__main__":
    main()
