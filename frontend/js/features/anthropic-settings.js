const ANTHROPIC_CONFIG_FIELDS = {
    anthropicApiUrlPlatform: 'anthropic_api_url',
    claudeAuthorizeUrl: 'claude_oauth_authorize_url',
    claudeTokenUrl: 'claude_oauth_token_url',
    claudeClientId: 'claude_client_id',
    claudeUserAgent: 'claude_user_agent'
};

const ANTHROPIC_CONFIG_GROUPS = {
    code: {
        label: 'Claude Code',
        formId: 'claudeCodeSettingsForm',
        resetTitle: 'Reset Claude Code Settings',
        fieldIds: ['claudeAuthorizeUrl', 'claudeTokenUrl', 'claudeClientId']
    },
    shared: {
        label: 'Claude Code / Claude Platform',
        formId: 'claudePlatformSettingsForm',
        fieldIds: ['anthropicApiUrlPlatform', 'claudeUserAgent']
    }
};

async function loadAnthropicSettings(options = {}) {
    if (!Object.keys(ANTHROPIC_CONFIG_FIELDS).some((fieldId) => document.getElementById(fieldId))) return;
    const loadingIds = ['claudeCodeSettingsLoading', 'claudePlatformSettingsLoading'];
    const formIds = ['claudeCodeSettingsForm', 'claudePlatformSettingsForm'];
    const preserveContent = options.preserveContent ?? formIds.some(
        (id) => document.getElementById(id)?.dataset.loaded === 'true'
    );
    setProviderSettingsLoading(loadingIds, formIds, true, preserveContent);
    formIds.forEach(id => {
        const form = document.getElementById(id);
        if (form && form.dataset.loaded !== 'true') form.inert = true;
    });
    try {
        const response = await fetch('./api/providers/anthropic/config', { headers: getAuthHeaders() });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw createProviderRequestError(response, data);
        if (!data.config || typeof data.config !== 'object' || Array.isArray(data.config)) {
            throw new Error(t('unknown_error'));
        }
        Object.entries(ANTHROPIC_CONFIG_FIELDS).forEach(([fieldId, configKey]) => {
            const field = document.getElementById(fieldId);
            if (!field) return;
            field.value = data.config?.[configKey] || '';
        });
        applyProviderEnvironmentLocks(['claude-code.settings', 'anthropic.shared'], data.env_locked);
        formIds.forEach((id) => {
            const form = document.getElementById(id);
            if (form) form.dataset.loaded = 'true';
        });
    } catch (error) {
        showStatus(t('provider.settings_load_failed', {provider: 'Anthropic', error: error.message}), 'error');
    } finally {
        setProviderSettingsLoading(loadingIds, formIds, false, preserveContent);
        formIds.forEach(id => {
            const form = document.getElementById(id);
            if (form) form.inert = form.dataset.loaded !== 'true';
        });
    }
}

async function saveAnthropicSettings(scope) {
    const group = ANTHROPIC_CONFIG_GROUPS[scope];
    if (!group) return;
    const form = document.getElementById(group.formId);
    if (form?.dataset.loaded !== 'true' || form.dataset.saving === 'true') return;
    const contractScope = scope === 'shared'
        ? 'anthropic.shared'
        : 'claude-code.settings';
    if (!validateProviderFormScope(contractScope)) return;
    const config = {};
    group.fieldIds.forEach((fieldId) => {
        const field = document.getElementById(fieldId);
        if (field && !field.disabled) config[ANTHROPIC_CONFIG_FIELDS[fieldId]] = field.value.trim();
    });
    form.dataset.saving = 'true';
    form.inert = true;
    try {
        const response = await fetch('./api/providers/anthropic/config', {
            method: 'POST', headers: getAuthHeaders(), body: JSON.stringify({ config })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw createProviderRequestError(response, data);
        showStatus(t('provider.settings_saved', {provider: group.label}), 'success');
    } catch (error) {
        showStatus(t('provider.settings_save_failed', {provider: group.label, error: error.message}), 'error');
    } finally {
        form.inert = false;
        delete form.dataset.saving;
    }
}

async function resetAnthropicSettings(scope) {
    const group = ANTHROPIC_CONFIG_GROUPS[scope];
    if (!group) return;
    const form = document.getElementById(group.formId);
    if (form?.dataset.loaded !== 'true' || form.dataset.saving === 'true') return;
    const confirmed = await showConfirmModal(
        t('provider.reset_confirm', {provider: group.label}),
        {
            title: t('provider.reset_title', {provider: group.label}),
            confirmLabel: t('btn_reset_defaults')
        }
    );
    if (!confirmed || form.dataset.saving === 'true') return;
    form.dataset.saving = 'true';
    form.inert = true;
    try {
        const response = await fetch(
            `./api/providers/anthropic/config/reset?scope=${encodeURIComponent(scope)}`,
            { method: 'POST', headers: getAuthHeaders() }
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw createProviderRequestError(response, data);
        showStatus(data.message || t('provider.settings_reset', {provider: group.label}), 'success');
        group.fieldIds.forEach(fieldId => {
            const field = document.getElementById(fieldId);
            const key = ANTHROPIC_CONFIG_FIELDS[fieldId];
            if (field && data.config && Object.hasOwn(data.config, key)) field.value = data.config[key];
        });
    } catch (error) {
        showStatus(t('provider.settings_reset_failed', {provider: group.label, error: error.message}), 'error');
    } finally {
        form.inert = false;
        delete form.dataset.saving;
    }
}

function showAnthropicCredentialSaveResult(kind, data) {
    const isCode = kind === 'code';
    const prefix = isCode ? 'claudeOauth' : 'claudePlatform';
    const title = document.getElementById(`${prefix}SaveResultTitle`);
    const text = document.getElementById(`${prefix}SaveResultText`);
    if (title) title.textContent = t(data.credential_action === 'updated'
        ? 'runtime.credential_updated_title'
        : 'runtime.credential_added_title');
    if (text) {
        const count = Number(data.model_count) || 0;
        text.textContent = `${data.message} ${t('runtime.models_available', {count: formatConsoleNumber(count)})}`;
    }
    document.getElementById(`${prefix}SaveResult`)?.classList.remove('hidden');
}

async function addClaudePlatformCredential(event) {
    event?.preventDefault();
    const field = document.getElementById('claudePlatformApiKey');
    const button = document.getElementById('addClaudePlatformKeyBtn');
    const apiKey = field?.value.trim() || '';
    if (!validateProviderFormScope('claude-platform.credential')) return;
    button.disabled = true;
    button.textContent = t('runtime.validating');
    document.getElementById('claudePlatformSaveResult')?.classList.add('hidden');
    try {
        const response = await fetch('./api/providers/anthropic/platform/credentials', {
            method: 'POST', headers: getAuthHeaders(), body: JSON.stringify({ api_key: apiKey })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw createProviderRequestError(response, data);
        resetProviderTransientSecrets('claude-platform.credential');
        showAnthropicCredentialSaveResult('platform', data);
        showStatus(data.message, 'success');
        await AppState.primaryCreds.refresh();
        await loadModelCatalog(true);
        await refreshUsageStats();
    } catch (error) {
        showStatus(t('provider.api_key_add_failed', {
            provider: 'Claude Platform', error: formatProviderRequestError(error)
        }), 'error');
    } finally {
        button.disabled = false;
        button.textContent = t('runtime.validate_add');
    }
}

async function startClaudeOauth() {
    const button = document.getElementById('startClaudeOauthBtn');
    button.disabled = true;
    button.textContent = t('runtime.generating');
    document.getElementById('claudeOauthSaveResult')?.classList.add('hidden');
    try {
        const response = await fetch('./api/providers/anthropic/claude-code/oauth/start', {
            method: 'POST', headers: getAuthHeaders()
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw createProviderRequestError(response, data);
        const fields = document.getElementById('claudeOauthFields');
        const link = document.getElementById('claudeAuthorizationUrl');
        if (fields) {
            fields.dataset.oauthState = data.state || '';
            fields.classList.remove('hidden');
        }
        if (link) {
            link.href = data.auth_url || '#';
            link.textContent = data.auth_url || t('runtime.authorization_unavailable');
        }
        document.getElementById('claudeAuthorizationCode').value = '';
        showStatus(t('provider.auth_ready', {provider: 'Claude Code'}), 'success');
    } catch (error) {
        showStatus(t('provider.auth_start_failed', {
            provider: 'Claude Code', error: formatProviderRequestError(error)
        }), 'error');
    } finally {
        button.disabled = false;
        button.textContent = t('runtime.get_provider_auth');
    }
}

async function saveClaudeOauth() {
    const fields = document.getElementById('claudeOauthFields');
    const field = document.getElementById('claudeAuthorizationCode');
    const button = document.getElementById('saveClaudeOauthBtn');
    const code = field?.value.trim() || '';
    const state = fields?.dataset.oauthState || '';
    if (!validateProviderFormScope('claude-code.oauth')) return;
    if (!state) {
        showStatus(t('provider.auth_session_required', {provider: 'Claude Code'}), 'error');
        return;
    }
    button.disabled = true;
    button.textContent = t('runtime.saving');
    try {
        const response = await fetch('./api/providers/anthropic/claude-code/oauth/complete', {
            method: 'POST', headers: getAuthHeaders(), body: JSON.stringify({ code, state })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw createProviderRequestError(response, data);
        delete fields.dataset.oauthState;
        resetProviderTransientSecrets('claude-code.oauth');
        showAnthropicCredentialSaveResult('code', data);
        showStatus(data.message, 'success');
        await AppState.primaryCreds.refresh();
        await loadModelCatalog(true);
        await refreshUsageStats();
    } catch (error) {
        showStatus(t('provider.credential_save_failed', {
            provider: 'Claude Code', error: formatProviderRequestError(error)
        }), 'error');
    } finally {
        button.disabled = false;
        button.textContent = t('runtime.save_credential');
    }
}

function handleClaudeCodeFileSelect(event) { AppState.claudeCodeUploadFiles.handleFileSelect(event); }
function handleClaudeCodeFileDrop(event) { event.preventDefault(); event.currentTarget.classList.remove('dragover'); AppState.claudeCodeUploadFiles.addFiles(Array.from(event.dataTransfer.files)); }
function clearClaudeCodeFiles() { AppState.claudeCodeUploadFiles.clearFiles(); }
function uploadClaudeCodeFiles() { AppState.claudeCodeUploadFiles.upload(); }
function handleClaudePlatformFileSelect(event) { AppState.claudePlatformUploadFiles.handleFileSelect(event); }
function handleClaudePlatformFileDrop(event) { event.preventDefault(); event.currentTarget.classList.remove('dragover'); AppState.claudePlatformUploadFiles.addFiles(Array.from(event.dataTransfer.files)); }
function clearClaudePlatformFiles() { AppState.claudePlatformUploadFiles.clearFiles(); }
function uploadClaudePlatformFiles() { AppState.claudePlatformUploadFiles.upload(); }
