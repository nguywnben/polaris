async function loadAntigravitySettings(options = {}) {

    const loading = document.getElementById('antigravitySettingsLoading');

    const form = document.getElementById('antigravitySettingsForm');

    const preserveContent = options.preserveContent ?? AppState.antigravityConfigLoaded;

    if (!loading || !form) return;

    try {

        if (!preserveContent) loading.hidden = false;

        if (!preserveContent) form.classList.add('hidden');

        const response = await fetch('./api/providers/antigravity/config', { headers: getAuthHeaders() });

        const data = await response.json();

        if (response.ok) {

            AppState.antigravityConfig = data.config || {};

            AppState.antigravityConfigLoaded = true;

            AppState.antigravityEnvLockedFields = new Set(data.env_locked || []);

            AppState.antigravityConfiguredSecrets = new Set(data.configured_secrets || []);

            populateAntigravitySettings();

            form.classList.remove('hidden');

        } else {

            showStatus(t('provider.settings_load_failed', {
                provider: 'Google Antigravity',
                error: data.detail || data.error || t('unknown_error')
            }), 'error');

        }

    } catch (error) {

        showStatus(t('status_net_error', {error: error.message}), 'error');

    } finally {

        loading.hidden = true;

    }

}

function populateAntigravitySettings() {

    const c = AppState.antigravityConfig || {};

    setAntigravityConfigField('antigravityOauthClientId', c.antigravity_client_id || '');

    const secretField = document.getElementById('antigravityOauthClientSecret');
    if (secretField) {
        secretField.value = '';
        secretField.dataset.secretConfigured = String(
            AppState.antigravityConfiguredSecrets?.has('antigravity_client_secret')
        );
        secretField.placeholder = secretField.dataset.secretConfigured === 'true'
            ? t('provider.form.client_secret_help')
            : '';
    }

    setAntigravityConfigField('antigravityApiUrl', c.antigravity_api_url || '');

    setAntigravityConfigField('antigravityOauthUrl', c.oauth_url || '');

    setAntigravityConfigField('antigravityGoogleApisUrl', c.google_apis_url || '');

    setAntigravityConfigField('antigravityResourceManagerUrl', c.resource_manager_url || '');

    setAntigravityConfigField('antigravityServiceUsageUrl', c.service_usage_url || '');

    setAntigravityConfigField('antigravityUserAgent', c.antigravity_user_agent || '');

    setAntigravityConfigField('antigravityPayloadUserAgent', c.antigravity_payload_user_agent || '');

    setAntigravityConfigCheckbox('antigravityStreamToNonstream', Boolean(c.stream_to_nonstream !== false));

    setAntigravityConfigCheckbox('antigravitySwitchCredential', Boolean(c.switch_credential_enabled));

    applyProviderEnvironmentLocks(
        'antigravity.settings',
        Array.from(AppState.antigravityEnvLockedFields || [])
    );

}

function setAntigravityConfigField(fieldId, value) {

    const field = document.getElementById(fieldId);

    if (!field) return;

    field.value = value;

    const configKey = ANTIGRAVITY_CONFIG_FIELD_KEYS[fieldId];

    const isLocked = AppState.antigravityEnvLockedFields.has(configKey);

    field.disabled = isLocked;

    field.classList.toggle('env-locked', isLocked);

}

function setAntigravityConfigCheckbox(fieldId, checked) {

    const field = document.getElementById(fieldId);

    if (!field) return;

    field.checked = checked;

    const configKey = ANTIGRAVITY_CONFIG_FIELD_KEYS[fieldId];

    const isLocked = AppState.antigravityEnvLockedFields.has(configKey);

    field.disabled = isLocked;

    field.classList.toggle('env-locked', isLocked);

    field.closest('.switch-row')?.classList.toggle('env-locked', isLocked);

}

async function saveAntigravitySettings() {

    try {

        if (!validateProviderFormScope('antigravity.settings')) return;

        const getValue = (id, def = '') => document.getElementById(id)?.value.trim() || def;

        const getChecked = (id, def = false) => {
            const field = document.getElementById(id);
            return field ? field.checked : def;
        };

        const config = {
            antigravity_client_id: getValue('antigravityOauthClientId'),
            antigravity_api_url: getValue('antigravityApiUrl'),
            oauth_url: getValue('antigravityOauthUrl'),
            google_apis_url: getValue('antigravityGoogleApisUrl'),
            resource_manager_url: getValue('antigravityResourceManagerUrl'),
            service_usage_url: getValue('antigravityServiceUsageUrl'),
            antigravity_user_agent: getValue('antigravityUserAgent'),
            antigravity_payload_user_agent: getValue('antigravityPayloadUserAgent'),
            stream_to_nonstream: getChecked('antigravityStreamToNonstream', true),
            switch_credential_enabled: getChecked('antigravitySwitchCredential')
        };

        const clientSecret = getValue('antigravityOauthClientSecret');
        if (clientSecret) config.antigravity_client_secret = clientSecret;

        const response = await fetch('./api/providers/antigravity/config', {

            method: 'POST',

            headers: getAuthHeaders(),

            body: JSON.stringify({ config })

        });

        const data = await response.json();

        if (response.ok) {

            showStatus(data.message || t('provider.settings_saved', {provider: 'Google Antigravity'}), 'success');

            setTimeout(() => loadAntigravitySettings(), 600);

        } else {

            showStatus(t('provider.settings_save_failed', {
                provider: 'Google Antigravity',
                error: data.detail || data.error || t('unknown_error')
            }), 'error');

        }

    } catch (error) {

        showStatus(t('status_net_error', {error: error.message}), 'error');

    }

}

async function resetAntigravitySettings() {

    const confirmed = await showConfirmModal(
        t('provider.reset_confirm', {provider: 'Google Antigravity'}),
        {
            title: t('confirm_reset_antigravity_title'),
            confirmLabel: t('btn_reset_defaults')
        }
    );

    if (!confirmed) return;

    try {

        const response = await fetch('./api/providers/antigravity/config/reset', {
            method: 'POST',
            headers: getAuthHeaders()
        });

        const data = await response.json().catch(() => ({}));

        if (response.ok) {

            showStatus(data.message || t('provider.settings_reset', {provider: 'Google Antigravity'}), 'success');

            AppState.antigravityConfig = data.config || {};

            AppState.antigravityEnvLockedFields = new Set(data.env_locked || []);

            AppState.antigravityConfiguredSecrets = new Set(data.configured_secrets || []);

            populateAntigravitySettings();

            setTimeout(() => loadAntigravitySettings(), 600);

        } else {

            showStatus(t('provider.settings_reset_failed', {
                provider: 'Google Antigravity',
                error: data.detail || data.error || t('unknown_error')
            }), 'error');

        }

    } catch (error) {

        showStatus(t('status_net_error', {error: error.message}), 'error');

    }

}

// =====================================================================

// =====================================================================
