"""Credential result copy must come from structured state, never server prose."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ProviderSaveResultTests(unittest.TestCase):
    def test_localized_copy_and_honest_model_counts(self):
        script = """
const fs = require('fs'), vm = require('vm');
const context = {
  document: {addEventListener() {}},
  t: (key, vars = {}) => `${key}:${JSON.stringify(vars)}`,
  formatConsoleNumber: value => String(value)
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/features/provider-save-results.js', 'utf8'), context);
const samples = [
  {message: 'ENGLISH SECRET', model_count: 41},
  {credential_action: 'updated', model_count: 0},
  {credential_action: 'replaced'},
  {credential_action: 'skipped', credential_saved: false, file_path: 'fixture.json'},
  {model_count: null}, {model_count: -1}, {model_count: 'not-a-number'}
];
console.log(JSON.stringify(samples.map(context.providerCredentialResultCopy)));
"""
        result = subprocess.run(
            [shutil.which("node") or "node", "-e", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        copies = json.loads(result.stdout)
        self.assertNotIn("ENGLISH SECRET", result.stdout)
        self.assertIn('"count":"41"', copies[0]["body"])
        self.assertIn("credential_updated_title", copies[1]["title"])
        self.assertIn('"count":"0"', copies[1]["body"])
        self.assertIn("credential_replaced_title", copies[2]["title"])
        self.assertEqual(copies[3]["variant"], "info")
        self.assertIn("credential_skipped_body", copies[3]["body"])
        for copy in copies[2:]:
            self.assertNotIn("models_available", copy["body"])
