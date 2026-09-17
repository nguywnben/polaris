"""Production self-hosted navigation and Activity workspace contracts."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.panel.root import router, serve_control_panel

ROOT = BACKEND_DIR.parent
FRONTEND = ROOT / "frontend"


class NavigationConsoleContractTests(unittest.TestCase):
    def _run_javascript_contract(self, source: str) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for the navigation behavior contract.")
        result = subprocess.run(
            [node],
            cwd=ROOT,
            capture_output=True,
            encoding="utf-8",
            input=source,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_primary_navigation_follows_configuration_testing_access_and_operations(self) -> None:
        body = serve_control_panel().body.decode("utf-8")
        sidebar = (FRONTEND / "fragments/layout/sidebar.html").read_text(encoding="utf-8")
        tabs = re.findall(r'data-ui-action="switch-tab" data-tab="([^"]+)"', sidebar)

        self.assertEqual(
            tabs,
            [
                "dashboard",
                "providers",
                "credentials",
                "models",
                "quality",
                "playground",
                "access",
                "identity",
                "activity",
                "config",
                "about",
            ],
        )
        for key in (
            "navigation.overview",
            "navigation.credentials",
            "navigation.models_routing",
            "navigation.activity",
            "navigation.identity",
        ):
            self.assertIn(f'data-i18n="{key}"', sidebar)
        self.assertNotIn('id="advancedNavigation"', sidebar)
        self.assertNotIn("<details", sidebar)
        self.assertNotRegex(
            sidebar,
            r'<button[^>]+data-tab="identity"[^>]*\bhidden\b',
        )
        self.assertIn('href="#mainContent"', body)
        self.assertIn('id="mainContent"', body)

    def test_secondary_pages_are_top_level_sidebar_items(self) -> None:
        sidebar = (FRONTEND / "fragments/layout/sidebar.html").read_text(encoding="utf-8")
        shell = (FRONTEND / "css/shell.css").read_text(encoding="utf-8")
        responsive = (FRONTEND / "css/responsive.css").read_text(encoding="utf-8")

        self.assertRegex(sidebar, r'<button[^>]+data-tab="identity"[^>]*>')
        self.assertRegex(sidebar, r'<button[^>]+data-tab="about"[^>]*>')
        self.assertNotIn("sidebar-navigation-group", sidebar)
        self.assertNotIn(".sidebar-navigation-group", shell)
        self.assertNotIn(".sidebar-navigation-group", responsive)

    def test_activity_is_one_home_with_three_accessible_views(self) -> None:
        body = serve_control_panel().body.decode("utf-8")
        navigation = (FRONTEND / "js/core/navigation.js").read_text(encoding="utf-8")
        activity = (FRONTEND / "js/features/activity.js").read_text(encoding="utf-8")
        root_source = (BACKEND_DIR / "core/panel/root.py").read_text(encoding="utf-8")

        self.assertIn('id="activityTab"', body)
        self.assertIn('role="tablist"', body)
        for view in ("traces", "audit", "runtime"):
            self.assertIn(f'data-activity-view="{view}"', body)
            self.assertIn(f'data-activity-panel="{view}"', body)
        self.assertNotIn('id="auditTab" class="tab-content"', body)
        self.assertNotIn('id="logsTab" class="tab-content"', body)
        self.assertIn("'/activity': 'activity'", navigation)
        self.assertIn("'/audit': 'audit'", navigation)
        self.assertIn("'/logs': 'logs'", navigation)
        self.assertIn("['audit', 'logs'].includes(routeTabName) ? 'activity'", navigation)
        self.assertIn("activity: '/activity'", navigation)
        self.assertIn("function setActivityView", activity)
        self.assertIn("function activityViewFromLocation", activity)
        self.assertIn("ArrowLeft", activity)
        self.assertIn("ArrowRight", activity)
        self.assertIn('@router.get("/activity"', root_source)

        console_routes = {route.path: route.endpoint for route in router.routes}
        for path in ("/activity", "/audit", "/logs"):
            self.assertIs(console_routes[path], serve_control_panel)

    def test_activity_view_and_fixed_identity_navigation_behave_in_the_dom(self) -> None:
        activity = (FRONTEND / "js/features/activity.js").read_text(encoding="utf-8")
        conditional = (FRONTEND / "js/features/conditional-navigation.js").read_text(
            encoding="utf-8"
        )
        harness = f"""
class TestElement {{
    constructor() {{ this.attributes = {{}}; this.hidden = false; this.tabIndex = 0; }}
    addEventListener() {{}}
    focus() {{ this.focused = true; }}
    setAttribute(name, value) {{ this.attributes[name] = value; }}
}}
const elements = new Map();
for (const id of [
    'activityTracesTab', 'activityAuditTab', 'activityRuntimeTab',
    'activityTracesPanel', 'activityAuditPanel', 'activityRuntimePanel'
]) elements.set(id, new TestElement());
const teamAccess = new TestElement();
global.document = {{
    addEventListener() {{}},
    getElementById(id) {{ return elements.get(id) || null; }},
    querySelector(selector) {{
        return selector === '[data-tab="identity"]' || selector === '[data-conditional-navigation="team-access"]' ? teamAccess : null;
    }}
}};
global.window = {{ location: {{pathname: '/activity', search: ''}} }};
global.history = {{ pushState() {{}} }};
global.AppState = {{authenticated: true, activeActivityView: 'traces', teamAccessEnabled: null}};
global.triggerTabDataLoad = (name) => name;
global.identityValidateOidcPolicy = (payload) => payload;
global.identityApi = async () => ({{enabled: false}});
{activity}
{conditional}
function assert(condition, message) {{ if (!condition) throw new Error(message); }}
(async () => {{
    setActivityView('audit', {{load: false}});
    assert(elements.get('activityAuditTab').attributes['aria-selected'] === 'true', 'audit tab not selected');
    assert(elements.get('activityAuditPanel').hidden === false, 'audit panel hidden');
    assert(elements.get('activityTracesPanel').hidden === true, 'traces panel visible');
    assert(activityViewFromLocation('/audit', '') === 'audit', 'audit URL alias failed');
    assert(activityViewFromLocation('/logs', '') === 'runtime', 'logs URL alias failed');
    await refreshTeamAccessNavigation();
    assert(teamAccess.hidden === false, 'identity must remain visible when OIDC is disabled');
    identityApi = async () => {{throw new Error('unavailable');}};
    await refreshTeamAccessNavigation();
    assert(teamAccess.hidden === false, 'identity must remain visible when policy loading fails');
    assert(AppState.teamAccessEnabled === null, 'failed policy must not enable OIDC');
    resetConditionalNavigation();
    assert(teamAccess.hidden === false, 'reset must not hide identity');
    identityApi = async () => ({{enabled: true}});
    await refreshTeamAccessNavigation();
    assert(teamAccess.hidden === false, 'enabled Team access must be visible');
    AppState.teamAccessEnabled = null;
    window.location.pathname = '/identity';
    updateTeamAccessNavigation();
    assert(teamAccess.hidden === false, 'direct Team access configuration must remain discoverable');
}})().catch((error) => {{ console.error(error); process.exitCode = 1; }});
"""
        self._run_javascript_contract(harness)

    def test_team_access_policy_remains_fail_closed_without_hiding_navigation(self) -> None:
        conditional = (FRONTEND / "js/features/conditional-navigation.js").read_text(
            encoding="utf-8"
        )
        state = (FRONTEND / "js/core/state.js").read_text(encoding="utf-8")

        self.assertIn("teamAccessEnabled: null", state)
        self.assertIn("policy?.enabled === true", conditional)
        self.assertIn("teamAccessTab.hidden = false", conditional)
        self.assertIn("catch", conditional)
        self.assertIn("teamAccessEnabled = null", conditional)
        self.assertIn("refreshTeamAccessNavigation", conditional)

    def test_mobile_drawer_and_page_navigation_have_explicit_focus_management(self) -> None:
        mobile = (FRONTEND / "js/features/mobile-navigation.js").read_text(encoding="utf-8")
        navigation = (FRONTEND / "js/core/navigation.js").read_text(encoding="utf-8")

        self.assertIn("sidebar.inert", mobile)
        self.assertIn("open && !wasOpen", mobile)
        self.assertIn("restoreFocus && wasOpen", mobile)
        self.assertIn("restoreFocus", mobile)
        self.assertIn("event.key === 'Escape'", mobile)
        self.assertIn("focusActivePage", navigation)
        self.assertIn("heading.focus", navigation)

    def test_tab_navigation_yields_a_paint_before_running_heavy_loaders(self) -> None:
        navigation = (FRONTEND / "js/core/navigation.js").read_text(encoding="utf-8")

        self.assertIn("requestAnimationFrame", navigation)
        self.assertIn("setTimeout(start, 0)", navigation)
        self.assertIn("AppState.tabLoadPromises[tabName] = loadPromise", navigation)

    def test_mobile_drawer_preserves_the_original_return_focus_across_resize_sync(self) -> None:
        mobile = (FRONTEND / "js/features/mobile-navigation.js").read_text(encoding="utf-8")
        harness = f"""
class TestClassList {{
    constructor() {{ this.names = new Set(); }}
    contains(name) {{ return this.names.has(name); }}
    toggle(name, force) {{ force ? this.names.add(name) : this.names.delete(name); }}
}}
class TestElement {{
    constructor() {{ this.classList = new TestClassList(); this.style = {{}}; this.attributes = {{}}; }}
    focus() {{ document.activeElement = this; }}
    setAttribute(name, value) {{ this.attributes[name] = value; }}
    removeAttribute(name) {{ delete this.attributes[name]; }}
}}
const sidebar = new TestElement();
const overlay = new TestElement();
const menuButton = new TestElement();
const activeTab = new TestElement();
sidebar.querySelector = () => activeTab;
global.document = {{
    activeElement: menuButton,
    body: new TestElement(),
    addEventListener() {{}},
    querySelector(selector) {{
        if (selector === '.dashboard-sidebar') return sidebar;
        if (selector === '.sidebar-overlay') return overlay;
        if (selector === '.mobile-menu-btn') return menuButton;
        return null;
    }},
    getElementById() {{ return new TestElement(); }}
}};
global.window = {{innerWidth: 360, requestAnimationFrame(callback) {{ callback(); }}}};
global.t = (key) => key;
{mobile}
function assert(condition, message) {{ if (!condition) throw new Error(message); }}
setMobileMenuState(true);
assert(document.activeElement === activeTab, 'drawer did not move focus inside');
syncMobileNavigationState();
setMobileMenuState(false, {{restoreFocus: true}});
assert(document.activeElement === menuButton, 'resize sync replaced the original return target');
assert(sidebar.inert === true, 'closed drawer remained interactive');
"""
        self._run_javascript_contract(harness)

    def test_all_settings_groups_are_visible_without_disclosure_controls(
        self,
    ) -> None:
        settings = (FRONTEND / "fragments/pages/settings.html").read_text(encoding="utf-8")

        self.assertEqual(settings.count('data-settings-tier="advanced"'), 1)
        self.assertEqual(settings.count('data-settings-tier="compatibility"'), 1)
        self.assertNotIn('id="codeAssistEndpoint"', settings)
        self.assertIn('id="keepaliveUrl"', settings)
        self.assertNotIn("<details", settings)
        self.assertNotIn("<summary", settings)
        self.assertNotIn("config-advanced-summary", settings)


if __name__ == "__main__":
    unittest.main()
