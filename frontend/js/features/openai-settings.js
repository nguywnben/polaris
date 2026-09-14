const OPENAI_CONFIG_FIELDS = {
    openaiApiUrl: 'openai_api_url',
    codexApiUrl: 'codex_api_url',
    codexUsageUrl: 'codex_usage_url',
    codexAuthBase: 'codex_auth_base',
    codexClientId: 'codex_client_id',
    codexUserAgent: 'codex_user_agent'
};

const OPENAI_CONFIG_GROUPS = {
    platform: {
        label: 'OpenAI Platform',
        resetTitle: 'Reset OpenAI Platform Settings',
        fieldIds: ['openaiApiUrl']
    },
    codex: {
        label: 'Codex',
        resetTitle: 'Reset Codex Settings',
        fieldIds: ['codexApiUrl', 'codexUsageUrl', 'codexAuthBase', 'codexClientId', 'codexUserAgent']
    }
};

async function loadOpenAISettings(options = {}) {
    if (!Object.keys(OPENAI_CONFIG_FIELDS).some((fieldId) => document.getElementById(fieldId))) {
        return;
    }

    const loadingIds = ['codexSettingsLoading', 'openaiPlatformSettingsLoading'];
    const formIds = ['codexSettingsForm', 'openaiPlatformSettingsForm'];
    const preserveContent = options.preserveContent ?? formIds.some(
        (id) => document.getElementById(id)?.dataset.loaded === 'true'
    );
    setProviderSettingsLoading(loadingIds, formIds, true, preserveContent);

    try {
        const response = await fetch('./api/providers/openai/config', {
            headers: getAuthHeaders()
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw createProviderRequestError(response, data);

        Object.entries(OPENAI_CONFIG_FIELDS).forEach(([fieldId, configKey]) => {
            const field = document.getElementById(fieldId);
            if (!field) return;
            field.value = data.config?.[configKey] || '';
        });
        applyProviderEnvironmentLocks(['codex.settings', 'openai-platform.settings'], data.env_locked);
        formIds.forEach((id) => {
            const form = document.getElementById(id);
            if (form) form.dataset.loaded = 'true';
        });
    } catch (error) {
        showStatus(t('provider.settings_load_failed', {provider: 'OpenAI', error: error.message}), 'error');
    } finally {
        setProviderSettingsLoading(loadingIds, formIds, false, preserveContent);
    }
}

async function saveOpenAISettings(scope) {
    const group = OPENAI_CONFIG_GROUPS[scope];
    if (!group) return;
    const contractScope = scope === 'platform' ? 'openai-platform.settings' : 'codex.settings';
    if (!validateProviderFormScope(contractScope)) return;
    const config = {};
    group.fieldIds.forEach((fieldId) => {
        const configKey = OPENAI_CONFIG_FIELDS[fieldId];
        const field = document.getElementById(fieldId);
        if (field && !field.disabled) config[configKey] = field.value.trim();
    });

    try {
        const response = await fetch('./api/providers/openai/config', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ config })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw createProviderRequestError(response, data);
        showStatus(t('provider.settings_saved', {provider: group.label}), 'success');
        await loadOpenAISettings();
    } catch (error) {
        showStatus(t('provider.settings_save_failed', {provider: group.label, error: error.message}), 'error');
    }
}

async function resetOpenAISettings(scope) {
    const group = OPENAI_CONFIG_GROUPS[scope];
    if (!group) return;
    const confirmed = await showConfirmModal(
        t('provider.reset_confirm', {provider: group.label}),
        {
            title: t('provider.reset_title', {provider: group.label}),
            confirmLabel: t('btn_reset_defaults')
        }
    );
    if (!confirmed) return;

    try {
        const response = await fetch(
            `./api/providers/openai/config/reset?scope=${encodeURIComponent(scope)}`,
            { method: 'POST', headers: getAuthHeaders() }
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw createProviderRequestError(response, data);
        showStatus(data.message || t('provider.settings_reset', {provider: group.label}), 'success');
        await loadOpenAISettings();
    } catch (error) {
        showStatus(t('provider.settings_reset_failed', {provider: group.label, error: error.message}), 'error');
    }
}

function showOpenAICredentialSaveResult(kind, data) {
    const isCodex = kind === 'codex';
    const prefix = isCodex ? 'codexOauth' : 'openaiPlatform';
    const result = document.getElementById(`${prefix}SaveResult`);
    const title = document.getElementById(`${prefix}SaveResultTitle`);
    const text = document.getElementById(`${prefix}SaveResultText`);
    if (title) {
        title.textContent = t(data.credential_action === 'updated'
            ? 'runtime.credential_updated_title'
            : 'runtime.credential_added_title');
    }
    if (text) {
        const modelCount = Number(data.model_count) || 0;
        text.textContent = `${data.message} ${t('runtime.models_available', {count: formatConsoleNumber(modelCount)})}`;
    }
    result?.classList.remove('hidden');
}

async function addOpenAIPlatformCredential(event) {
    event?.preventDefault();
    const field = document.getElementById('openaiPlatformApiKey');
    const button = document.getElementById('addOpenaiPlatformKeyBtn');
    const apiKey = field?.value.trim() || '';
    if (!validateProviderFormScope('openai-platform.credential')) return;

    button.disabled = true;
    button.textContent = t('runtime.validating');
    document.getElementById('openaiPlatformSaveResult')?.classList.add('hidden');
    try {
        const response = await fetch('./api/providers/openai/platform/credentials', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ api_key: apiKey })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw createProviderRequestError(response, data);
        resetProviderTransientSecrets('openai-platform.credential');
        showOpenAICredentialSaveResult('platform', data);
        showStatus(data.message, 'success');
        await AppState.primaryCreds.refresh();
        await loadModelCatalog(true);
        await refreshUsageStats();
    } catch (error) {
        showStatus(t('provider.api_key_add_failed', {
            provider: 'OpenAI Platform', error: formatProviderRequestError(error)
        }), 'error');
    } finally {
        button.disabled = false;
        button.textContent = t('runtime.validate_add');
    }
}

async function startCodexOauth() {
    const button = document.getElementById('startCodexOauthBtn');
    button.disabled = true;
    button.textContent = t('runtime.generating');
    document.getElementById('codexOauthSaveResult')?.classList.add('hidden');
    try {
        const response = await fetch('./api/providers/openai/codex/oauth/start', {
            method: 'POST',
            headers: getAuthHeaders()
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw createProviderRequestError(response, data);

        const fields = document.getElementById('codexOauthFields');
        const code = document.getElementById('codexUserCode');
        const verification = document.getElementById('codexVerificationUrl');
        if (fields) {
            fields.dataset.flowId = data.flow_id || '';
            fields.dataset.pollInterval = String(data.interval || 5);
            fields.classList.remove('hidden');
        }
        if (code) code.textContent = data.user_code || t('runtime.code_unavailable');
        if (verification) {
            verification.href = data.verification_uri || '#';
            verification.textContent = data.verification_uri || t('runtime.verification_unavailable');
        }
        showStatus(t('provider.device_code_ready', {provider: 'Codex'}), 'success');
    } catch (error) {
        showStatus(t('provider.auth_start_failed', {
            provider: 'Codex', error: formatProviderRequestError(error)
        }), 'error');
    } finally {
        button.disabled = false;
        button.textContent = t('runtime.get_authorization_code');
    }
}

async function completeCodexOauth() {
    const fields = document.getElementById('codexOauthFields');
    const flowId = fields?.dataset.flowId || '';
    const button = document.getElementById('completeCodexOauthBtn');
    if (!flowId) {
        showStatus(t('provider.auth_session_required', {provider: 'Codex'}), 'error');
        return;
    }

    button.disabled = true;
        button.textContent = t('runtime.checking');
    try {
        const response = await fetch('./api/providers/openai/codex/oauth/complete', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ flow_id: flowId })
        });
        const data = await response.json().catch(() => ({}));
        if (response.status === 202 && data.pending) {
            showStatus(data.message || t('provider.authorization_pending', {provider: 'Codex'}), 'info');
            return;
        }
        if (!response.ok) throw createProviderRequestError(response, data);

        delete fields.dataset.flowId;
        showOpenAICredentialSaveResult('codex', data);
        showStatus(data.message, 'success');
        await AppState.primaryCreds.refresh();
        await loadModelCatalog(true);
        await refreshUsageStats();
    } catch (error) {
        showStatus(t('provider.credential_save_failed', {
            provider: 'Codex', error: formatProviderRequestError(error)
        }), 'error');
    } finally {
        button.disabled = false;
        button.textContent = t('runtime.check_authorization');
    }
}

function handleCodexFileSelect(event) {
    AppState.codexUploadFiles.handleFileSelect(event);
}

function handleCodexFileDrop(event) {
    event.preventDefault();
    event.currentTarget.classList.remove('dragover');
    AppState.codexUploadFiles.addFiles(Array.from(event.dataTransfer.files));
}

function clearCodexFiles() {
    AppState.codexUploadFiles.clearFiles();
}

function uploadCodexFiles() {
    AppState.codexUploadFiles.upload();
}

function handleOpenAIPlatformFileSelect(event) {
    AppState.openaiPlatformUploadFiles.handleFileSelect(event);
}

function handleOpenAIPlatformFileDrop(event) {
    event.preventDefault();
    event.currentTarget.classList.remove('dragover');
    AppState.openaiPlatformUploadFiles.addFiles(Array.from(event.dataTransfer.files));
}

function clearOpenAIPlatformFiles() {
    AppState.openaiPlatformUploadFiles.clearFiles();
}

function uploadOpenAIPlatformFiles() {
    AppState.openaiPlatformUploadFiles.upload();
}
