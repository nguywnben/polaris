const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const coverageSession = process.argv.includes('--coverage') ? new (require('node:inspector').Session)() : null;
if (coverageSession) {
    coverageSession.connect();
    coverageSession.post('Profiler.enable');
    coverageSession.post('Profiler.startPreciseCoverage', { callCount: true, detailed: true });
}
class Element {
    constructor() { this.value = ''; this.files = []; this.children = []; this.listeners = {}; this.hidden = false; this.dataset = {}; this.classList = { toggle() {} }; }
    setAttribute(name, value) { this[name] = value; }
    removeAttribute(name) { delete this[name]; }
    replaceChildren(...nodes) { this.children = nodes; }
    append(...nodes) { this.children.push(...nodes); }
    appendChild(node) { this.children.push(node); }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    querySelectorAll() { return []; }
    click() { this.clicked = true; }
    remove() {}
}
const elements = new Map();
const el = id => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
const documentListeners = {};
global.document = { getElementById: el, createElement: () => new Element(), querySelectorAll: () => [], body: new Element(), addEventListener(name, fn) { documentListeners[name] = fn; } };
global.t = (key, vars) => key + (vars ? JSON.stringify(vars) : '');
global.getAuthHeaders = () => ({});
global.showConfirmModal = async () => true;
global.FormData = class { constructor() { this.values = new Map(); } append(k, v) { this.values.set(k, v); } };
const source = fs.readFileSync('frontend/js/features/backups.js', 'utf8');
vm.runInThisContext(source, { filename: 'frontend/js/features/backups.js' });
let requests = [];
const plan = { compatible: true, archive_version: 1, conflict_policy: 'abort_if_configured', table_counts: { credentials: 2 }, components: ['database'], created_at: '2026-09-15T00:00:00Z', source_application_version: '1.0.0', excluded: [] };
const response = (payload, status = 200) => ({ ok: status === 200, status, json: async () => payload, blob: async () => new Blob(['encrypted']) });
function inputs() {
    el('backupArchive').files = [{ size: 100, name: 'fixture.polaris-backup' }];
    el('backupRestorePassphrase').value = 'test-passphrase';
    el('backupConflictPolicy').value = 'abort_if_configured';
}
async function setup(permissions = ['backup.export', 'backup.restore']) {
    leaveBackupConsole(); requests = [];
    global.fetch = async (url, options) => {
        requests.push({ url, options });
        return response(url.endsWith('/session') ? { principal: { permissions } } : { dry_run: true, plan });
    };
    await loadBackupConsole(); inputs();
}
(async () => {
    await setup([]);
    await validateBackupArchive();
    assert.equal(requests.length, 1, 'permission denial must block requests');
    assert.equal(el('backupValidate').disabled, true);

    await setup();
    el('backupRestorePassphrase').value = 'short';
    await validateBackupArchive();
    assert.equal(requests.length, 1, 'invalid passphrase must not reach network');
    inputs(); el('backupArchive').files = [{ size: 64 * 1024 * 1024 + 1 }];
    await validateBackupArchive();
    assert.equal(requests.length, 1, 'oversize file must not reach network');

    await setup(); await restoreBackupArchive();
    assert.equal(requests.length, 1, 'restore needs successful validation');
    await validateBackupArchive();
    assert.equal(requests.at(-1).url, './api/backups/validate');
    assert.equal(requests.at(-1).options.body.values.get('conflict_policy'), 'abort_if_configured');
    assert.equal(el('backupRestore').disabled, false);
    backupInputsChanged();
    assert.equal(el('backupRestore').disabled, true, 'editing invalidates validation');

    await setup(); await validateBackupArchive();
    global.showConfirmModal = async () => false;
    await restoreBackupArchive();
    assert.equal(requests.length, 2, 'cancel must not restore');
    global.showConfirmModal = async () => { el('backupRestorePassphrase').value = 'changed-passphrase'; backupInputsChanged(); return true; };
    await restoreBackupArchive();
    assert.equal(requests.length, 2, 'changing inputs while confirming invalidates restore');

    await setup();
    let complete;
    let validationCalls = 0;
    global.fetch = () => { validationCalls++; return new Promise(resolve => { complete = resolve; }); };
    const pending = validateBackupArchive();
    await validateBackupArchive();
    backupInputsChanged();
    complete(response({ dry_run: true, plan })); await pending;
    assert.equal(validationCalls, 1, 'double click must send only one validation request');
    assert.equal(el('backupRestore').disabled, true, 'stale validation must be ignored');

    await setup(); await validateBackupArchive();
    global.showConfirmModal = async () => true;
    let restoreCalls = 0;
    global.fetch = async () => { restoreCalls++; throw new Error('sensitive server detail'); };
    await restoreBackupArchive();
    assert.equal(restoreCalls, 1, 'unknown restore outcome must not auto retry');
    assert.equal(el('backupStatus').textContent, 'backup.restore_unknown');
    assert.equal(el('backupRestore').disabled, true);
    assert.equal(el('backupPlan').children.length, 0, 'unknown restore outcome must remove the earlier dry-run assurance');

    await setup(); await validateBackupArchive();
    global.fetch = async () => response({ restored: true, session_reauthentication_required: true });
    await restoreBackupArchive();
    assert.equal(el('backupReauthenticate').hidden, false);
    assert.equal(el('backupRestorePassphrase').value, '');
    assert.equal(el('backupRestore').disabled, true);

    await setup();
    global.fetch = async () => response({ error: { code: 'backup_backend_unsupported', message: 'secret' } }, 409);
    await validateBackupArchive();
    assert.equal(el('backupStatus').textContent, 'backup.unsupported');
    assert.equal(el('backupCreate').disabled, true);
    leaveBackupConsole();
    assert.equal(el('backupRestorePassphrase').value, '');

    await setup();
    el('backupCreatePassphrase').value = 'test-passphrase';
    el('backupConfirmPassphrase').value = 'different-value';
    await downloadBackupArchive();
    assert.equal(requests.length, 1, 'mismatch must not download');
    assert.equal(el('backupStatus').textContent, 'backup.passphrase_mismatch');
    el('backupConfirmPassphrase').value = 'test-passphrase';
    await downloadBackupArchive();
    assert.equal(requests.at(-1).url, './api/backups');
    assert.deepEqual(JSON.parse(requests.at(-1).options.body), { passphrase: 'test-passphrase' });
    assert.equal(el('backupCreatePassphrase').value, '');
    assert.equal(el('backupStatus').textContent, 'backup.downloaded');
    await downloadBackupArchive(true);
    assert.equal(requests.at(-1).url, './api/backups/sanitized-export');
    assert.equal(requests.at(-1).options.body, undefined);

    await setup();
    global.fetch = async () => response({ error: { code: 'backup_archive_invalid', message: 'SECRET' } }, 400);
    await validateBackupArchive();
    assert.equal(el('backupStatus').textContent, 'backup.archive_invalid');
    assert.equal(el('backupRestore').disabled, true);
    global.fetch = async () => response({ dry_run: false, plan });
    await validateBackupArchive();
    assert.equal(el('backupStatus').textContent, 'backup.failed');
    assert.equal(el('backupRestore').disabled, true);

    await setup();
    const maliciousPlan = { ...plan, source_application_version: 'SECRET', components: ['SECRET'], table_counts: { secret: 'SECRET', credentials: 3, config: -99 } };
    global.fetch = async () => response({ dry_run: true, plan: maliciousPlan });
    await validateBackupArchive();
    const summary = el('backupPlan').children.map(child => child.textContent).join(' ');
    assert.equal(summary.includes('SECRET'), false, 'summary must use allowlisted numeric facts only');
    assert.ok(summary.includes('"count":3'));

    await setup();
    global.fetch = () => new Promise(resolve => { complete = resolve; });
    const leaving = validateBackupArchive();
    leaveBackupConsole();
    complete(response({ dry_run: true, plan })); await leaving;
    assert.equal(el('backupRestore').disabled, true, 'navigation invalidates in-flight validation');
    assert.equal(el('backupRestorePassphrase').value, '', 'secrets clear when in-flight operation finishes');

    await setup();
    let permissionReloads = 0;
    global.fetch = url => {
        if (url.endsWith('/session')) { permissionReloads++; return Promise.resolve(response({ principal: { permissions: [] } })); }
        return new Promise(resolve => { complete = resolve; });
    };
    const navigating = validateBackupArchive();
    leaveBackupConsole();
    assert.equal(el('backupRestorePassphrase').value, '', 'navigation must immediately clear DOM secrets');
    await loadBackupConsole();
    complete(response({ dry_run: true, plan })); await navigating;
    assert.equal(permissionReloads, 1, 'returning during a pending request must recheck permissions afterward');
    assert.equal(el('backupValidate').disabled, true);

    global.fetch = async () => response({ detail: 'SECRET' }, 403);
    await loadBackupConsole();
    assert.equal(el('backupCreate').disabled, true);
    assert.equal(el('backupStatus').textContent, 'backup.permissions_failed');
    await setup();
    global.fetch = async () => response({}, 401);
    await validateBackupArchive();
    assert.equal(el('backupReauthenticate').hidden, false);
    assert.equal(el('backupCreate').disabled, true);

    await setup();
    initBackupBindings(); initBackupBindings();
    await validateBackupArchive();
    const beforeLocale = el('backupPlan').children[0].textContent;
    const originalTranslate = global.t;
    global.t = (key, vars) => `translated:${originalTranslate(key, vars)}`;
    documentListeners['polaris:locale-change']();
    assert.notEqual(el('backupPlan').children[0].textContent, beforeLocale, 'validated plan must update when locale changes');
    global.t = originalTranslate;
    for (const restoring of [false, true]) {
        backupError(new Error('untrusted response detail'), restoring);
        const statusKey = restoring ? 'backup.restore_unknown' : 'backup.failed';
        const requestCount = requests.length;
        global.t = (key, vars) => `translated:${originalTranslate(key, vars)}`;
        documentListeners['polaris:locale-change']();
        assert.equal(el('backupStatus').textContent, `translated:${statusKey}`, 'failure status must update with the locale');
        assert.equal(requests.length, requestCount, 'locale changes must not retry or revalidate');
        global.t = originalTranslate;
    }
    el('backupChooseArchive').listeners.click();
    assert.equal(el('backupArchive').clicked, true, 'localized chooser opens the hidden file input');
    el('backupArchive').files = [{ size: 100, name: '<img src=x onerror=alert(1)>.ogb' }];
    el('backupArchive').listeners.change();
    assert.equal(el('backupSelectedArchive').textContent, '<img src=x onerror=alert(1)>.ogb', 'selected name is text only');
    leaveBackupConsole();
    assert.equal(el('backupSelectedArchive').textContent, 'backup.no_archive');
    let prevented = 0;
    el('backupCreateForm').listeners.submit({ preventDefault() { prevented++; } });
    el('backupImportForm').listeners.submit({ preventDefault() { prevented++; } });
    assert.equal(prevented, 2, 'forms must use custom validation');

    const catalogs = Object.fromEntries(['en','vi','zh-CN','zh-TW','de','es','fr','id','it','ja','ko','pt','ru','th','tr'].map(l => [l, {}]));
    global.PAGE_LOCALE_TRANSLATIONS = structuredClone(catalogs);
    global.MESSAGE_CATALOGS = catalogs;
    global.ENGLISH_SEMANTIC_KEYS_BY_MESSAGE = new Map();
    vm.runInThisContext(fs.readFileSync('frontend/js/core/backup-locales.js', 'utf8'), { filename: 'frontend/js/core/backup-locales.js' });
    for (const [locale, catalog] of Object.entries(catalogs)) {
        assert.deepEqual(Object.keys(catalog), Object.keys(catalogs.en), locale);
        for (const [key, value] of Object.entries(catalog)) {
            assert.equal(typeof value, 'string');
            assert.deepEqual(value.match(/\{\w+\}/g), catalogs.en[key].match(/\{\w+\}/g), `${locale}:${key} interpolation`);
        }
        if (locale !== 'en') for (const [key, value] of Object.entries(catalog)) assert.notEqual(value, catalogs.en[key], `${locale}:${key}`);
    }
    for (const match of source.matchAll(/['"](backup\.[a-z_]+)['"]/g)) {
        if (['backup.export', 'backup.restore'].includes(match[1])) continue;
        assert.ok(catalogs.en[match[1]], `Missing runtime copy: ${match[1]}`);
    }
    console.log('Backup permissions, validation, cancellation, stale responses, unknown outcome, reauthentication, and 15 locales passed.');
    if (coverageSession) {
        coverageSession.post('Profiler.takePreciseCoverage', (error, coverage) => {
            if (error) throw error;
            const script = coverage.result.find(item => item.url.endsWith('frontend/js/features/backups.js'));
            assert.ok(script, 'V8 must report the actual feature module');
            const ranges = script.functions.flatMap(fn => fn.ranges);
            let offset = 0;
            let total = 0;
            let covered = 0;
            for (const line of source.split('\n')) {
                const position = offset + line.search(/\S|$/);
                offset += line.length + 1;
                if (!line.trim() || line.trim().startsWith('//')) continue;
                total++;
                const closest = ranges.filter(range => range.startOffset <= position && range.endOffset > position)
                    .sort((a, b) => (a.endOffset - a.startOffset) - (b.endOffset - b.startOffset))[0];
                if (closest?.count > 0) covered++;
            }
            console.log(`backups.js V8 executed-line coverage: ${covered}/${total} (${(100 * covered / total).toFixed(1)}%)`);
            assert.ok(covered / total >= 0.8, 'New feature module must meet the 80% coverage target');
            coverageSession.disconnect();
        });
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
