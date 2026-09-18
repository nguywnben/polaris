const XAI_CONFIG_FIELDS = {
    grokApiUrl: 'xai_oauth_api_url',
    xaiClientId: 'xai_client_id',
    xaiOauthIssuer: 'xai_oauth_issuer',
    xaiApiUrl: 'xai_api_url',
    xaiUserAgent: 'xai_user_agent'
};

const XAI_CONFIG_GROUPS = {
    oauth: {
        label: 'Grok Build',
        formId: 'grokSettingsForm',
        fieldIds: ['xaiClientId', 'xaiOauthIssuer', 'grokApiUrl']
    },
    api: {
        label: 'SpaceXAI Console',
        formId: 'xaiConsoleSettingsForm',
        fieldIds: ['xaiApiUrl']
    },
    shared: {
        label: 'Grok Build / SpaceXAI Console',
        formId: 'xaiSharedSettingsForm',
        fieldIds: ['xaiUserAgent']
    }
};

async function loadXaiSettings(options = {}) {
    if (!Object.keys(XAI_CONFIG_FIELDS).some(fieldId => document.getElementById(fieldId))) return;

    const loadingIds = ['grokSettingsLoading', 'xaiConsoleSettingsLoading'];
    const formIds = ['grokSettingsForm', 'xaiConsoleSettingsForm', 'xaiSharedSettingsForm'];
    const preserveContent = options.preserveContent ?? formIds.some(
        id => document.getElementById(id)?.dataset.loaded === 'true'
    );
    setProviderSettingsLoading(loadingIds, formIds, true, preserveContent);
    formIds.forEach(id => {
        const form = document.getElementById(id);
        if (form && form.dataset.loaded !== 'true') form.inert = true;
    });

    try {
        const response = await fetch('./api/providers/xai/config', { headers: getAuthHeaders() });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw createProviderRequestError(response, data);
        if (!data.config || typeof data.config !== 'object' || Array.isArray(data.config)) {
            throw new Error(t('unknown_error'));
        }
        Object.entries(XAI_CONFIG_FIELDS).forEach(([fieldId, configKey]) => {
            const field = document.getElementById(fieldId);
            if (!field) return;
            field.value = data.config?.[configKey] || '';
        });
        applyProviderEnvironmentLocks(['grok.settings', 'xai.settings', 'xai.shared'], data.env_locked);
        formIds.forEach((id) => {
            const form = document.getElementById(id);
            if (form) form.dataset.loaded = 'true';
        });
    } catch (error) {
        showStatus(t('provider.settings_load_failed', {provider: 'Grok Build / SpaceXAI Console', error: error.message}), 'error');
    } finally {
        setProviderSettingsLoading(loadingIds, formIds, false, preserveContent);
        formIds.forEach(id => {
            const form = document.getElementById(id);
            if (form) form.inert = form.dataset.loaded !== 'true';
        });
    }
}

async function saveXaiSettings(scope) {
    const group = XAI_CONFIG_GROUPS[scope];
    if (!group) return;
    const form = document.getElementById(group.formId);
    if (form?.dataset.loaded !== 'true' || form.dataset.saving === 'true') return;
    const contractScope = scope === 'oauth' ? 'grok.settings' : scope === 'shared' ? 'xai.shared' : 'xai.settings';
    if (!validateProviderFormScope(contractScope)) return;
    const config = {};
    group.fieldIds.forEach((fieldId) => {
        const configKey = XAI_CONFIG_FIELDS[fieldId];
        const field = document.getElementById(fieldId);
        if (field && !field.disabled) config[configKey] = field.value.trim();
    });
    form.dataset.saving = 'true';
    form.inert = true;
    try {
        const response = await fetch('./api/providers/xai/config', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ config })
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

async function resetXaiSettings(scope) {
    const group = XAI_CONFIG_GROUPS[scope];
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
        const response = await fetch(`./api/providers/xai/config/reset?scope=${encodeURIComponent(scope)}`, {
            method: 'POST',
            headers: getAuthHeaders()
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw createProviderRequestError(response, data);
        showStatus(data.message || t('provider.settings_reset', {provider: group.label}), 'success');
        group.fieldIds.forEach(fieldId => {
            const field = document.getElementById(fieldId);
            const key = XAI_CONFIG_FIELDS[fieldId];
            if (field && data.config && Object.hasOwn(data.config, key)) field.value = data.config[key];
        });
    } catch (error) {
        showStatus(t('provider.settings_reset_failed', {provider: group.label, error: error.message}), 'error');
    } finally {
        form.inert = false;
        delete form.dataset.saving;
    }
}

function showXaiCredentialSaveResult(kind, data) {
    const isOauth = kind === 'oauth';
    const prefix = isOauth ? 'xaiOauth' : 'xaiApiKey';
    showProviderCredentialSaveResult(prefix, data);
}

async function addXaiApiKeyCredential(event) {
    event?.preventDefault();
    const field = document.getElementById('xaiApiKey');
    const button = document.getElementById('addXaiKeyBtn');
    const apiKey = field?.value.trim() || '';
    if (!validateProviderFormScope('xai.credential')) return;
    button.disabled = true;
    button.textContent = t('runtime.validating');
    document.getElementById('xaiApiKeySaveResult')?.classList.add('hidden');
    try {
        const response = await fetch('./api/providers/xai/credentials', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ api_key: apiKey })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw createProviderRequestError(response, data);
        resetProviderTransientSecrets('xai.credential');
        showXaiCredentialSaveResult('api-key', data);
        showStatus(providerCredentialResultCopy(data).title, 'success');
        await AppState.primaryCreds.refresh();
        await loadModelCatalog(true);
        await refreshUsageStats();
    } catch (error) {
        showStatus(t('provider.api_key_add_failed', {
            provider: 'SpaceXAI Console', error: formatProviderRequestError(error)
        }), 'error');
    } finally {
        button.disabled = false;
        button.textContent = t('provider.ui.add_key');
    }
}

async function startXaiOauth() {
    const button = document.getElementById('startXaiOauthBtn');
    button.disabled = true;
    button.textContent = t('runtime.generating');
    document.getElementById('xaiOauthSaveResult')?.classList.add('hidden');
    try {
        const response = await fetch('./api/providers/xai/oauth/start', {
            method: 'POST',
            headers: getAuthHeaders()
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw createProviderRequestError(response, data);
        const authorizationLink = document.getElementById('xaiAuthorizationUrl');
        authorizationLink.href = data.auth_url || '#';
        authorizationLink.textContent = data.auth_url || t('runtime.authorization_unavailable');
        document.getElementById('xaiAuthorizationCode').value = '';
        const oauthFields = document.getElementById('xaiOauthFields');
        if (oauthFields) {
            oauthFields.dataset.state = data.state || '';
            oauthFields.classList.remove('hidden');
        }
        showStatus(t('provider.auth_ready', {provider: 'Grok Build'}), 'success');
    } catch (error) {
        showStatus(t('provider.auth_start_failed', {
            provider: 'Grok Build', error: formatProviderRequestError(error)
        }), 'error');
    } finally {
        button.disabled = false;
        button.textContent = t('runtime.get_provider_auth');
    }
}

async function saveXaiOauth() {
    const field = document.getElementById('xaiAuthorizationCode');
    const button = document.getElementById('saveXaiOauthBtn');
    const code = field?.value.trim() || '';
    const oauthFields = document.getElementById('xaiOauthFields');
    const state = oauthFields?.dataset.state || '';
    if (!validateProviderFormScope('grok.oauth')) return;
    if (!state) {
        showStatus(t('provider.auth_session_required', {provider: 'Grok Build'}), 'error');
        return;
    }
    button.disabled = true;
    button.textContent = t('runtime.saving');
    try {
        const response = await fetch('./api/providers/xai/oauth/complete', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ code, state })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw createProviderRequestError(response, data);
        resetProviderTransientSecrets('grok.oauth');
        delete oauthFields.dataset.state;
        showXaiCredentialSaveResult('oauth', data);
        showStatus(providerCredentialResultCopy(data).title, 'success');
        await AppState.primaryCreds.refresh();
        await loadModelCatalog(true);
        await refreshUsageStats();
    } catch (error) {
        showStatus(t('provider.credential_save_failed', {
            provider: 'Grok Build', error: formatProviderRequestError(error)
        }), 'error');
    } finally {
        button.disabled = false;
        button.textContent = t('runtime.save_credential');
    }
}

const ANTIGRAVITY_CONFIG_FIELD_KEYS = {
    antigravityOauthClientId: 'antigravity_client_id',
    antigravityOauthClientSecret: 'antigravity_client_secret',
    antigravityApiUrl: 'antigravity_api_url',
    antigravityUserAgent: 'antigravity_user_agent',
    antigravityPayloadUserAgent: 'antigravity_payload_user_agent',
};
