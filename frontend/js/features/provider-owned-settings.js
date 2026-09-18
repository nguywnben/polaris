// Shared provider transports have one editor; loading a sibling must not discard drafts.
const googleSettingsState = {loaded: false, pending: null, locked: new Set()};
const GOOGLE_SECRET_CONFIG_KEYS = new Set(
    ['google.shared', 'google.compatibility'].flatMap(getProviderFormFields)
        .filter(definition => definition.secretLifetime !== 'none')
        .map(definition => definition.configKey)
);

async function loadGoogleProviderSettings(force = false) {
    if (googleSettingsState.pending) return googleSettingsState.pending;
    if (googleSettingsState.loaded && !force) return;
    googleSettingsState.pending = (async () => {
        const forms = [...document.querySelectorAll('[data-google-scope]')];
        forms.forEach(form => {
            form.inert = true;
            form.setAttribute('aria-busy', 'true');
            form.classList.toggle('is-initial-loading', !googleSettingsState.loaded);
        });
        try {
            const response = await fetch('./api/providers/google/config', {headers: getAuthHeaders()});
            const data = await response.json();
            if (!response.ok) throw createProviderRequestError(response, data);
            if (!data.config || typeof data.config !== 'object' || Array.isArray(data.config)) {
                throw new Error(t('unknown_error'));
            }
            googleSettingsState.locked = new Set(data.env_locked || []);
            forms.forEach(form => form.querySelectorAll('[data-google-config]').forEach(field => {
                const key = field.dataset.googleConfig;
                const secret = GOOGLE_SECRET_CONFIG_KEYS.has(key);
                field.value = secret ? '' : (data.config?.[key] || '');
                field.disabled = googleSettingsState.locked.has(key);
                field.classList.toggle('env-locked', field.disabled);
                if (secret) setSetupSecretVisibility(field, false);
            }));
            googleSettingsState.loaded = true;
        } catch (error) {
            showStatus(t('provider.settings_load_failed', {provider: 'Google', error: error.message}), 'error');
        } finally {
            forms.forEach(form => {
                form.inert = !googleSettingsState.loaded;
                form.removeAttribute('aria-busy');
            });
            googleSettingsState.pending = null;
        }
    })();
    return googleSettingsState.pending;
}

async function saveGoogleProviderSettings(form, reset = false) {
    if (!googleSettingsState.loaded || form.dataset.saving === 'true') return;
    const scope = form.dataset.googleScope;
    if (!reset && !validateProviderFormScope(`google.${scope}`)) return;
    if (reset && !await showConfirmModal(t('provider.reset_confirm', {provider: 'Google'}), {
        title: t('provider.reset_title', {provider: 'Google'}), confirmLabel: t('btn_reset_defaults')
    })) return;
    const fields = [...form.querySelectorAll('[data-google-config]')];
    const secretFields = fields.filter(field => GOOGLE_SECRET_CONFIG_KEYS.has(field.dataset.googleConfig));
    const config = {};
    for (const field of fields) {
        if (field.disabled) continue;
        const value = field.value.trim();
        if (!GOOGLE_SECRET_CONFIG_KEYS.has(field.dataset.googleConfig) || value) {
            config[field.dataset.googleConfig] = value;
        }
    }
    form.dataset.saving = 'true';
    form.inert = true;
    try {
        const url = reset ? `./api/providers/google/config/reset?scope=${scope}` : './api/providers/google/config';
        const response = await fetch(url, {method: 'POST', headers: getAuthHeaders(),
            ...(reset ? {} : {body: JSON.stringify({config})})});
        const data = await response.json();
        if (!response.ok) throw createProviderRequestError(response, data);
        // Only overwrite this scope after save/reset. The other editor may contain an unsaved draft.
        if (reset) {
            if (!data.config || typeof data.config !== 'object' || Array.isArray(data.config)
                || fields.some(field => !GOOGLE_SECRET_CONFIG_KEYS.has(field.dataset.googleConfig)
                    && (!Object.hasOwn(data.config, field.dataset.googleConfig)
                        || typeof data.config[field.dataset.googleConfig] !== 'string'))) {
                throw new Error(t('unknown_error'));
            }
            for (const field of fields) {
                if (!GOOGLE_SECRET_CONFIG_KEYS.has(field.dataset.googleConfig)) {
                    field.value = data.config[field.dataset.googleConfig];
                }
            }
        }
        secretFields.forEach(field => {
            field.value = ''; setSetupSecretVisibility(field, false);
        });
        showStatus(t(reset ? 'provider.settings_reset' : 'provider.settings_saved', {provider: 'Google'}), 'success');
    } catch (error) {
        secretFields.forEach(field => setSetupSecretVisibility(field, false));
        showStatus(t('provider.settings_save_failed', {provider: 'Google', error: error.message}), 'error');
    } finally {
        form.inert = false;
        delete form.dataset.saving;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-google-settings]').forEach(details => {
        details.querySelector('form').inert = true;
        details.addEventListener('toggle', () => {
            if (details.open) void loadGoogleProviderSettings();
        });
    });
});
document.addEventListener('submit', event => {
    if (!event.target.matches('[data-google-scope]')) return;
    event.preventDefault();
    void saveGoogleProviderSettings(event.target);
});
document.addEventListener('click', async event => {
    const link = event.target.closest('[data-provider-owned-link]');
    if (link) {
        const provider = link.dataset.providerOwnedLink;
        document.querySelector(`[data-ui-action="select-provider"][data-provider="${provider}"]`)?.click();
        const panelId = PROVIDER_ONBOARDING_VARIANTS[provider]?.panelId;
        const details = document.getElementById(panelId)?.querySelector('details');
        if (details) details.open = true;
        return;
    }
    const button = event.target.closest('[data-provider-owned-action]');
    if (!button || button.disabled) return;
    const action = button.dataset.providerOwnedAction;
    button.disabled = true;
    try {
        if (action === 'save-xai-shared') await saveXaiSettings('shared');
        if (action === 'reset-xai-shared') await resetXaiSettings('shared');
        if (action === 'reset-google') await saveGoogleProviderSettings(button.closest('form'), true);
    } finally { button.disabled = false; }
});
