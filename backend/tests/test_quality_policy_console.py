"""Browser-side AI Quality completion contracts for P4.1."""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "frontend/js/features/quality-policy.js"
FRAGMENT = ROOT / "frontend/fragments/pages/ai-quality.html"
STYLES = ROOT / "frontend/css/quality-policy.css"


class QualityPolicyConsoleTests(unittest.TestCase):
    def _run_contract(self, assertions: str) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required for the AI Quality DOM contract.")
        harness = f"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync({json.dumps(str(SCRIPT))}, 'utf8');
vm.runInThisContext(source + `\n;globalThis.__qualityContract = {{deriveQualityWarnings, deriveQualityTransformationSummary}};`);
const {{deriveQualityWarnings: warnings, deriveQualityTransformationSummary: summary}} = globalThis.__qualityContract;
function assert(condition, message) {{ if (!condition) throw new Error(message); }}
{assertions}
"""
        result = subprocess.run(
            [node, "-e", harness],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_policy_page_explains_live_precedence_and_unambiguous_disable(self) -> None:
        fragment = FRAGMENT.read_text(encoding="utf-8")

        for element_id in (
            "qualityApplicationMode",
            "qualityPrecedence",
            "qualityTransformationSummary",
            "qualityPolicyWarnings",
            "qualityCompressionOffMeaning",
        ):
            self.assertIn(f'id="{element_id}"', fragment)
        self.assertIn('data-i18n="quality.apply_live_copy"', fragment)
        self.assertIn('data-i18n="quality.precedence_copy"', fragment)
        self.assertIn('data-i18n="quality.compression_off_copy"', fragment)

    def test_draft_summary_predicts_when_compression_transforms_history(self) -> None:
        self._run_contract(
            """
const disabled = summary({compression: {enabled: false, threshold_tokens: 32000, target_tokens: 24000}});
assert(disabled.code === 'compression_disabled' && disabled.willTransform === false, 'disabled summary');
const enabled = summary({compression: {enabled: true, threshold_tokens: 32000, target_tokens: 24000}});
assert(enabled.code === 'compression_above_threshold' && enabled.threshold === 32000, 'enabled summary');
assert(enabled.target === 24000 && enabled.willTransform === null, 'conditional transform summary');
"""
        )

    def test_specific_warnings_cover_risky_custom_combinations(self) -> None:
        self._run_contract(
            """
const result = warnings({
    compatibility_mode: true,
    return_reasoning: true,
    anti_truncation_max_attempts: 7,
    compression: {enabled: true, threshold_tokens: 8000, target_tokens: 4000, min_recent_turns: 1},
    guardrails: {enabled: true, pii_masking_enabled: false, injection_detection_enabled: false, blocked_keywords: []},
    response_cache: {enabled: true, ttl_seconds: 7200, max_entries: 1000}
});
for (const code of [
    'compatibility_changes_instruction_shape', 'low_recent_turn_retention',
    'guardrails_without_checks', 'cache_with_reasoning', 'high_recovery_attempts'
]) assert(result.includes(code), `missing warning: ${code}`);
assert(warnings({
    compatibility_mode: false,
    return_reasoning: true,
    anti_truncation_max_attempts: 3,
    compression: {enabled: true, threshold_tokens: 32000, target_tokens: 24000, min_recent_turns: 4},
    guardrails: {enabled: false, pii_masking_enabled: true, injection_detection_enabled: true, blocked_keywords: []},
    response_cache: {enabled: false, ttl_seconds: 300, max_entries: 1000}
}).length === 0, 'balanced policy should have no risk warning');
"""
        )

    def test_revision_conflict_reloads_latest_policy_instead_of_overwriting_it(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("if (response.status === 409) await loadQualityPolicy", source)
        self.assertIn("preserveContent: true", source)
        self.assertIn("quality_policy_revision_conflict: 'quality.error_conflict'", source)

    def test_responsive_policy_sections_collapse_without_horizontal_scrolling(self) -> None:
        styles = STYLES.read_text(encoding="utf-8")

        self.assertIn(".quality-explanation-grid", styles)
        self.assertRegex(
            styles,
            r"(?s)@media \(max-width: 700px\).*?\.quality-explanation-grid.*?grid-template-columns: 1fr",
        )

    def test_profile_cards_use_neutral_selection_and_hover_only_when_unselected(self) -> None:
        styles = STYLES.read_text(encoding="utf-8")

        self.assertNotIn(".quality-profile-card:hover", styles)
        self.assertRegex(
            styles,
            r"(?s)\.quality-profile-card:not\(\.selected\):hover\s*\{"
            r".*?background:\s*var\(--control-hover\)"
            r".*?border-color:\s*var\(--control-hover-border\)",
        )
        self.assertRegex(
            styles,
            r"(?s)\.quality-profile-card\.selected\s*\{"
            r".*?background:\s*var\(--bg-subtle\)"
            r".*?border-color:\s*var\(--text\)"
            r".*?box-shadow:\s*none",
        )

    def test_quality_controls_have_clear_precedence_and_consistent_spacing(self) -> None:
        styles = STYLES.read_text(encoding="utf-8")

        self.assertRegex(
            styles,
            r"(?s)\.quality-precedence-list\s*\{"
            r".*?grid-template-columns:\s*1fr"
            r".*?list-style-position:\s*outside",
        )
        self.assertRegex(
            styles,
            r"(?s)\.quality-precedence-list li\s*\{.*?color:\s*var\(--text\)",
        )
        self.assertRegex(
            styles,
            r"(?s)\.quality-policy-grid > \.config-group > \.switch-row \+ \.form-group\s*\{"
            r".*?margin-top:\s*16px",
        )
        self.assertRegex(
            styles,
            r"(?s)\.quality-dependent-controls \.switch-row\s*\{"
            r".*?margin-top:\s*0",
        )

    def test_switch_copy_preserves_title_and_description_typography(self) -> None:
        styles = STYLES.read_text(encoding="utf-8")

        self.assertRegex(
            styles,
            r"(?s)\.quality-policy-grid \.switch-row strong\s*\{"
            r".*?font-weight:\s*680",
        )
        self.assertRegex(
            styles,
            r"(?s)\.quality-policy-grid \.switch-row small\s*\{"
            r".*?font-weight:\s*400",
        )


if __name__ == "__main__":
    unittest.main()
