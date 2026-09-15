const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = process.argv[2];
const family = process.argv[3];

function harness() {
    const elements = new Map();
    class Element {
        constructor(id) {
            this.id = id; this.value = ''; this.type = 'text'; this.disabled = false;
            this.dataset = {}; this.children = []; this.inert = false; this.validity = '';
            this.classList = {toggle() {}, add() {}, remove() {}};
        }
        setAttribute() {}
        removeAttribute() {}
        closest() { return null; }
        setCustomValidity(value) { this.validity = value; }
        reportValidity() { return !this.validity; }
        focus() { throw new Error('No automatic field focus'); }
        querySelectorAll(selector) {
            return selector.includes('password') ? this.children.filter(x => x.type === 'password') : this.children;
        }
    }
    const requests = [];
    let failed = false;
    let malformed = false;
    const context = vm.createContext({console, URL, Set, Map, Promise,
        document: {getElementById: id => elements.get(id) || null, addEventListener() {},
            querySelectorAll: selector => selector === '[data-google-scope]'
                ? [...elements.values()].filter(x => x.dataset.googleScope) : []},
        t: key => key, getAuthHeaders: () => ({}), showStatus() {},
        showConfirmModal: async () => true,
        setSetupSecretVisibility(field, visible) { field.type = visible ? 'text' : 'password'; },
        PROVIDER_WORKSPACES: {grok: {settingsFamily: 'xai'}},
        fetch: async (url, options = {}) => {
            requests.push({url, options});
            return {ok: !failed, status: failed ? 503 : 200,
                json: async () => failed ? {detail: 'temporary'} : malformed ? {} : {config, env_locked: []}};
        }
    });
    const run = name => vm.runInContext(fs.readFileSync(path.join(root, 'frontend/js/features', name), 'utf8'), context);
    run('provider-settings-shared.js'); run('provider-onboarding.js');
    run('anthropic-settings.js'); run('xai-settings.js'); run('provider-owned-settings.js');
    const contract = vm.runInContext('PROVIDER_FORM_CONTRACT', context);
    const config = {};
    const scopes = family === 'google' ? ['google.shared', 'google.compatibility']
        : family === 'anthropic' ? ['claude-code.settings', 'anthropic.shared']
        : ['grok.settings', 'xai.settings', 'xai.shared'];
    const formIds = family === 'google' ? ['googleSharedSettingsForm', 'googleCompatibilitySettingsForm']
        : family === 'anthropic' ? ['claudeCodeSettingsForm', 'claudePlatformSettingsForm']
        : ['grokSettingsForm', 'xaiConsoleSettingsForm', 'xaiSharedSettingsForm'];
    const forms = scopes.map((scope, i) => {
        const form = new Element(formIds[i]); elements.set(form.id, form);
        if (family === 'google') form.dataset.googleScope = scope.split('.')[1];
        contract[scope].forEach(def => {
            const field = new Element(def.id); field.type = def.type;
            field.dataset.googleConfig = def.configKey;
            config[def.configKey] = def.type === 'url' ? 'https://api.example.test/v1' : 'configured-value';
            form.children.push(field); elements.set(field.id, field);
        });
        return form;
    });
    const api = family === 'google'
        ? vm.runInContext('({load:loadGoogleProviderSettings, save:saveGoogleProviderSettings})', context)
        : vm.runInContext(`({load:load${family === 'xai' ? 'Xai' : 'Anthropic'}Settings, save:save${family === 'xai' ? 'Xai' : 'Anthropic'}Settings, reset:reset${family === 'xai' ? 'Xai' : 'Anthropic'}Settings, workspace:loadProviderWorkspaceSettings})`, context);
    return {api, forms, elements, config, requests, fail: value => {failed = value;}, malformed: value => {malformed = value;}};
}

const tests = [];
tests.push(async function firstLoadFailureIsInertAndRetryWorks() {
    const h = harness(); h.fail(true); await h.api.load();
    assert(h.forms.every(form => form.inert), 'Failed initial load must leave every editor inert');
    const before = h.requests.length;
    if (family === 'google') await h.api.save(h.forms[0]); else await h.api.save(family === 'xai' ? 'oauth' : 'code');
    assert.equal(h.requests.length, before, 'Unloaded editor cannot save');
    h.fail(false); await h.api.load();
    assert(h.forms.every(form => !form.inert), 'Successful retry enables loaded editors');
});
tests.push(async function successfulSaveAndResetPreserveSiblingDraft() {
    const h = harness(); await h.api.load();
    const target = h.forms[0].children[0], sibling = h.forms[1].children[0];
    target.value = 'https://edited.example.test'; sibling.value = 'https://unsaved.example.test';
    const scope = family === 'xai' ? 'oauth' : 'code';
    h.fail(true);
    if (family === 'google') await h.api.save(h.forms[0]); else await h.api.save(scope);
    assert.equal(target.value, 'https://edited.example.test', 'Failed save retains submitted draft');
    h.fail(false);
    if (family === 'google') await h.api.save(h.forms[0]); else await h.api.save(scope);
    assert.equal(sibling.value, 'https://unsaved.example.test', 'Save must not reload sibling editor');
    const saved = JSON.parse(h.requests.at(-1).options.body).config;
    assert.deepEqual(Object.keys(saved).sort(), h.forms[0].children.filter(x => x.type !== 'password').map(x => x.dataset.googleConfig).sort(), 'Save owns only target scope');
    h.fail(true);
    if (family === 'google') await h.api.save(h.forms[0], true); else await h.api.reset(scope);
    assert.equal(target.value, 'https://edited.example.test', 'Failed reset retains target draft');
    h.fail(false);
    if (family === 'google') await h.api.save(h.forms[0], true); else await h.api.reset(scope);
    assert.equal(sibling.value, 'https://unsaved.example.test', 'Reset must not reload sibling editor');
    assert.equal(target.value, h.config[target.dataset.googleConfig], 'Reset applies target defaults');
    assert.equal(h.requests.filter(r => !r.options.method).length, 1, 'No broad reload after mutation');
});
tests.push(async function malformedSuccessDoesNotEnableUnknownSettings() {
    const h = harness(); h.malformed(true); await h.api.load();
    assert(h.forms.every(form => form.inert), 'Malformed config response must not mark editor ready');
    h.malformed(false); await h.api.load();
    assert(h.forms.every(form => !form.inert), 'Malformed initial response remains retryable');
});
if (family === 'anthropic') tests.push(async function sharedScopeActuallyValidatesItsFields() {
    const h = harness(); await h.api.load(); h.elements.get('claudeUserAgent').value = '';
    const count = h.requests.length; await h.api.save('shared');
    assert.equal(h.requests.length, count, 'Shared required User-Agent must validate before POST');
});
if (family === 'xai') tests.push(async function siblingWorkspaceReusesLoadedFamily() {
    const h = harness(); await h.api.load(); h.forms[0].children[0].value = 'https://unsaved.example.test';
    await h.api.workspace('grok');
    assert.equal(h.requests.length, 1, 'Existing loaded XAI forms prevent a new family fetch');
    assert.equal(h.forms[0].children[0].value, 'https://unsaved.example.test');
});
if (family === 'google') tests.push(async function googleUsesSharedContractValidation() {
    const h = harness(); await h.api.load(); h.forms[0].children[0].value = 'not-a-url';
    const count = h.requests.length; await h.api.save(h.forms[0]);
    assert.equal(h.requests.length, count, 'Google URL uses shared validation before POST');
});
if (family === 'google') tests.push(async function visibleSecretSuccessClearsAndRemasks() {
    const h = harness(); await h.api.load();
    const secret = h.elements.get('codeAssistClientSecret');
    secret.type = 'text'; secret.value = 'replacement-secret';
    await h.api.save(h.forms[1]);
    assert.equal(JSON.parse(h.requests.at(-1).options.body).config.code_assist_client_secret, 'replacement-secret');
    assert.equal(secret.value, '', 'Successful visible-secret save clears the value');
    assert.equal(secret.type, 'password', 'Successful visible-secret save remasks the input');
});
if (family === 'google') tests.push(async function emptyVisibleSecretIsOmitted() {
    const h = harness(); await h.api.load();
    const secret = h.elements.get('codeAssistClientSecret'); secret.type = 'text'; secret.value = '';
    await h.api.save(h.forms[1]);
    assert(!Object.hasOwn(JSON.parse(h.requests.at(-1).options.body).config, 'code_assist_client_secret'), 'Blank means unchanged even when eye toggle is open');
    assert.equal(secret.type, 'password');
});
if (family === 'google') tests.push(async function visibleSecretFailuresPreserveButRemaskDraft() {
    const h = harness(); await h.api.load(); h.fail(true);
    const secret = h.elements.get('codeAssistClientSecret');
    for (const reset of [false, true]) {
        secret.type = 'text'; secret.value = 'retry-secret';
        await h.api.save(h.forms[1], reset);
        assert.equal(secret.value, 'retry-secret', 'Failed mutation preserves secret for retry');
        assert.equal(secret.type, 'password', 'Failed mutation remasks visible secret');
    }
});
if (family === 'google') tests.push(async function resetNeverReflectsRedactedSecretAndIncompleteMapIsAtomic() {
    const h = harness(); await h.api.load();
    const form = h.forms[1], secret = h.elements.get('codeAssistClientSecret');
    const before = form.children.map(field => field.value);
    secret.type = 'text'; h.config.code_assist_client_secret = 'redacted-server-marker';
    delete h.config[form.children[0].dataset.googleConfig];
    await h.api.save(form, true);
    assert.deepEqual(form.children.map(field => field.value), before, 'Incomplete reset map must not partially overwrite any target field');
    h.config[form.children[0].dataset.googleConfig] = 'https://reset.example.test';
    secret.type = 'text'; secret.value = 'local-secret';
    await h.api.save(form, true);
    assert.equal(secret.value, '', 'Redacted server secret must never be reflected');
    assert.equal(secret.type, 'password');
});
if (family === 'google') tests.push(async function forcedLoadTreatsVisibleSecretAsSecret() {
    const h = harness(); await h.api.load();
    const secret = h.elements.get('codeAssistClientSecret');
    secret.type = 'text'; secret.value = 'visible-local-secret';
    await h.api.load(true);
    assert.equal(secret.value, '', 'Loading must not reflect redacted secret into eye-visible input');
    assert.equal(secret.type, 'password');
});
(async () => {
    const errors = [];
    for (const test of tests) {
        try { await test(); } catch (error) { errors.push(`${test.name}: ${error.message}`); }
    }
    assert.deepEqual(errors, []);
    console.log(`${family}: ${tests.length} runtime contracts passed`);
})().catch(error => {console.error(error); process.exitCode = 1;});
