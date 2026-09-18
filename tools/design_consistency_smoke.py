"""Bounded empty-state design matrix with screenshots and measurable findings."""

import argparse
import json
from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SIZES = ((360, 800), (768, 1024), (844, 390), (1024, 768), (1440, 900), (1920, 1080))
ROUTES = (
    "dashboard",
    "providers",
    "credentials",
    "models",
    "ai-quality",
    "playground",
    "access",
    "identity",
    "activity",
    "activity?view=audit",
    "activity?view=runtime",
    "config",
    "about",
)
AUDIT = """() => {
    const visible = el => el.checkVisibility({checkVisibilityCSS:true}) && !el.closest('[inert]');
    const label = el => el.id || el.className || el.tagName;
    const controls = [...document.querySelectorAll('button,input,select,textarea,summary,a[href]')].filter(visible);
    const overflow = [...document.querySelectorAll('main *, .login-wrapper *, .oauth-callback-card *')]
        .filter(visible).filter(el => {
            const r=el.getBoundingClientRect(); return r.width && (r.right > innerWidth+1 || r.left < -1);
        }).slice(0,15).map(label);
    const tiny = controls.filter(el => !el.disabled && !el.matches('input[type=checkbox],input[type=radio],a') && el.getBoundingClientRect().height < 31.5)
        .map(el => ({el:label(el), height:Math.round(el.getBoundingClientRect().height)}));
    const missingNames = controls.filter(el => el.matches('input,select,textarea') &&
        !el.labels?.length && !el.getAttribute('aria-label') && !el.getAttribute('aria-labelledby')).map(label);
    const placeholder = controls.filter(el => el.matches('textarea,input:is([type=text],[type=password],[type=search],[type=url],[type=number],[type=email],[type=datetime-local])'))
        .filter(el => !el.placeholder.trim() || getComputedStyle(el,'::placeholder').fontWeight !== '400').map(label);
    const rgb = value => (value.match(/[\\d.]+/g)||[]).map(Number);
    const blend = (fg,bg) => fg.slice(0,3).map((v,i)=>v*(fg[3]??1)+bg[i]*(1-(fg[3]??1)));
    const lum = c => c.slice(0,3).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
    const contrast = [];
    for(const el of document.querySelectorAll('body *')) {
        if(!visible(el) || el.closest(':disabled,[aria-disabled=true],.skeleton,svg') || ![...el.childNodes].some(n=>n.nodeType===3 && n.textContent.trim()))continue;
        const style=getComputedStyle(el); if(Number(style.opacity)<1)continue;
        const layers=[]; let node=el;
        while(node){layers.push(rgb(getComputedStyle(node).backgroundColor));node=node.parentElement;}
        let bg=[255,255,255]; for(const layer of layers.reverse()) bg=blend(layer,bg);
        const fg=blend(rgb(style.color),bg); const a=lum(fg),b=lum(bg); const ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
        const large=parseFloat(style.fontSize)>=24 || (parseFloat(style.fontSize)>=18.66 && Number(style.fontWeight)>=700);
        if(ratio < (large?3:4.5)-.01)contrast.push({el:label(el),text:el.textContent.trim().slice(0,65),ratio:+ratio.toFixed(2),color:style.color});
    }
    const logo = [...document.querySelectorAll('.app-mark-image')].filter(visible)
        .map(el => ({el:label(el),filter:getComputedStyle(el).filter}));
    const healthIconProbe = document.createElement('div');
    healthIconProbe.className = 'health-item-logo';
    healthIconProbe.setAttribute('aria-hidden', 'true');
    document.body.append(healthIconProbe);
    const healthIconChrome = {
        background: getComputedStyle(healthIconProbe).backgroundColor,
        borderWidth: getComputedStyle(healthIconProbe).borderWidth
    };
    healthIconProbe.remove();
    const healthGrid = document.querySelector('#providerHealthGrid');
    let healthGridColumns = 0;
    if (healthGrid) {
        const originalHealthGrid = healthGrid.innerHTML;
        healthGrid.innerHTML = Array.from({length: 6}, () => '<div class="provider-health-item"></div>').join('');
        healthGridColumns = getComputedStyle(healthGrid).gridTemplateColumns.trim().split(' ').length;
        healthGrid.innerHTML = originalHealthGrid;
    }
    const usageSummary = document.querySelector('#usageProviderSummary');
    const usageSummaryMarginBottom = usageSummary
        ? getComputedStyle(usageSummary).marginBottom
        : null;
    const overlaps = [...document.querySelectorAll('.recent-activity-header + .card-title-copy')].filter(visible)
        .filter(el=>el.getBoundingClientRect().top < el.previousElementSibling.getBoundingClientRect().bottom).map(label);
    return {overflow,tiny,missingNames,placeholder,contrast,logo,healthIconChrome,healthGridColumns,usageSummaryMarginBottom,overlaps,theme:document.documentElement.dataset.theme,
        heading:[...document.querySelectorAll('.page-title,.login-title')].filter(visible).map(el=>({text:el.textContent,size:getComputedStyle(el).fontSize}))};
}"""


def main(stage, strict, only):
    output = ROOT / "temp/design-consistency" / stage
    output.mkdir(parents=True, exist_ok=True)
    results, errors, menu_failures = [], [], []
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", reduced_motion="reduce")
        context.route("https://**", lambda route: route.abort())
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))

        def capture(target, name):
            if only and name not in only:
                return
            for width, height in SIZES:
                target.set_viewport_size({"width": width, "height": height})
                for theme in ("light", "dark"):
                    target.emulate_media(color_scheme=theme)
                    expect(target.locator("html")).to_have_attribute("data-theme", theme)
                    target.wait_for_timeout(250)
                    # Wait for resize/media-query rendering, not just the theme attribute.
                    target.evaluate("""async () => {
                        scrollTo(0,0);
                        await new Promise(requestAnimationFrame);
                        await new Promise(requestAnimationFrame);
                    }""")
                    if width in (360, 1440):
                        target.screenshot(
                            path=str(output / f"{name}-{width}-{theme}.png"), full_page=True
                        )
                    result = target.evaluate(AUDIT)
                    result.update(page=name, width=width, height=height, expectedTheme=theme)
                    results.append(result)
            print(f"Captured {name}: 12 combinations", flush=True)

        page.goto(base + "/setup", wait_until="networkidle")
        capture(page, "setup")
        page.locator("#setupPassword").fill(PASSWORD)
        page.locator("#setupPasswordConfirm").fill(PASSWORD)
        page.locator("#setupSubmitButton").click()
        expect(page).to_have_url(base + "/dashboard")
        for route in ROUTES:
            page.goto(base + "/" + route, wait_until="networkidle")
            capture(page, route.replace("?view=", "-"))
        page.goto(base + "/dashboard", wait_until="networkidle")
        for width, height in ((360, 800), (844, 390)):
            page.set_viewport_size({"width": width, "height": height})
            for theme in ("light", "dark"):
                page.emulate_media(color_scheme=theme)
                expect(page.locator("html")).to_have_attribute("data-theme", theme)
                page.wait_for_timeout(250)
                page.locator(".mobile-menu-btn").click()
                expect(page.locator(".dashboard-sidebar")).to_have_class("dashboard-sidebar open")
                if not page.locator("#mainContent").evaluate("el => el.inert"):
                    menu_failures.append(f"{width}/{theme}: background not inert")
                page.screenshot(path=str(output / f"sidebar-{width}-{theme}.png"))
                page.locator(".sidebar-footer button").focus()
                page.keyboard.press("Tab")
                if not page.evaluate(
                    "document.querySelector('.dashboard-sidebar').contains(document.activeElement)"
                ):
                    menu_failures.append(f"{width}/{theme}: Tab leaves open drawer")
                page.keyboard.press("Shift+Tab")
                if not page.locator(".sidebar-footer button").evaluate(
                    "el => el === document.activeElement"
                ):
                    menu_failures.append(f"{width}/{theme}: reverse Tab fails to wrap")
                page.keyboard.press("Escape")
                expect(page.locator(".mobile-menu-btn")).to_be_focused()
                assert not page.locator("#mainContent").evaluate("el => el.inert")
                # Navigation and desktop resize must release the modal drawer state.
                page.locator(".mobile-menu-btn").click()
                page.locator('.dashboard-sidebar [data-tab="providers"]').click()
                expect(page.locator("#providersTab")).to_be_visible()
                assert not page.locator("#mainContent").evaluate("el => el.inert")
                page.locator(".mobile-menu-btn").click()
                page.set_viewport_size({"width": 1440, "height": 900})
                expect(page.locator(".dashboard-sidebar")).not_to_have_attribute(
                    "aria-modal", "true"
                )
                assert not page.locator("#mainContent").evaluate("el => el.inert")
                page.set_viewport_size({"width": width, "height": height})
        guest = browser.new_context(locale="vi-VN", reduced_motion="reduce")
        guest.route("https://**", lambda route: route.abort())
        guest_page = guest.new_page()
        guest_page.on("pageerror", lambda error: errors.append(str(error)))
        for route in ("login", "callback"):
            guest_page.goto(base + "/" + route, wait_until="networkidle")
            capture(guest_page, route)
        browser.close()
    report = {"results": results, "errors": errors, "menuFailures": menu_failures}
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = {
        "cases": len(results),
        "overflow": sum(bool(r["overflow"]) for r in results),
        "contrast": sum(bool(r["contrast"]) for r in results),
        "names": sum(bool(r["missingNames"]) for r in results),
        "placeholder": sum(bool(r["placeholder"]) for r in results),
        "menuFailures": menu_failures,
        "errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=False))
    if strict:
        assert not errors and not menu_failures, summary
        assert all(
            not r["overflow"]
            and not r["missingNames"]
            and not r["placeholder"]
            and r["theme"] == r["expectedTheme"]
            for r in results
        ), summary
        assert all(not r["tiny"] for r in results if r["width"] <= 960), (
            "Undersized phone/tablet controls"
        )
        assert all(not r["contrast"] for r in results), "Text contrast below the measured threshold"
        assert all(not r["overlaps"] for r in results), (
            "Recent activity header overlaps its description"
        )
        assert all(
            r["healthIconChrome"]["background"] in ("rgba(0, 0, 0, 0)", "transparent")
            and r["healthIconChrome"]["borderWidth"] == "0px"
            for r in results
        ), "Provider health icons should not have a background or border"
        assert all(r["usageSummaryMarginBottom"] in (None, "0px") for r in results), (
            "Provider analysis should not reserve trailing bottom space"
        )
        assert all(r["width"] < 1200 or r["healthGridColumns"] >= 3 for r in results), (
            "Provider health matrix should use at least three columns on wide screens"
        )
        assert all(
            all(
                logo["filter"] == ("invert(1)" if r["theme"] == "dark" else "none")
                for logo in r["logo"]
            )
            for r in results
        ), "Brand theme mismatch"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", default="before")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--only",
        action="append",
        choices=("setup", "login", "callback", *(route.replace("?view=", "-") for route in ROUTES)),
        help="Recheck a failed surface without repeating the complete visual matrix.",
    )
    args = parser.parse_args()
    main(args.stage, args.strict, args.only)
