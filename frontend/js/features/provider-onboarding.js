const PROVIDER_CAPABILITY_SCHEMA_VERSION = 2;
const PROVIDER_REQUIRED_OPERATIONS = Object.freeze([
    'add', 'test', 'model_discovery', 'disable', 'delete'
]);

const PROVIDER_ONBOARDING_VARIANTS = PROVIDER_WORKSPACES;

const PROVIDER_SETTINGS_LOADERS = Object.freeze({
    antigravity: () => loadAntigravitySettings(),
    'google-ai-studio': () => loadGoogleAIStudioSettings(),
    xai: () => loadXaiSettings(),
    openai: () => loadOpenAISettings(),
    anthropic: () => loadAnthropicSettings()
});

const PROVIDER_SETTINGS_LOADED = Object.freeze({
    antigravity: () => AppState.antigravityConfigLoaded === true,
    'google-ai-studio': () => document.getElementById('googleAiStudioApiUrl')?.dataset.loaded === 'true',
    xai: () => document.getElementById('xaiSettingsForm')?.dataset.loaded === 'true',
    openai: () => document.getElementById('openaiPlatformSettingsForm')?.dataset.loaded === 'true',
    anthropic: () => document.getElementById('claudePlatformSettingsForm')?.dataset.loaded === 'true'
});

let providerCapabilityPromise = null;
let providerCapabilityByVariant = Object.create(null);
const providerSettingsPromises = new Map();

function getProviderCapabilityLabel(credentialType) {
    if (credentialType === 'oauth') return 'OAuth';
    if (credentialType === 'api_key') return 'API Key';
    if (credentialType === 'connection') return t('provider.form.endpoint_label');
    return credentialType;
}

function validateProviderCapabilityPayload(payload) {
    if (!payload || payload.schema_version !== PROVIDER_CAPABILITY_SCHEMA_VERSION) {
        throw new TypeError('provider-capability-schema');
    }
    if (!Array.isArray(payload.credential_variants)) {
        throw new TypeError('provider-capability-variants');
    }
    const operationVocabulary = new Set(payload.operation_vocabulary || []);
    const variants = Object.create(null);
    payload.credential_variants.forEach((variant) => {
        if (!variant || typeof variant.variant_id !== 'string'
            || typeof variant.display_name !== 'string'
            || !['oauth', 'api_key', 'connection'].includes(variant.credential_type)
            || !Array.isArray(variant.operations)
            || variant.operations.some((operation) => !operationVocabulary.has(operation))) {
            throw new TypeError('provider-capability-entry');
        }
        variants[variant.variant_id] = variant;
    });
    Object.keys(PROVIDER_ONBOARDING_VARIANTS).forEach((variantId) => {
        const variant = variants[variantId];
        if (!variant || PROVIDER_REQUIRED_OPERATIONS.some(
            (operation) => !variant.operations.includes(operation)
        )) {
            throw new TypeError('provider-capability-incomplete');
        }
    });
    return variants;
}

function renderProviderCapabilityBadges() {
    Object.entries(PROVIDER_ONBOARDING_VARIANTS).forEach(([variantId, definition]) => {
        const capability = providerCapabilityByVariant[variantId];
        const selector = document.getElementById(definition.selectorId);
        const badges = selector?.querySelector('.provider-capabilities');
        if (!capability || !selector || !badges) return;

        const labels = [getProviderCapabilityLabel(capability.credential_type)];
        if (capability.operations.includes('test')) labels.push(t('providers.connection_test'));
        if (capability.operations.includes('model_discovery')) labels.push(t('providers.model_discovery'));
        badges.replaceChildren(...labels.map((label) => {
            const badge = document.createElement('span');
            badge.textContent = label;
            return badge;
        }));
        badges.setAttribute('aria-label', capability.display_name);
        selector.dataset.capabilityState = 'ready';
    });
}

function setProviderCapabilityStatus(state, error = null) {
    const container = document.getElementById('providerCapabilityStatus');
    const text = document.getElementById('providerCapabilityStatusText');
    const retry = document.getElementById('providerCapabilityRetryBtn');
    if (!container || !text || !retry) return;
    container.dataset.state = state;
    container.classList.toggle('hidden', state === 'ready');
    retry.classList.toggle('hidden', state !== 'failed');
    if (state === 'loading') text.textContent = t('providers.capabilities_loading');
    if (state === 'ready') {
        text.textContent = t('providers.capabilities_ready', {
            count: Object.keys(PROVIDER_ONBOARDING_VARIANTS).length
        });
    }
    if (state === 'failed') {
        text.textContent = t('providers.capabilities_failed');
        if (error) console.warn('Provider capability catalog could not be refreshed.', error);
    }
}

async function loadProviderCapabilities({force = false} = {}) {
    if (providerCapabilityPromise && !force) return providerCapabilityPromise;
    setProviderCapabilityStatus('loading');
    providerCapabilityPromise = (async () => {
        const response = await fetch('./api/providers/capabilities', {headers: getAuthHeaders()});
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.detail || payload.error || t('unknown_error'));
        providerCapabilityByVariant = validateProviderCapabilityPayload(payload);
        renderProviderCapabilityBadges();
        setProviderCapabilityStatus('ready');
        return providerCapabilityByVariant;
    })().catch((error) => {
        providerCapabilityPromise = null;
        setProviderCapabilityStatus('failed', error);
        throw error;
    });
    return providerCapabilityPromise;
}

async function loadProviderWorkspaceSettings(providerId) {
    const family = PROVIDER_ONBOARDING_VARIANTS[providerId]?.settingsFamily;
    const loader = family ? PROVIDER_SETTINGS_LOADERS[family] : null;
    if (!loader) return;
    if (PROVIDER_SETTINGS_LOADED[family]?.()) return;
    if (!providerSettingsPromises.has(family)) {
        const promise = Promise.resolve().then(loader).finally(() => {
            providerSettingsPromises.delete(family);
        });
        providerSettingsPromises.set(family, promise);
    }
    return providerSettingsPromises.get(family);
}

function presentProviderImportPanel(panel) {
    if (!panel) return;
    panel.classList.add('provider-import-panel');
    const title = panel.querySelector(':scope > .card-title');
    if (!title) return;
    title.dataset.providerStaticLabel = 'import';
    title.textContent = t('providers.import_credentials');
}

function createProviderDisclosure(panel, {providerId}) {
    if (!panel || panel.matches('details')) return panel;
    const details = document.createElement('details');
    details.className = `${panel.className} provider-secondary-disclosure`;
    details.dataset.disclosureKind = 'settings';

    const summary = document.createElement('summary');
    summary.className = 'provider-disclosure-summary';
    summary.dataset.providerDisclosureLabel = 'settings';
    summary.textContent = t('providers.advanced_settings');
    details.appendChild(summary);
    while (panel.firstChild) details.appendChild(panel.firstChild);
    panel.replaceWith(details);

    details.addEventListener('toggle', () => {
        if (details.open) void loadProviderWorkspaceSettings(providerId);
    });
    return details;
}

function enhanceProviderWorkspaces() {
    Object.entries(PROVIDER_ONBOARDING_VARIANTS).forEach(([providerId, definition]) => {
        const workspace = document.getElementById(definition.panelId);
        const tools = workspace?.querySelector(':scope > .provider-tools-grid');
        const importPanel = tools?.querySelector(':scope > .tool-panel:nth-child(2)');
        presentProviderImportPanel(importPanel);

        const settingsPanel = workspace?.querySelector(
            '.provider-settings-panel, .provider-advanced-panel'
        );
        createProviderDisclosure(settingsPanel, {providerId});
    });
}

async function loadProviderOnboarding(options = {}) {
    enhanceProviderWorkspaces();
    try {
        return await loadProviderCapabilities(options);
    } catch (_error) {
        return providerCapabilityByVariant;
    }
}

function retryProviderCapabilities() {
    void loadProviderOnboarding({force: true});
}

function refreshProviderOnboardingCopy() {
    document.querySelectorAll('[data-provider-static-label="import"]').forEach((title) => {
        title.textContent = t('providers.import_credentials');
    });
    document.querySelectorAll('[data-provider-disclosure-label]').forEach((summary) => {
        summary.textContent = t('providers.advanced_settings');
    });
    if (Object.keys(providerCapabilityByVariant).length) renderProviderCapabilityBadges();
    const state = document.getElementById('providerCapabilityStatus')?.dataset.state;
    if (state) setProviderCapabilityStatus(state);
}

document.addEventListener('DOMContentLoaded', enhanceProviderWorkspaces, {once: true});
document.addEventListener('polaris:locale-change', refreshProviderOnboardingCopy);
