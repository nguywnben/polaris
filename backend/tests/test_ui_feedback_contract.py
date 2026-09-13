"""Shared console feedback and accessibility contracts for PROD-SELFHOST-R1 P3.2."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.panel.root import _console_asset_version, serve_control_panel

ROOT = BACKEND_DIR.parent
FRONTEND = ROOT / "frontend"


class _AccessibilitySmokeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.headings: set[str] = set()
        self.state_hosts: set[str] = set()
        self.unscoped_headers = 0
        self.unlabelled_pagination = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if tag == "h1" and element_id:
            self.headings.add(element_id)
        if "data-page-state-host" in values and element_id:
            self.state_hosts.add(element_id)
        if tag == "th" and values.get("scope") != "col":
            self.unscoped_headers += 1
        if "pagination-container" in (values.get("class") or "").split():
            labelled = values.get("aria-label") or values.get("aria-labelledby")
            if values.get("role") != "navigation" or not labelled:
                self.unlabelled_pagination += 1


class UiFeedbackContractTests(unittest.TestCase):
    def _run_javascript_contract(self, source: str) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for the UI behavior contract.")
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

    def test_shared_page_state_component_has_safe_dom_and_retry_behavior(self) -> None:
        source = (FRONTEND / "js/ui/page-states.js").read_text(encoding="utf-8")
        harness = f"""
class TestElement {{
    constructor(tag = 'div') {{
        this.tagName = tag.toUpperCase(); this.children = []; this.attributes = {{}};
        this.className = ''; this.hidden = false; this.textContent = ''; this.listeners = {{}};
    }}
    append(...children) {{ this.children.push(...children); for (const child of children) child.parentElement = this; }}
    replaceChildren(...children) {{ this.children = []; this.append(...children); }}
    setAttribute(name, value) {{ this.attributes[name] = String(value); }}
    removeAttribute(name) {{ delete this.attributes[name]; }}
    addEventListener(name, callback) {{ this.listeners[name] = callback; }}
    click() {{ this.listeners.click?.({{currentTarget: this}}); }}
}}
const host = new TestElement();
global.document = {{
    createElement(tag) {{ return new TestElement(tag); }},
    getElementById(id) {{ return id === 'stateHost' ? host : null; }}
}};
{source}
function assert(condition, message) {{ if (!condition) throw new Error(message); }}
let retried = false;
showPageState('stateHost', {{kind: 'error', title: 'Unavailable', message: '<unsafe>', actionLabel: 'Retry', onAction() {{ retried = true; }}}});
const state = host.children[0];
assert(host.hidden === false, 'state host stayed hidden');
assert(state.attributes.role === 'alert', 'error state is not assertive');
assert(state.children[1].textContent === '<unsafe>', 'message was not rendered as text');
state.children[2].click();
assert(retried, 'retry action was not invoked');
clearPageState(host);
assert(host.hidden === true && host.children.length === 0, 'state did not clear');
"""
        self._run_javascript_contract(harness)

    def test_bundle_version_changes_when_the_asset_manifest_changes(self) -> None:
        class Asset:
            def __init__(self, name: str) -> None:
                self.name = name

            def __str__(self) -> str:
                return self.name

            def stat(self) -> SimpleNamespace:
                return SimpleNamespace(st_mtime_ns=1_700_000_000_000_000_000, st_size=5)

        first = Asset("first.js")
        second = Asset("second.js")
        with patch("core.panel.root._console_asset_paths", return_value=(first,)):
            first_version = _console_asset_version()
        with patch("core.panel.root._console_asset_paths", return_value=(first, second)):
            second_version = _console_asset_version()
        self.assertNotEqual(first_version, second_version)

    def test_core_pages_and_data_components_have_accessible_feedback_contracts(self) -> None:
        body = serve_control_panel().body.decode("utf-8")
        parser = _AccessibilitySmokeParser()
        parser.feed(body)

        self.assertEqual(parser.unscoped_headers, 0)
        self.assertEqual(parser.unlabelled_pagination, 0)
        self.assertTrue(
            {
                "dashboardUsageState",
                "virtualKeyState",
                "modelCatalogState",
                "qualityState",
                "configState",
                "primaryCredsState",
            }
            <= parser.state_hosts
        )

        root_source = (BACKEND_DIR / "core/panel/root.py").read_text(encoding="utf-8")
        self.assertIn('"js/ui/page-states.js"', root_source)

    def test_blank_risk_loaders_render_error_or_stale_state_with_retry(self) -> None:
        contracts = {
            "js/features/dashboard.js": "dashboardUsageState",
            "js/features/virtual-keys.js": "virtualKeyState",
            "js/features/model-pool.js": "modelCatalogState",
            "js/features/quality-policy.js": "qualityState",
            "js/features/system-settings.js": "configState",
            "js/core/credential-manager.js": "CredsState",
        }
        for relative_path, state_host in contracts.items():
            with self.subTest(path=relative_path):
                source = (FRONTEND / relative_path).read_text(encoding="utf-8")
                self.assertIn("showPageState", source)
                self.assertIn("clearPageState", source)
                self.assertIn(state_host, source)
                self.assertRegex(source, r"kind:\s*preserveContent\s*\?\s*'stale'\s*:\s*'error'")

    def test_toasts_and_modals_expose_feedback_and_focus_management(self) -> None:
        notifications = (FRONTEND / "js/ui/notifications.js").read_text(encoding="utf-8")
        dialogs = (FRONTEND / "js/ui/dialogs.js").read_text(encoding="utf-8")

        self.assertIn("aria-live", notifications)
        self.assertIn("aria-atomic", notifications)
        self.assertIn("statusType === 'error' ? 'alert' : 'status'", notifications)
        self.assertIn("modalReturnFocus", notifications)
        self.assertIn("getModalFocusableElements", notifications)
        self.assertIn("event.key !== 'Tab'", notifications)
        self.assertIn("returnTarget.focus", notifications)
        self.assertIn("showConfirmModal", dialogs)

    def test_feedback_never_uses_browser_native_dialogs_and_honors_reduced_motion(self) -> None:
        native_dialog = re.compile(r"(?<![\w.])(alert|confirm|prompt)\s*\(")
        for path in (FRONTEND / "js").rglob("*.js"):
            with self.subTest(path=path.relative_to(FRONTEND)):
                self.assertIsNone(native_dialog.search(path.read_text(encoding="utf-8")))

        styles = "\n".join(
            path.read_text(encoding="utf-8") for path in (FRONTEND / "css").glob("*.css")
        )
        reduced_motion = re.search(
            r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(?P<body>.*?)\n\}",
            styles,
            re.DOTALL,
        )
        self.assertIsNotNone(reduced_motion)
        self.assertIn("transition-duration", reduced_motion.group("body"))
        self.assertIn("scroll-behavior", reduced_motion.group("body"))

    def test_console_layout_uses_compact_badges_and_never_creates_horizontal_scrollers(
        self,
    ) -> None:
        styles = "\n".join(
            path.read_text(encoding="utf-8") for path in (FRONTEND / "css").glob("*.css")
        )

        self.assertNotRegex(styles, r"overflow-x:\s*auto")
        badge_rule = re.search(r"\.status-badge\s*\{(?P<body>.*?)\}", styles, re.DOTALL)
        self.assertIsNotNone(badge_rule)
        self.assertIn("width: fit-content", badge_rule.group("body"))
        self.assertIn("max-width: 100%", badge_rule.group("body"))

    def test_wrapping_form_labels_keep_visible_space_before_controls(self) -> None:
        styles = (FRONTEND / "css/forms-and-data.css").read_text(encoding="utf-8")

        self.assertIn("label.form-group > span:first-child", styles)
        self.assertRegex(
            styles,
            r"label\.form-group\s*>\s*span:first-child\s*\{[^}]*margin-bottom:\s*8px",
        )

    def test_select_controls_balance_text_and_chevron_spacing(self) -> None:
        foundation = (FRONTEND / "css/foundation.css").read_text(encoding="utf-8")
        styles = (FRONTEND / "css/forms-and-data.css").read_text(encoding="utf-8")

        self.assertIn("--select-chevron:", foundation)
        select_rule = re.search(r"select\s*\{(?P<body>.*?)\}", styles, re.DOTALL)
        self.assertIsNotNone(select_rule)
        body = select_rule.group("body")
        self.assertIn("appearance: none", body)
        self.assertIn("background-position: right 13px center", body)
        self.assertIn("background-size: 12px 8px", body)
        self.assertIn("padding: 8px 38px 8px 13px", body)

    def test_form_controls_share_complete_interaction_states(self) -> None:
        foundation = (FRONTEND / "css/foundation.css").read_text(encoding="utf-8")
        styles = (FRONTEND / "css/forms-and-data.css").read_text(encoding="utf-8")

        for token in ("--field-focus-border: var(--accent);", "--select-chevron-open:"):
            self.assertIn(token, foundation)
        self.assertNotIn("--field-focus-ring:", foundation)
        self.assertNotIn("--field-invalid-ring:", foundation)

        for selector in (
            "input:not([type])",
            'input[type="datetime-local"]',
            "select:open",
            ":user-invalid",
            ":focus-visible",
        ):
            self.assertIn(selector, styles)

        self.assertIn("background-image: var(--select-chevron-open)", styles)
        self.assertNotIn("box-shadow: 0 0 0 3px var(--field-focus-ring)", styles)
        self.assertNotIn("box-shadow: 0 0 0 3px var(--field-invalid-ring)", styles)
        self.assertRegex(
            styles,
            r"\):focus\s*\{[^}]*border-color:\s*var\(--field-focus-border\);[^}]*box-shadow:\s*none;",
        )
        self.assertRegex(
            styles,
            r"select:open\s*\{[^}]*border-color:\s*var\(--field-focus-border\);[^}]*box-shadow:\s*none;",
        )
        self.assertNotIn("input:focus,\nselect:focus,\ntextarea:focus", styles)

    def test_page_styles_do_not_override_shared_field_focus_state(self) -> None:
        page_styles = "\n".join(
            (FRONTEND / path).read_text(encoding="utf-8")
            for path in (
                "css/identity.css",
                "css/audit.css",
                "css/observability.css",
            )
        )

        for broad_override in (
            ".identity-panel :focus-visible",
            ".identity-dialog :focus-visible",
            ".audit-filter-grid :focus-visible",
            ".audit-retention :focus-visible",
            ".activity-filter-panel :focus-visible",
            ".trace-filter-grid :focus-visible",
            ".trace-retention :focus-visible",
            ".recent-activity-card :focus-visible",
        ):
            self.assertNotIn(broad_override, page_styles)

    def test_pages_do_not_use_standalone_advisory_panels(self) -> None:
        fragments = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (FRONTEND / "fragments/pages").glob("*.html")
        )

        self.assertNotIn('class="config-note', fragments)
        self.assertNotIn("playground-privacy-note", fragments)
        self.assertNotIn("trace-privacy-note", fragments)
        self.assertNotIn("model-policy-note", fragments)
        self.assertNotIn("quality-safety-note", fragments)


if __name__ == "__main__":
    unittest.main()
