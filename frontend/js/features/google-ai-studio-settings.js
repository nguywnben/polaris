async function loadGoogleAIStudioSettings(options = {}) {
    const field = document.getElementById('googleAiStudioApiUrl');
    if (!field) return;

    const preserveContent = options.preserveContent ?? field.dataset.loaded === 'true';

    setProviderSettingsLoading(
        ['googleAiStudioSettingsLoading'],
        ['googleAiStudioSettingsForm'],
        true,
        preserveContent
    );

    try {
        const response = await fetch('./api/providers/google-ai-studio/config', {
            headers: getAuthHeaders()
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw createProviderRequestError(response, data);
        }
        field.value = data.config?.google_ai_studio_api_url || '';
        field.dataset.loaded = 'true';
        applyProviderEnvironmentLocks('google-ai-studio.settings', data.env_locked);
    } catch (error) {
        showStatus(t('provider.settings_load_failed', {provider: 'Google AI Studio', error: error.message}), 'error');
    } finally {
        setProviderSettingsLoading(
            ['googleAiStudioSettingsLoading'],
            ['googleAiStudioSettingsForm'],
            false,
            preserveContent
        );
    }
}

async function saveGoogleAIStudioSettings() {
    const field = document.getElementById('googleAiStudioApiUrl');
    const apiUrl = field?.value.trim() || '';
    if (!validateProviderFormScope('google-ai-studio.settings')) return;

    try {
        const response = await fetch('./api/providers/google-ai-studio/config', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                config: { google_ai_studio_api_url: apiUrl }
            })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw createProviderRequestError(response, data);
        }
        showStatus(data.message || t('provider.settings_saved', {provider: 'Google AI Studio'}), 'success');
        await loadGoogleAIStudioSettings();
    } catch (error) {
        showStatus(t('provider.settings_save_failed', {provider: 'Google AI Studio', error: error.message}), 'error');
    }
}

async function resetGoogleAIStudioSettings() {
    const confirmed = await showConfirmModal(
        t('provider.reset_confirm', {provider: 'Google AI Studio'}),
        {
            title: t('confirm_reset_google_ai_studio_title'),
            confirmLabel: t('btn_reset_defaults')
        }
    );
    if (!confirmed) return;

    try {
        const response = await fetch('./api/providers/google-ai-studio/config/reset', {
            method: 'POST',
            headers: getAuthHeaders()
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw createProviderRequestError(response, data);
        }
        showStatus(data.message || t('provider.settings_reset', {provider: 'Google AI Studio'}), 'success');
        await loadGoogleAIStudioSettings();
    } catch (error) {
        showStatus(t('provider.settings_reset_failed', {provider: 'Google AI Studio', error: error.message}), 'error');
    }
}

async function addGoogleAIStudioCredential(event) {
    event?.preventDefault();
    const keyField = document.getElementById('googleAiStudioApiKey');
    const button = document.getElementById('addGoogleAiStudioKeyBtn');
    const apiKey = keyField?.value.trim() || '';

    if (!validateProviderFormScope('google-ai-studio.credential')) return;

    button.disabled = true;
    button.textContent = t('runtime.validating');
    document.getElementById('googleAiStudioSaveResult')?.classList.add('hidden');

    try {
        const response = await fetch('./api/providers/google-ai-studio/credentials', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ api_key: apiKey })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw createProviderRequestError(response, data);
        }

        const result = document.getElementById('googleAiStudioSaveResult');
        const title = document.getElementById('googleAiStudioSaveResultTitle');
        const text = document.getElementById('googleAiStudioSaveResultText');
        if (title) {
            title.textContent = t(data.credential_action === 'updated'
                ? 'runtime.credential_updated_title'
                : 'runtime.credential_added_title');
        }
        if (text) {
            text.textContent = `${data.message} ${t('runtime.models_available', {count: formatConsoleNumber(data.model_count)})}`;
        }
        result?.classList.remove('hidden');
        resetProviderTransientSecrets('google-ai-studio.credential');
        showStatus(data.message, 'success');
        await AppState.primaryCreds.refresh();
        await refreshUsageStats();
    } catch (error) {
        showStatus(t('provider.api_key_add_failed', {
            provider: 'Google AI Studio', error: formatProviderRequestError(error)
        }), 'error');
    } finally {
        button.disabled = false;
        button.textContent = t('runtime.validate_add');
    }
}
