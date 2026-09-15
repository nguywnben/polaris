"""DOM and runtime contracts for Antigravity credit ownership."""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "frontend/js/features/provider-credit-settings.js"
CARDS = ROOT / "frontend/js/ui/credential-cards.js"
PROVIDERS = ROOT / "frontend/fragments/pages/providers.html"
ROOT_ROUTE = ROOT / "backend/core/panel/root.py"
HARNESS = ROOT / "backend/tests/provider_credit_settings_contract.cjs"


class ProviderCreditSettingsFrontendTests(unittest.TestCase):
    def test_credit_controls_belong_to_antigravity_workspace_not_pool_cards(self):
        html = PROVIDERS.read_text(encoding="utf-8")
        cards = CARDS.read_text(encoding="utf-8")

        credit_position = html.index('id="antigravityCreditSettings"')
        advanced_position = html.index('class="tool-panel provider-advanced-panel"', credit_position)
        self.assertLess(credit_position, advanced_position)
        self.assertNotIn('data-credential-command="enable_credit"', cards)
        self.assertNotIn('data-credential-command="disable_credit"', cards)

    def test_credit_script_is_bundled_after_dialog_dependencies(self):
        root = ROOT_ROUTE.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")

        self.assertIn('"js/features/provider-credit-settings.js"', root)
        self.assertLess(
            root.index('"js/ui/dialogs.js"'),
            root.index('"js/features/provider-credit-settings.js"'),
        )
        self.assertNotIn("createCredsManager", source)
        self.assertNotIn("AppState.primaryCreds", source)

    def test_credit_runtime_uses_bounded_provider_summary_page_and_preserves_error_state(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for the provider credit DOM contract.")

        result = subprocess.run(
            [node, str(HARNESS), str(SOURCE)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
