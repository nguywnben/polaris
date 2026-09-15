// Portable archives are supported only by the SQLite backend. Secrets stay in form controls.
const MAX_BACKUP_UPLOAD_BYTES = 64 * 1024 * 1024;
const BackupConsoleState = {
    active: false, busy: false, reloadRequested: false, generation: 0, revision: 0,
    validatedRevision: null, planSummary: null, statusKey: '', permissions: new Set(), unsupported: false, restored: false
};

function backupElement(id) { return document.getElementById(id); }

function backupStatus(key = '') {
    BackupConsoleState.statusKey = key;
    const status = backupElement('backupStatus');
    if (status) {
        status.textContent = key ? t(key) : '';
        if (key) status.setAttribute('data-i18n', key);
        else status.removeAttribute('data-i18n');
    }
}

function renderBackupControls() {
    const state = BackupConsoleState;
    const blocked = !state.active || state.busy || state.unsupported || state.restored;
    for (const [id, permission] of [
        ['backupCreate', 'backup.export'], ['backupSanitized', 'backup.export'],
        ['backupValidate', 'backup.restore'], ['backupRestore', 'backup.restore'],
        ['backupChooseArchive', 'backup.restore']
    ]) {
        const button = backupElement(id);
        if (button) button.disabled = blocked || !state.permissions.has(permission)
            || (id === 'backupRestore' && state.validatedRevision !== state.revision);
    }
    backupElement('backupControls')?.setAttribute('aria-busy', String(state.busy));
    for (const input of backupElement('backupControls')?.querySelectorAll('input, select') || []) {
        const permission = ['backupCreatePassphrase', 'backupConfirmPassphrase'].includes(input.id)
            ? 'backup.export' : 'backup.restore';
        input.disabled = blocked || !state.permissions.has(permission);
    }
}

function backupInputsChanged() {
    BackupConsoleState.revision++;
    BackupConsoleState.validatedRevision = null;
    BackupConsoleState.planSummary = null;
    backupElement('backupPlan')?.replaceChildren();
    const selected = backupElement('backupSelectedArchive');
    const name = backupElement('backupArchive')?.files?.[0]?.name;
    if (selected) {
        selected.textContent = name ? name.slice(0, 255) : t('backup.no_archive');
        if (name) selected.removeAttribute('data-i18n');
        else selected.setAttribute('data-i18n', 'backup.no_archive');
    }
    renderBackupControls();
}

function clearBackupSecrets() {
    for (const id of ['backupCreatePassphrase', 'backupConfirmPassphrase', 'backupRestorePassphrase']) {
        const input = backupElement(id);
        if (input) {
            input.value = '';
            input.type = 'password';
            input.removeAttribute('aria-invalid');
            backupElement(`${id}Toggle`)?.setAttribute('aria-pressed', 'false');
        }
    }
    const file = backupElement('backupArchive');
    if (file) file.value = '';
    const selected = backupElement('backupSelectedArchive');
    if (selected) {
        selected.textContent = t('backup.no_archive');
        selected.setAttribute('data-i18n', 'backup.no_archive');
    }
    const policy = backupElement('backupConflictPolicy');
    if (policy) policy.value = 'abort_if_configured';
}

function leaveBackupConsole() {
    BackupConsoleState.active = false;
    BackupConsoleState.reloadRequested = false;
    BackupConsoleState.generation++;
    backupInputsChanged();
    // Requests already own their bodies; leaving during confirmation cancels that generation.
    clearBackupSecrets();
}

async function loadBackupConsole() {
    const state = BackupConsoleState;
    state.active = true;
    if (state.busy) {
        state.reloadRequested = true;
        renderBackupControls();
        return;
    }
    const generation = ++state.generation;
    state.permissions = new Set();
    state.busy = true;
    state.unsupported = false;
    state.restored = false;
    backupElement('backupReauthenticate').hidden = true;
    backupInputsChanged();
    backupStatus('backup.loading');
    try {
        const response = await fetch('./api/identity/session', { headers: getAuthHeaders(false), cache: 'no-store' });
        if (!response.ok) throw new Error('backup_permissions_unavailable');
        const payload = await response.json();
        if (!state.active || generation !== state.generation) return;
        const permissions = payload?.principal?.permissions;
        if (!Array.isArray(permissions) || permissions.length > 64) throw new Error('backup_permissions_invalid');
        state.permissions = new Set(permissions.filter(value => ['backup.export', 'backup.restore'].includes(value)));
        backupStatus(state.permissions.size ? '' : 'backup.denied');
    } catch (_) {
        if (state.active && generation === state.generation) backupStatus('backup.permissions_failed');
    } finally {
        await finishBackupOperation();
    }
}

function backupCanStart(permission) {
    const state = BackupConsoleState;
    return state.active && !state.busy && !state.restored && !state.unsupported && state.permissions.has(permission);
}

function backupPassphraseValid(id) {
    const input = backupElement(id);
    const length = Array.from(input?.value || '').length;
    const valid = length >= 12 && length <= 256;
    input?.setAttribute('aria-invalid', String(!valid));
    if (!valid) backupStatus('backup.passphrase_invalid');
    return valid;
}

function backupImportValid() {
    if (!backupPassphraseValid('backupRestorePassphrase')) return false;
    const file = backupElement('backupArchive')?.files?.[0];
    if (!file || file.size <= 0 || file.size > MAX_BACKUP_UPLOAD_BYTES) {
        backupElement('backupArchive')?.setAttribute('aria-invalid', 'true');
        backupStatus('backup.file_invalid');
        return false;
    }
    backupElement('backupArchive')?.setAttribute('aria-invalid', 'false');
    if (!['abort_if_configured', 'replace'].includes(backupElement('backupConflictPolicy')?.value)) return false;
    return true;
}

function backupImportBody() {
    const body = new FormData();
    body.append('archive', backupElement('backupArchive').files[0]);
    body.append('passphrase', backupElement('backupRestorePassphrase').value);
    body.append('conflict_policy', backupElement('backupConflictPolicy').value);
    return body;
}

async function backupRequest(path, body, json = false) {
    const response = await fetch(`./api/backups${path}`, {
        method: 'POST', headers: getAuthHeaders(json), body, cache: 'no-store'
    });
    if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        const error = new Error('backup_request_failed');
        error.code = payload?.error?.code;
        error.status = response.status;
        throw error;
    }
    return response;
}

function backupError(error, restoring = false) {
    const keys = {
        backup_backend_unsupported: 'backup.unsupported',
        backup_restore_conflict: 'backup.conflict',
        backup_archive_too_large: 'backup.file_invalid',
        backup_archive_invalid: 'backup.archive_invalid'
    };
    if (error?.code === 'backup_backend_unsupported') BackupConsoleState.unsupported = true;
    if (error?.status === 401 || error?.status === 403) {
        BackupConsoleState.permissions.clear();
        backupElement('backupReauthenticate').hidden = error.status !== 401;
    }
    // A dropped response may follow a completed restore. Never infer rollback or retry it.
    backupStatus(restoring ? (keys[error?.code] || 'backup.restore_unknown')
        : (keys[error?.code] || (error?.status === 403 ? 'backup.denied' : 'backup.failed')));
}

async function finishBackupOperation() {
    BackupConsoleState.busy = false;
    if (!BackupConsoleState.active) clearBackupSecrets();
    if (BackupConsoleState.active && BackupConsoleState.reloadRequested && !BackupConsoleState.restored) {
        BackupConsoleState.reloadRequested = false;
        await loadBackupConsole();
        return;
    }
    BackupConsoleState.reloadRequested = false;
    renderBackupControls();
}

function renderBackupPlan(plan) {
    // Never render source strings, arbitrary table names, paths, or returned exception text.
    const counts = plan.table_counts;
    const count = ['audit_events', 'config', 'credentials', 'durable_usage_ledger',
        'durable_usage_migrations', 'identity_migrations', 'management_identities',
        'management_role_bindings', 'oidc_policy_revision', 'primary_credentials',
        'request_traces', 'durable_migration_checkpoints'].reduce((sum, key) => {
        const value = counts?.[key];
        return sum + (Number.isSafeInteger(value) && value >= 0 ? Math.min(value, 1e12) : 0);
    }, 0);
    BackupConsoleState.planSummary = { count, replace: plan.conflict_policy === 'replace' };
    renderBackupSummary();
}

function renderBackupSummary() {
    const container = backupElement('backupPlan');
    container.replaceChildren();
    const summary = BackupConsoleState.planSummary;
    if (!summary) return;
    for (const message of [t('backup.plan_ready'), t('backup.plan_records', { count: summary.count }),
        t(summary.replace ? 'backup.replace' : 'backup.abort')]) {
        const paragraph = document.createElement('p');
        paragraph.className = 'card-copy';
        paragraph.textContent = message;
        container.append(paragraph);
    }
}

async function validateBackupArchive() {
    if (!backupCanStart('backup.restore') || !backupImportValid()) return;
    const state = BackupConsoleState;
    state.validatedRevision = null;
    state.planSummary = null;
    backupElement('backupPlan')?.replaceChildren();
    const revision = state.revision;
    const generation = state.generation;
    state.busy = true;
    renderBackupControls();
    backupStatus('backup.validating');
    try {
        const response = await backupRequest('/validate', backupImportBody());
        const result = await response.json();
        if (!state.active || state.generation !== generation || state.revision !== revision) return;
        if (result?.dry_run !== true || result?.plan?.compatible !== true
            || result.plan.conflict_policy !== backupElement('backupConflictPolicy').value) {
            throw new Error('backup_invalid_plan');
        }
        state.validatedRevision = revision;
        renderBackupPlan(result.plan);
        backupStatus('backup.plan_ready');
    } catch (error) {
        if (state.active && state.generation === generation && state.revision === revision) backupError(error);
    } finally { await finishBackupOperation(); }
}

async function restoreBackupArchive() {
    const state = BackupConsoleState;
    if (!backupCanStart('backup.restore') || state.validatedRevision !== state.revision || !backupImportValid()) return;
    const generation = state.generation;
    const revision = state.revision;
    state.busy = true;
    renderBackupControls();
    try {
        const confirmed = await showConfirmModal(t('backup.confirm_restore'), {
            title: t('backup.restore'), confirmLabel: t('backup.restore')
        });
        if (!confirmed || !state.active || generation !== state.generation || revision !== state.revision) return;
        state.validatedRevision = null;
        state.planSummary = null;
        renderBackupSummary();
        backupStatus('backup.restoring');
        const response = await backupRequest('/restore', backupImportBody());
        const result = await response.json();
        if (result?.restored !== true) throw new Error('backup_restore_unconfirmed');
        clearBackupSecrets();
        state.restored = true;
        state.permissions.clear();
        if (state.active) {
            backupStatus('backup.restored');
            backupElement('backupReauthenticate').hidden = false;
        }
    } catch (error) {
        state.validatedRevision = null;
        if (state.active && generation === state.generation) backupError(error, true);
    } finally { await finishBackupOperation(); }
}

async function downloadBackupArchive(sanitized = false) {
    if (!backupCanStart('backup.export')) return;
    if (!sanitized) {
        if (!backupPassphraseValid('backupCreatePassphrase')) return;
        const match = backupElement('backupCreatePassphrase').value === backupElement('backupConfirmPassphrase').value;
        backupElement('backupConfirmPassphrase').setAttribute('aria-invalid', String(!match));
        if (!match) { backupStatus('backup.passphrase_mismatch'); return; }
    }
    const state = BackupConsoleState;
    const generation = state.generation;
    state.busy = true;
    renderBackupControls();
    backupStatus('backup.downloading');
    try {
        const body = sanitized ? undefined : JSON.stringify({ passphrase: backupElement('backupCreatePassphrase').value });
        const response = await backupRequest(sanitized ? '/sanitized-export' : '', body, !sanitized);
        const blob = await response.blob();
        if (!state.active || state.generation !== generation) return;
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = sanitized ? 'polaris-sanitized.json' : 'polaris-backup.ogb';
        document.body.append(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        if (!sanitized) {
            for (const id of ['backupCreatePassphrase', 'backupConfirmPassphrase']) {
                backupElement(id).value = '';
                backupElement(id).type = 'password';
                backupElement(`${id}Toggle`)?.setAttribute('aria-pressed', 'false');
            }
        }
        backupStatus('backup.downloaded');
    } catch (error) {
        if (state.active && state.generation === generation) backupError(error);
    } finally { await finishBackupOperation(); }
}

function initBackupBindings() {
    const section = backupElement('backupControls');
    if (!section || section.dataset.bound === 'true') return;
    section.dataset.bound = 'true';
    for (const id of ['backupArchive', 'backupRestorePassphrase', 'backupConflictPolicy']) {
        backupElement(id)?.addEventListener(id === 'backupRestorePassphrase' ? 'input' : 'change', backupInputsChanged);
    }
    for (const [id, handler] of [
        ['backupCreateForm', () => downloadBackupArchive()],
        ['backupImportForm', validateBackupArchive]
    ]) backupElement(id)?.addEventListener('submit', event => { event.preventDefault(); void handler(); });
    backupElement('backupRestore')?.addEventListener('click', () => { void restoreBackupArchive(); });
    backupElement('backupChooseArchive')?.addEventListener('click', () => {
        if (backupCanStart('backup.restore')) backupElement('backupArchive')?.click();
    });
    backupElement('backupSanitized')?.addEventListener('click', () => { void downloadBackupArchive(true); });
    document.addEventListener('polaris:locale-change', () => {
        renderBackupSummary();
        backupStatus(BackupConsoleState.statusKey);
    });
    renderBackupControls();
}
