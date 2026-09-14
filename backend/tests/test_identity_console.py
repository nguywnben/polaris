"""Static security, permission, and interaction contracts for the Identity console."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.panel.root import serve_control_panel

ROOT = BACKEND_DIR.parent
FRONTEND = ROOT / "frontend"
IDENTITY_FRAGMENT = FRONTEND / "fragments/pages/identity.html"
IDENTITY_CONTRACT = FRONTEND / "js/core/identity-contract.js"
IDENTITY_SCRIPT = FRONTEND / "js/features/identity.js"
IDENTITY_STYLE = FRONTEND / "css/identity.css"
IDENTITY_LOCALES = FRONTEND / "js/core/identity-locales.js"


class IdentityConsoleContractTests(unittest.TestCase):
    def _source(self, path: Path) -> str:
        self.assertTrue(path.is_file(), f"Missing Identity console asset: {path}")
        return path.read_text(encoding="utf-8")

    def _run_identity_contract(self, assertions: str, *, include_feature: bool = False) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for the Identity client behavior contract.")
        source_paths = [str(IDENTITY_CONTRACT)]
        feature_exports = ""
        if include_feature:
            source_paths.append(str(IDENTITY_SCRIPT))
            feature_exports = """
    reset: resetIdentityConsoleState,
    api: identityApi,
    renderOidc: renderIdentityOidc,
    toggle: toggleManagedIdentity,
    updateRole: updateIdentityRole,
    submitCreate: submitIdentityCreate,
    changePage: changeIdentityPage,
    changeSessionPage: changeIdentitySessionPage,
    loadPage: loadIdentityPage,
    initBindings: initIdentityBindings,
    setApi(fn) { identityApi = fn; },
    setConfirm(fn) { showIdentityConfirmation = fn; },
    setLoadPage(fn) { loadIdentityPage = fn; },
    setLoadSessions(fn) { loadIdentitySessions = fn; },
"""
        harness = f"""
const fs = require('fs');
const vm = require('vm');
class TestElement {{
    constructor() {{
        this.classes = new Set();
        this.classList = {{
            add: (...names) => names.forEach((name) => this.classes.add(name)),
            toggle: (name, force) => force ? this.classes.add(name) : this.classes.delete(name)
        }};
        this.dataset = {{}};
        this.disabled = false;
        this.isConnected = true;
        this.open = false;
        this.listeners = new Map();
    }}
    addEventListener(type, listener) {{
        if (!this.listeners.has(type)) this.listeners.set(type, []);
        this.listeners.get(type).push(listener);
    }}
    append() {{}}
    appendChild() {{}}
    close() {{ this.open = false; }}
    focus() {{ this.focused = true; }}
    matches() {{ return true; }}
    replaceChildren() {{}}
    setAttribute() {{}}
    dispatchEvent(event) {{
        for (const listener of this.listeners.get(event.type) || []) listener(event);
    }}
}}
global.__elements = new Map();
global.__queryResult = null;
global.document = {{
    addEventListener() {{}},
    getElementById(id) {{ return global.__elements.get(id) || null; }},
    querySelector() {{ return global.__queryResult; }},
    createElement() {{ return new TestElement(); }}
}};
global.HTMLElement = TestElement;
global.CSS = {{ escape(value) {{ return String(value); }} }};
global.AppState = {{ authenticated: true, tabLoadTimes: {{}} }};
global.navigate = (path) => {{ global.__navigated = path; }};
global.showStatus = () => {{}};
global.t = (key) => key;
global.getActiveLocale = () => 'en';
global.getAuthHeaders = () => ({{}});
const source = {json.dumps(source_paths)}.map((path) => fs.readFileSync(path, 'utf8')).join('\\n');
vm.runInThisContext(source + `\n;globalThis.__identityContract = {{
    state: IdentityConsoleState,
    can: identityCan,
    validatePrincipal: identityValidatePrincipal,
    validatePage: identityValidatePage,
    validateRecord: identityValidateRecord,
    validateSession: identityValidateSession,
    validateOidc: identityValidateOidcPolicy,
    invalidatedByAdvance: identityCurrentSessionInvalidatedByOidcAdvance,
    invalidatedByMutation: identityMutationInvalidatesCurrentSession,
    resetState: identityResetState,
{feature_exports}
}};`);
const contract = global.__identityContract;
function assert(condition, message) {{ if (!condition) throw new Error(message); }}
(async () => {{
{assertions}
}})().catch((error) => {{ console.error(error); process.exitCode = 1; }});
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

    def test_identity_destination_is_reachable_and_bundled(self):
        body = serve_control_panel().body.decode("utf-8")
        root_source = (BACKEND_DIR / "core/panel/root.py").read_text(encoding="utf-8")
        navigation = self._source(FRONTEND / "js/core/navigation.js")

        self.assertIn('@router.get("/identity"', root_source)
        self.assertIn('data-tab="identity"', body)
        self.assertIn('id="identityTab"', body)
        self.assertIn("'/identity': 'identity'", navigation)
        self.assertIn("identity: '/identity'", navigation)
        self.assertIn("identity: () => loadIdentityConsole()", navigation)
        for asset in (
            "pages/identity.html",
            "css/identity.css",
            "js/core/identity-locales.js",
            "js/core/identity-contract.js",
            "js/features/identity.js",
        ):
            self.assertIn(asset, root_source)

    def test_identity_page_exposes_semantic_status_and_inventory_surfaces(self):
        fragment = self._source(IDENTITY_FRAGMENT)

        for element_id in (
            "identityPrincipalSummary",
            "identityOidcSummary",
            "identityRecoverySummary",
            "identityList",
            "identityListStatus",
            "identityPreviousPage",
            "identityNextPage",
            "identitySessionList",
            "identitySessionStatus",
            "identityCreateDialog",
            "identityConfirmDialog",
        ):
            self.assertIn(f'id="{element_id}"', fragment)
        self.assertIn('aria-live="polite"', fragment)
        self.assertIn('<dialog id="identityCreateDialog"', fragment)
        self.assertIn('<dialog id="identityConfirmDialog"', fragment)
        self.assertRegex(fragment, r"<h1[^>]+data-i18n=\"identity\.title\"")

    def test_escape_key_closes_the_create_dialog(self):
        self._run_identity_contract(
            """
const dialog = new HTMLElement();
dialog.open = true;
global.__elements.set('identityCreateDialog', dialog);
contract.initBindings();
let prevented = false;
dialog.dispatchEvent({
    type: 'keydown',
    key: 'Escape',
    preventDefault() { prevented = true; }
});
assert(prevented, 'Escape did not suppress the native dialog default');
assert(!dialog.open, 'Escape did not close the create dialog');
""",
            include_feature=True,
        )

    def test_client_uses_only_the_bounded_w411_resources(self):
        source = self._source(IDENTITY_CONTRACT) + self._source(IDENTITY_SCRIPT)

        self.assertIn("fetch(`./api/identity${path}`", source)
        for resource in (
            "identityApi('/session'",
            "identityApi(`/identities?",
            "identityApi(`/sessions?",
            "identityApi('/oidc-policy'",
            "identityApi('/oidc-policy/advance'",
            "identityApi('/recovery'",
        ):
            self.assertIn(resource, source)
        self.assertIn("page_size", source)
        self.assertIn("next_cursor", source)
        self.assertIn("expected_revision", source)
        self.assertIn("encodeURIComponent", source)

    def test_controls_are_derived_from_exact_effective_permissions(self):
        source = self._source(IDENTITY_CONTRACT) + self._source(IDENTITY_SCRIPT)

        for permission in (
            "identity.read",
            "identity.manage",
            "owners.manage",
            "sessions.manage",
            "oidc.manage",
            "recovery.manage",
        ):
            self.assertIn(f"'{permission}'", source)
        self.assertIn("function identityCan(permission)", source)
        self.assertIn("identityCan('owners.manage')", source)
        self.assertIn("identityCan('sessions.manage')", source)
        self.assertIn("identityCan('oidc.manage')", source)

        self._run_identity_contract(
            """
contract.state.permissions = new Set(['identity.read', 'invented.manage']);
assert(contract.can('identity.read') === true, 'exact granted permission was denied');
assert(contract.can('identity.manage') === false, 'missing permission was granted');
assert(contract.can('invented.manage') === false, 'unknown permission was granted');
"""
        )

    def test_mutations_confirm_risk_and_preserve_stale_operator_input(self):
        source = (
            self._source(IDENTITY_CONTRACT)
            + self._source(IDENTITY_SCRIPT)
            + self._source(FRONTEND / "js/features/navigation.js")
        )

        for action in (
            "identity-create",
            "identity-toggle",
            "identity-role",
            "identity-session-revoke",
            "identity-oidc-advance",
        ):
            self.assertIn(action, source)
        self.assertIn("showIdentityConfirmation", source)
        self.assertIn("returnFocus", source)
        self.assertIn("error.status === 409", source)
        self.assertIn("roleDrafts.set(record.identityId, role)", source)
        self.assertIn("await loadIdentityPage()", source)
        self.assertIn("await loadIdentityOidc()", source)
        self.assertNotIn("preserveIdentityDraft", source)

        self._run_identity_contract(
            """
contract.state.roleDrafts.set('idn_example', 'operator');
assert(contract.state.roleDrafts.get('idn_example') === 'operator', 'role draft was lost');
contract.state.principal = { principalType: 'oidc_user' };
assert(contract.invalidatedByAdvance() === true, 'OIDC session invalidation was missed');
contract.state.principal.identityId = 'idn_self';
assert(contract.invalidatedByMutation('idn_self') === true, 'self mutation invalidation was missed');
assert(contract.invalidatedByMutation('idn_other') === false, 'another identity signed out this user');
contract.state.principal = { principalType: 'local_owner' };
assert(contract.invalidatedByAdvance() === false, 'local owner was signed out incorrectly');
"""
        )

    def test_untrusted_records_use_dom_text_and_never_browser_storage(self):
        source = self._source(IDENTITY_CONTRACT) + self._source(IDENTITY_SCRIPT)
        fragment = self._source(IDENTITY_FRAGMENT)
        combined = source + fragment

        self.assertIn("textContent", source)
        self.assertIn("function identityValidateOidcPolicy(payload)", source)
        self.assertIn("function identityValidateRecovery(payload)", source)
        self.assertIn("function identityValidateCursor(value, maximum", source)
        self.assertNotIn("innerHTML", source)
        self.assertNotIn("localStorage", combined)
        self.assertNotIn("sessionStorage", combined)
        for forbidden in (
            "access_token",
            "refresh_token",
            "client_secret",
            "session_digest",
            "bearer_token",
        ):
            self.assertNotIn(forbidden, combined.lower())

        self._run_identity_contract(
            """
const principal = {
    principal: {
        identity_id: 'local-owner', principal_type: 'local_owner', role: 'owner',
        role_source: 'local_bootstrap', permissions: Array(65).fill('identity.read')
    },
    authentication_context: 'opaque_session'
};
let rejectedPermissions = false;
try { contract.validatePrincipal(principal); } catch { rejectedPermissions = true; }
assert(rejectedPermissions, 'oversized permission collection was accepted');
const identity = {
    identity_id: 'idn_example', principal_type: 'oidc_user', issuer: 'https://idp.example',
    subject: 'operator', enabled: true, revision: 1, authorization_epoch: 1,
    created_at: '2026-01-01T00:00:00+00:00', updated_at: '2026-01-01T00:00:00+00:00',
    binding_id: 'rbn_example', role: 'operator', role_source: 'direct_binding', binding_revision: 1
};
let rejectedPage = false;
try {
    contract.validatePage(
        { identities: Array(26).fill(identity), next_cursor: null },
        'identities', contract.validateRecord, 512
    );
} catch { rejectedPage = true; }
assert(rejectedPage, 'oversized identity page was accepted');
assert(contract.validateOidc({
    readiness: 'ready', revision: 1, authorization_epoch: 1, role_mapping_count: 0,
    enabled: true, secret_configured: true, issuer: null, redirect_uri: null,
    scopes: Array(65).fill('openid')
}) === null, 'oversized OIDC scopes were accepted');
"""
        )

    def test_mutation_controls_are_locked_while_requests_are_in_flight(self):
        source = self._source(IDENTITY_SCRIPT)

        self.assertGreaterEqual(source.count("element.disabled = true;"), 4)
        self.assertGreaterEqual(source.count("element.disabled = false;"), 4)
        self.assertIn("if (submit) submit.disabled = true;", source)
        self.assertIn("if (submit) submit.disabled = false;", source)

    def test_pagination_is_single_flight_and_create_conflicts_are_specific(self):
        self._run_identity_contract(
            """
for (const id of [
    'identityList', 'identityListStatus', 'identityPreviousPage', 'identityNextPage',
    'identityPageNumber', 'identitySessionList', 'identitySessionStatus',
    'identitySessionPreviousPage', 'identitySessionNextPage', 'identitySessionPageNumber'
]) global.__elements.set(id, new HTMLElement());
contract.state.permissions = new Set(['identity.read', 'identity.manage', 'sessions.manage']);
contract.state.identityNextCursor = 'identity-cursor-2';
contract.state.sessionNextCursor = 'ssr_0123456789abcdef0123456789abcdef';
let identityRequests = 0;
let sessionRequests = 0;
let releaseIdentity;
let releaseSession;
contract.setApi((path) => {
    if (path.startsWith('/identities?')) {
        identityRequests += 1;
        return new Promise((resolve) => { releaseIdentity = resolve; });
    }
    if (path.startsWith('/sessions?')) {
        sessionRequests += 1;
        return new Promise((resolve) => { releaseSession = resolve; });
    }
    throw new Error(`unexpected path: ${path}`);
});
const firstIdentityPage = contract.changePage('next');
const duplicateIdentityPage = contract.changePage('next');
const firstSessionPage = contract.changeSessionPage('next');
const duplicateSessionPage = contract.changeSessionPage('next');
assert(identityRequests === 1, 'rapid identity pagination issued duplicate requests');
assert(sessionRequests === 1, 'rapid session pagination issued duplicate requests');
assert(contract.state.identityPage === 2, 'identity page advanced more than once');
assert(contract.state.sessionPage === 2, 'session page advanced more than once');
assert(contract.state.identityCursorStack.length === 1, 'identity backstack was duplicated');
assert(contract.state.sessionCursorStack.length === 1, 'session backstack was duplicated');
assert(global.__elements.get('identityNextPage').disabled, 'identity pagination stayed enabled');
assert(global.__elements.get('identitySessionNextPage').disabled, 'session pagination stayed enabled');
releaseIdentity({ identities: [], next_cursor: null });
releaseSession({ sessions: [], next_cursor: null });
await Promise.all([
    firstIdentityPage, duplicateIdentityPage, firstSessionPage, duplicateSessionPage
]);

global.FormData = class {
    constructor(form) { this.form = form; }
    get(name) { return this.form.data[name]; }
};
const createDialog = new HTMLElement();
createDialog.open = true;
const createStatus = new HTMLElement();
const createSubmit = new HTMLElement();
global.__elements.set('identityCreateDialog', createDialog);
global.__elements.set('identityCreateStatus', createStatus);
global.__elements.set('identityCreateSubmit', createSubmit);
const form = new HTMLElement();
form.reportValidity = () => true;
form.data = { issuer: 'https://idp.example', subject: 'existing', role: 'viewer' };
contract.setApi(async () => { const error = new Error('duplicate'); error.status = 409; throw error; });
await contract.submitCreate({ preventDefault() {}, currentTarget: form });
assert(
    createStatus.textContent === 'identity.already_exists',
    'create conflict was presented as a stale CAS revision'
);
""",
            include_feature=True,
        )

    def test_mutation_workflows_refetch_sign_out_clear_state_and_restore_focus(self):
        self._run_identity_contract(
            """
const identity = {
    identityId: 'idn_self', principalType: 'oidc_user', issuer: 'https://idp.example',
    subject: 'operator', enabled: true, revision: 1, authorizationEpoch: 1,
    createdAt: '2026-01-01T00:00:00+00:00', updatedAt: '2026-01-01T00:00:00+00:00',
    bindingId: 'rbn_example', role: 'operator', roleSource: 'direct_binding', bindingRevision: 1
};
contract.state.permissions = new Set(['identity.manage']);
contract.state.principal = { principalType: 'oidc_user', identityId: 'idn_self' };
contract.state.identities = [identity];
contract.state.createDraft = { issuer: 'https://private.example', subject: 'draft', role: 'viewer' };
contract.state.roleDrafts.set('idn_old', 'operator');
AppState.tabLoadTimes.identity = Date.now();
contract.setConfirm(async () => true);
contract.setApi(async () => ({}));
contract.setLoadPage(async () => { throw new Error('self mutation must sign out before refetch'); });
contract.setLoadSessions(async () => { throw new Error('self mutation must sign out before refetch'); });
const toggle = new HTMLElement();
toggle.dataset.identityId = 'idn_self';
await contract.toggle(toggle);
assert(AppState.authenticated === false, 'self mutation left the shell authenticated');
assert(global.__navigated === '/login', 'self mutation did not navigate to login');
assert(contract.state.principal === null, 'principal survived sign-out');
assert(contract.state.createDraft === null, 'create draft crossed the session boundary');
assert(contract.state.roleDrafts.size === 0, 'role draft crossed the session boundary');
assert(!('identity' in AppState.tabLoadTimes), 'identity tab cache survived sign-out');

AppState.authenticated = true;
contract.state.permissions = new Set(['identity.manage']);
contract.state.principal = { principalType: 'local_owner', identityId: 'local-owner' };
contract.state.identities = [{ ...identity, identityId: 'idn_other' }];
const roleSelect = new HTMLElement();
roleSelect.value = 'security_admin';
global.__queryResult = roleSelect;
let refetches = 0;
contract.setApi(async () => { const error = new Error('conflict'); error.status = 409; throw error; });
contract.setLoadPage(async () => { refetches += 1; });
contract.setLoadSessions(async () => {});
const roleButton = new HTMLElement();
roleButton.dataset.identityId = 'idn_other';
await contract.updateRole(roleButton);
assert(refetches === 1, '409 did not refetch the current identity revision');
assert(contract.state.roleDrafts.get('idn_other') === 'security_admin', '409 lost the role draft');
assert(roleSelect.focused === true, 'focus was not deliberately restored after refetch');

const advance = new HTMLElement();
global.__elements.set('identityOidcAdvance', advance);
contract.state.oidcPolicy = { readiness: 'ready' };
contract.state.permissions = new Set(['oidc.manage']);
contract.renderOidc();
assert(!advance.classes.has('hidden'), 'authorized OIDC control was hidden');
contract.state.oidcPolicy = null;
contract.renderOidc();
assert(advance.classes.has('hidden'), 'stale OIDC control remained visible');

contract.state.permissions = new Set(['identity.read']);
let releasePage;
contract.setApi(() => new Promise((resolve) => { releasePage = resolve; }));
const staleLoad = contract.loadPage({ generation: contract.state.generation });
contract.resetState();
releasePage({ identities: [{
    identity_id: 'idn_stale', principal_type: 'oidc_user', issuer: 'https://old.example',
    subject: 'old-user', enabled: true, revision: 1, authorization_epoch: 1,
    created_at: '2026-01-01T00:00:00+00:00', updated_at: '2026-01-01T00:00:00+00:00',
    binding_id: 'rbn_stale', role: 'viewer', role_source: 'direct_binding', binding_revision: 1
}], next_cursor: null });
await staleLoad;
assert(contract.state.identities.length === 0, 'stale response repopulated identity state');

AppState.authenticated = true;
contract.state.principal = { principalType: 'local_owner', identityId: 'local-owner' };
contract.state.createDraft = { issuer: 'https://private.example', subject: 'draft', role: 'viewer' };
AppState.tabLoadTimes.identity = Date.now();
global.fetch = async () => ({
    ok: false,
    status: 401,
    async json() { return {}; }
});
let unauthorizedRejected = false;
try { await contract.api('/session'); } catch { unauthorizedRejected = true; }
assert(unauthorizedRejected, '401 response did not reject the Identity API call');
assert(AppState.authenticated === false, '401 response left the shell authenticated');
assert(global.__navigated === '/login', '401 response did not navigate to login');
assert(contract.state.principal === null, '401 response retained principal state');
assert(contract.state.createDraft === null, '401 response retained an operator draft');
assert(!('identity' in AppState.tabLoadTimes), '401 response retained the Identity tab cache');
""",
            include_feature=True,
        )

    def test_identity_locale_catalog_is_complete_for_all_supported_locales(self):
        source = self._source(IDENTITY_LOCALES)
        keys = re.findall(
            r"^    '(identity\.[a-z0-9_]+)',?$",
            source.split("const IDENTITY_KEYS = [", 1)[1].split("];", 1)[0],
            re.MULTILINE,
        )
        values_block = source.split("const IDENTITY_LOCALE_VALUES = {", 1)[1].split("\n};", 1)[0]
        catalogs = {
            match.group(1) or match.group(2): json.loads(match.group(3))
            for match in re.finditer(
                r"^    (?:'([^']+)'|([a-z]{2})): (\[.*\]),?$",
                values_block,
                re.MULTILINE,
            )
        }
        expected = {
            "en",
            "zh-CN",
            "zh-TW",
            "de",
            "es",
            "fr",
            "id",
            "it",
            "ja",
            "ko",
            "pt",
            "ru",
            "th",
            "tr",
            "vi",
        }
        self.assertTrue(keys)
        self.assertEqual(set(catalogs), expected)
        for locale, values in catalogs.items():
            with self.subTest(locale=locale):
                self.assertEqual(len(values), len(keys))
                self.assertTrue(all(isinstance(value, str) and value for value in values))

        supplemental_block = source.split("const IDENTITY_SUPPLEMENTAL_LOCALE_VALUES = {", 1)[
            1
        ].split("\n};", 1)[0]
        supplemental = {
            match.group(1): json.loads(match.group(2))
            for match in re.finditer(
                r'^    "([^"]+)": (\{.*\}),?$', supplemental_block, re.MULTILINE
            )
        }
        self.assertEqual(set(supplemental), expected)
        for locale, messages in supplemental.items():
            with self.subTest(locale=locale, catalog="supplemental"):
                expected_keys = {"identity.already_exists"}
                if locale in {"en", "vi"}:
                    expected_keys.add("identity.governance")
                self.assertEqual(set(messages), expected_keys)
                self.assertTrue(messages["identity.already_exists"])

    def test_identity_has_dedicated_responsive_and_focus_styles(self):
        source = self._source(IDENTITY_STYLE)

        self.assertIn(".identity-layout", source)
        self.assertIn(".identity-record", source)
        self.assertIn("@media (max-width: 760px)", source)
        self.assertIn(":focus-visible", source)
        self.assertIn("min-width: 0", source)


if __name__ == "__main__":
    unittest.main()
