"""Backup visit lifecycle must not depend on cached Settings data requests."""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class BackupNavigationTests(unittest.TestCase):
    def test_reentry_refreshes_permissions_despite_pending_config_request(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the navigation contract")
        script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = new Map();
function element(id) {
    if (!elements.has(id)) {
        const classes = new Set();
        elements.set(id, {
            value: '', dataset: {}, hidden: false,
            style: {setProperty() {}},
            setAttribute() {}, removeAttribute() {}, replaceChildren() {},
            querySelectorAll: () => [],
            classList: {add: name => classes.add(name), remove: name => classes.delete(name),
                contains: name => classes.has(name)}
        });
    }
    return elements.get(id);
}
function deferred() {
    let resolve;
    const promise = new Promise(done => { resolve = done; });
    return {promise, resolve};
}
const initialPermissions = deferred(), pendingConfig = deferred();
const location = new URL('http://localhost/dashboard');
let requests = 0;
const context = vm.createContext({
    URL,
    document: {getElementById: element, querySelectorAll: () => [],
        querySelector: selector => selector === '.tab-content.active'
            ? [...elements].find(([id, el]) => id.endsWith('Tab') && el.classList.contains('active'))?.[1]
            : null},
    window: {location},
    history: {replaceState: (_, __, path) => {location.href = new URL(path, location.href).href;},
        pushState: (_, __, path) => {location.href = new URL(path, location.href).href;}},
    AppState: {authenticated: true, setupRequired: false, tabLoadTimes: {},
        tabLoadPromises: {config: pendingConfig.promise}},
    t: key => key, getAuthHeaders: () => ({}), setMobileMenuState() {},
    refreshUsageStats: async () => {}, loadConfig: () => pendingConfig.promise,
    fetch: async url => {
        assert.equal(url, './api/identity/session');
        requests++;
        return requests === 1 ? initialPermissions.promise
            : {ok: true, json: async () => ({principal: {permissions: ['backup.restore']}})};
    }
});
vm.runInContext(fs.readFileSync('frontend/js/features/backups.js', 'utf8')
    + '\nthis.state = BackupConsoleState;', context);
vm.runInContext(fs.readFileSync('frontend/js/core/navigation.js', 'utf8'), context);
context.resetConsoleScroll = () => {};
context.focusActivePage = () => {};
const permissionLoads = [];
const loadBackupConsole = context.loadBackupConsole;
context.loadBackupConsole = () => {
    const promise = loadBackupConsole();
    permissionLoads.push(promise);
    return promise;
};
(async () => {
    context.navigate('/config', false);
    assert.equal(requests, 1, 'entering Settings checks permissions despite pending config data');
    element('backupRestorePassphrase').value = 'test-only-previous-visit';
    context.navigate('/dashboard', false);
    assert.equal(element('backupRestorePassphrase').value, '', 'leave clears secrets immediately');
    context.navigate('/config', false);
    assert.equal(context.state.active, true);
    assert.equal(context.state.reloadRequested, true, 'return queues a fresh permission request');
    initialPermissions.resolve({ok: true, json: async () => ({principal: {permissions: ['backup.export']}})});
    await permissionLoads[0];
    assert.equal(requests, 2, 'stale permission completion triggers exactly one fresh check');
    assert.deepEqual([...context.state.permissions], ['backup.restore']);
    assert.equal(context.state.busy, false);
    assert.equal(element('backupValidate').disabled, false);
    assert.equal(element('backupCreate').disabled, true);
    assert.equal(element('backupRestorePassphrase').value, '');
    assert.equal(context.AppState.tabLoadPromises.config, pendingConfig.promise,
        'permission lifecycle finishes without waiting for config data');
    pendingConfig.resolve();
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
        result = subprocess.run(
            [node, "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
