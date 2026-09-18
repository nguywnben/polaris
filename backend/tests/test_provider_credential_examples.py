"""Downloaded credential examples match the offline import contract."""

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.pool_import import _parse_archive_payload, classify_pool_credential
from core.provider_registry import EXTENDED_PROVIDERS, normalize_provider_id

LEGACY = [
    "google_antigravity",
    "google_ai_studio",
    "grok",
    "xai_console",
    "codex",
    "openai_platform",
    "claude_code",
    "claude_platform",
    "ollama",
]


class ProviderCredentialExampleTests(unittest.TestCase):
    def test_all_examples_are_offline_importable_and_independent_of_form_secrets(self):
        providers = LEGACY + list(EXTENDED_PROVIDERS)
        script = """
const fs = require('fs'), vm = require('vm');
const ids = JSON.parse(process.argv[1]);
const context = {
    EXTENDED_PROVIDER_UI: Object.fromEntries(ids.slice(9).map(id => [id, {}])),
    document: new Proxy({}, {get() {throw new Error('must not read form secrets');}})
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/features/provider-credential-examples.js', 'utf8'), context);
const examples = Object.fromEntries(ids.map(id => [id, context.providerCredentialExample(id)]));
const altered = context.providerCredentialExample('codex'); altered.refresh_token = 'FORM_SECRET';
if (JSON.stringify(context.providerCredentialExample('codex')).includes('FORM_SECRET')) throw Error('shared mutable state');
let rejected = false; try { context.providerCredentialExample('unknown'); } catch { rejected = true; }
if (!rejected) throw Error('unknown provider accepted');
console.log(JSON.stringify(examples));
"""
        result = subprocess.run(
            [shutil.which("node") or "node", "-e", script, json.dumps(providers)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        examples = json.loads(result.stdout)
        self.assertEqual(len(examples), 23)
        for provider, sample in examples.items():
            with self.subTest(provider=provider):
                self.assertEqual(sample["provider"], provider)
                # Fill illustrative fields with synthetic values, never real credentials.
                filled = {
                    key: ("a" * 32 if key == "account_id" else "fixture-value")
                    if isinstance(value, str) and value.startswith("<YOUR_")
                    else value
                    for key, value in sample.items()
                }
                if provider == "muse_code":
                    filled["user_email"] = "fixture@example.test"
                payload = _parse_archive_payload(
                    json.dumps(filled).encode(), "sample.json", variant=provider
                )
                self.assertEqual(classify_pool_credential(payload), normalize_provider_id(provider))
                if provider in {"google_antigravity", "codex", "grok", "claude_code", "kiro"}:
                    self.assertNotIn("api_key", sample)
                    self.assertEqual(sample["refresh_token"], "<YOUR_REFRESH_TOKEN>")
                elif provider == "muse_code":
                    self.assertEqual(sample["credential_type"], "oauth")
                    self.assertNotIn("api_key", sample)
                    self.assertNotIn("refresh_token", sample)
                elif provider == "ollama":
                    self.assertEqual(sample["credential_type"], "connection")
                    self.assertNotIn("api_key", sample)
                else:
                    self.assertEqual(sample["api_key"], "<YOUR_API_KEY>")
