"""Secret-free OIDC entry readiness and explicit browser navigation contracts."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from starlette.requests import Request

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.panel.auth import setup_status


class OidcEntryReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_status_projects_only_boolean_and_never_discovers_provider(self):
        valid = {
            "OIDC_ENABLED": "true",
            "OIDC_ISSUER": "https://identity.example.com",
            "OIDC_CLIENT_ID": "console-test-client",
            "OIDC_CLIENT_SECRET": "test-only-credential-not-real",
            "OIDC_REDIRECT_URI": "https://console.example.com/api/identity/oidc/callback",
        }
        cases = [
            ({}, False, False),
            ({"OIDC_ENABLED": "false"}, False, False),
            (valid, False, True),
            (valid, True, False),
            ({**valid, "OIDC_ISSUER": "http://unsafe.example.com"}, False, False),
            ({**valid, "OIDC_CLIENT_SECRET": ""}, False, False),
            ({**valid, "OIDC_ENABLED": "invalid"}, False, False),
        ]
        request = Request({"type": "http", "headers": []})
        for environment, setup_required, expected in cases:
            with self.subTest(environment=environment, setup_required=setup_required):
                base = {"setup_required": setup_required, "authenticated": False}
                with (
                    patch.dict("os.environ", environment, clear=True),
                    patch(
                        "core.panel.auth.config.has_password_configured",
                        new=AsyncMock(return_value=not setup_required),
                    ),
                    patch("core.panel.auth.build_setup_status", new=AsyncMock(return_value=base)),
                    patch("core.panel.auth.get_storage_adapter", new=AsyncMock()),
                    patch("socket.getaddrinfo", side_effect=AssertionError("No discovery")),
                ):
                    response = await setup_status(request)
                self.assertEqual(
                    json.loads(response.body),
                    {
                        "setup_required": setup_required,
                        "authenticated": False,
                        "oidc_enabled": expected,
                    },
                )


class OidcEntryDomTests(unittest.TestCase):
    def test_guidance_and_all_fifteen_locale_catalogs_are_complete(self):
        fragment = (ROOT / "frontend/fragments/pages/identity.html").read_text(encoding="utf-8")
        self.assertIn("docs/oidc-foundation.md", fragment)
        self.assertNotIn('href="/login"', fragment)  # Authenticated navigation redirects it.
        self.assertNotRegex(fragment, r"<(?:input|select|textarea)\b[^>]*\bautofocus")
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for locale validation")
        harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const locales = ['en', 'zh-CN', 'zh-TW', 'de', 'es', 'fr', 'id', 'it',
    'ja', 'ko', 'pt', 'ru', 'th', 'tr', 'vi'];
const context = {
    PAGE_LOCALE_TRANSLATIONS: Object.fromEntries(locales.map(locale => [locale, {}])),
    MESSAGE_CATALOGS: Object.fromEntries(locales.map(locale => [locale, {}])),
    ENGLISH_SEMANTIC_KEYS_BY_MESSAGE: new Map()
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const english = context.MESSAGE_CATALOGS.en;
assert.equal(Object.keys(english).length, 6);
for (const locale of locales) {
    const catalog = context.MESSAGE_CATALOGS[locale];
    assert.deepEqual(Object.keys(catalog), Object.keys(english));
    for (const [key, value] of Object.entries(catalog)) {
        assert.equal(typeof value, 'string');
        assert.ok(value.trim().length > 0);
        if (locale !== 'en') assert.notEqual(value, english[key]);
    }
    assert.match(catalog['oidc_entry.setup_help'], /OIDC/);
    assert.match(catalog['oidc_entry.setup_help'], /Polaris/);
}
"""
        result = subprocess.run(
            [node, "-e", harness, str(ROOT / "frontend/js/core/oidc-entry-locales.js")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_entry_requires_explicit_navigation_and_preserves_owner_form(self):
        fragment = (ROOT / "frontend/fragments/auth/login.html").read_text(encoding="utf-8")
        self.assertIn('id="loginOidcEntry"', fragment)
        self.assertIn('href="/api/identity/oidc/start"', fragment)
        self.assertIn('id="loginForm"', fragment)
        self.assertIn('autocomplete="current-password"', fragment)
        self.assertNotIn("autofocus", fragment)
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the browser entry contract")
        harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const entry = {hidden: true, classList: {toggle(name, hidden) {
    assert.equal(name, 'hidden'); this.hidden = hidden;
}}};
const context = {document: {getElementById(id) {
    assert.equal(id, 'loginOidcEntry'); return entry;
}}, window: {location: {assign() {throw Error('Unexpected navigation');}}}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
for (const [data, visible] of [
    [undefined, false], [{}, false],
    [{oidc_enabled: true, setup_required: false}, true],
    [{oidc_enabled: true, setup_required: true}, false],
    [{oidc_enabled: false, setup_required: false}, false],
    [{oidc_enabled: 'true', setup_required: false}, false],
    [{oidc_enabled: true}, false]
]) {
    context.renderLoginOidcEntry(data);
    assert.equal(entry.hidden, !visible);
    assert.equal(entry.classList.hidden, !visible);
}
"""
        result = subprocess.run(
            [node, "-e", harness, str(ROOT / "frontend/js/features/authentication.js")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
