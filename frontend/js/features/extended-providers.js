// Provider-specific connection metadata stays with each key, never in System Settings.
const EXTENDED_PROVIDER_UI = Object.freeze({
    kimi: {name: 'Kimi API Platform', logo: 'kimi-api-platform.png', site: 'https://platform.kimi.ai/', base: 'https://api.moonshot.ai/v1'},
    kiro: {name: 'Kiro', logo: 'kiro-logo.png', site: 'https://kiro.dev/'},
    cloudflare: {name: 'Cloudflare Workers AI', logo: 'cloudflare-logo.png', site: 'https://www.cloudflare.com/products/workers-ai/', base: 'https://api.cloudflare.com/client/v4'},
    nvidia: {name: 'NVIDIA NIM', logo: 'nvidia-logo.png', site: 'https://developer.nvidia.com/nim', base: 'https://integrate.api.nvidia.com/v1'},
    opencode: {name: 'OpenCode', logo: 'opencode-logo.png', site: 'https://opencode.ai/', base: 'https://opencode.ai/zen/v1'},
    poolside: {name: 'Poolside Platform', logo: 'poolside-platform-logo.png', site: 'https://platform.poolside.ai/', base: 'https://inference.poolside.ai/v1'},
    kimchi: {name: 'Kimchi Coding', logo: 'kimchi-logo.png', site: 'https://kimchi.dev/', base: 'https://llm.kimchi.dev/openai/v1'},
    kilo: {name: 'Kilo', logo: 'kilo-logo.png', site: 'https://kilo.ai/', base: 'https://api.kilo.ai/api/gateway'},
    meta: {name: 'Meta Model API', logo: 'meta-model-api-logo.png', site: 'https://dev.meta.ai/', base: 'https://api.meta.ai/v1'},
    groq: {name: 'GroqCloud', logo: 'groqcloud-logo.png', site: 'https://console.groq.com/', base: 'https://api.groq.com/openai/v1'},
    deepseek: {name: 'DeepSeek Platform', logo: 'deepseek-platform-logo.png', site: 'https://platform.deepseek.com/', base: 'https://api.deepseek.com/v1'},
    mistral: {name: 'Mistral AI Studio', logo: 'mistral-ai-studio-logo.png', site: 'https://console.mistral.ai/', base: 'https://api.mistral.ai/v1'},
    cerebras: {name: 'Cerebras Cloud', logo: 'cerebras-cloud-logo.png', site: 'https://cloud.cerebras.ai/', base: 'https://api.cerebras.ai/v1'}
});

function extendedElement(tag, className = '', key = '') {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (key) { element.dataset.i18n = key; element.textContent = t(key); }
    return element;
}

function extendedLogo(id, definition, workspace = false) {
    const frame = extendedElement('div', `${workspace ? 'provider-workspace-logo' : 'provider-logo-frame'} extended-logo-${id}`);
    const image = document.createElement('img');
    image.src = `/frontend/assets/providers/${definition.logo}`;
    image.alt = '';
    frame.append(image);
    return frame;
}

function extendedField(form, provider, name, key, placeholder, {type = 'text', required = false, value = '', options} = {}) {
    const group = extendedElement('div', 'form-group');
    const label = extendedElement('label', '', key);
    const input = document.createElement(options ? 'select' : 'input');
    input.id = `extended-${provider}-${name}`;
    input.name = name;
    label.htmlFor = input.id;
    if (options) options.forEach(item => input.add(new Option({zen: 'Zen', go: 'Go'}[item] || item, item)));
    else {
        input.type = type;
        input.placeholder = placeholder;
        input.autocomplete = type === 'password' ? 'one-time-code' : 'off';
        input.autocapitalize = 'none';
        input.spellcheck = false;
        input.maxLength = {api_key: 4096, account_id: 64, organization_id: 128, profile_arn: 512}[name] || 2048;
    }
    input.required = required;
    input.value = value;
    group.append(label);
    if (type === 'password') {
        const wrapper = extendedElement('div', 'setup-secret-field');
        const toggle = extendedElement('button', 'setup-secret-toggle');
        toggle.type = 'button'; toggle.id = `${input.id}Toggle`;
        toggle.dataset.uiAction = 'toggle-setup-secret';
        toggle.setAttribute('aria-controls', input.id);
        toggle.setAttribute('aria-pressed', 'false');
        toggle.setAttribute('aria-label', t('setup_show_secret'));
        toggle.dataset.i18nAriaLabel = 'setup_show_secret';
        // Static icon geometry; never contains provider/user data.
        toggle.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>';
        wrapper.append(input, toggle); group.append(wrapper);
    } else group.append(input);
    form.append(group);
    return input;
}

async function saveExtendedProvider(event, provider, form) {
    event.preventDefault();
    if (form.dataset.saving === 'true' || !form.reportValidity()) return;
    const payload = Object.fromEntries(new FormData(form));
    const submit = form.querySelector('[type="submit"]');
    const controls = [...form.elements].filter(control => !control.disabled);
    controls.forEach(control => { control.disabled = true; });
    form.dataset.saving = 'true'; submit.disabled = true; form.setAttribute('aria-busy', 'true');
    try {
        const response = await fetch(`./api/providers/extended/${provider}/credentials`, {
            method: 'POST', headers: getAuthHeaders(), body: JSON.stringify(payload)
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : t('unknown_error'));
        form.elements.api_key.value = '';
        setSetupSecretVisibility(form.elements.api_key, false);
        showStatus(t('provider.ext.saved'), 'success');
    } catch (error) {
        showStatus(error.message || t('unknown_error'), 'error');
    } finally {
        controls.forEach(control => { control.disabled = false; });
        delete form.dataset.saving; submit.disabled = false; form.removeAttribute('aria-busy');
    }
}

function buildExtendedProviderWorkspaces() {
    const catalog = document.getElementById('providerCatalog');
    const page = document.getElementById('providersTab');
    if (!catalog || !page || document.getElementById('providerSelector-kimi')) return;
    Object.entries(EXTENDED_PROVIDER_UI).forEach(([provider, definition]) => {
        document.querySelectorAll('select[id$="ProviderFilter"]').forEach(select => {
            if (![...select.options].some(option => option.value === provider)) {
                select.add(new Option(definition.name, provider));
            }
        });
        const card = extendedElement('button', 'provider-hero-card provider-selector-button');
        card.type = 'button'; card.id = `providerSelector-${provider}`;
        card.dataset.provider = provider; card.dataset.providerName = definition.name;
        card.dataset.uiAction = 'select-provider'; card.setAttribute('role', 'tab');
        card.setAttribute('aria-selected', 'false'); card.tabIndex = -1;
        card.setAttribute('aria-controls', `providerWorkspace-${provider}`);
        const summary = extendedElement('div', 'provider-summary');
        const name = extendedElement('strong', 'provider-name'); name.textContent = definition.name;
        summary.append(name, extendedElement('p', '', `provider.ext.${provider}`));
        const badges = extendedElement('div', 'provider-capabilities');
        const badge = document.createElement('span'); badge.textContent = 'API Key'; badges.append(badge);
        card.append(extendedLogo(provider, definition), summary, badges); catalog.append(card);

        const workspace = extendedElement('section', 'provider-workspace hidden');
        workspace.id = `providerWorkspace-${provider}`;
        workspace.setAttribute('role', 'tabpanel'); workspace.setAttribute('aria-labelledby', card.id);
        const header = extendedElement('div', 'provider-workspace-header');
        const heading = extendedElement('div', 'provider-workspace-heading');
        const intro = document.createElement('div');
        const title = document.createElement('h2'); title.textContent = definition.name;
        const website = extendedElement('a', 'provider-site-link');
        website.href = definition.site; website.target = '_blank'; website.rel = 'noopener noreferrer';
        website.textContent = definition.site;
        intro.append(title, extendedElement('p', '', `provider.ext.${provider}`), website);
        heading.append(extendedLogo(provider, definition, true), intro); header.append(heading); workspace.append(header);
        if (provider === 'meta') {
            const notice = extendedElement('p', 'card-copy provider-tool-copy', 'provider.ext.meta_contributor_notice');
            notice.id = 'extended-meta-contributor-notice';
            workspace.append(notice);
        }

        const tools = extendedElement('div', 'provider-tools-grid');
        const panel = extendedElement('section', 'tool-panel');
        const form = extendedElement('form', 'extended-provider-form'); form.noValidate = true;
        form.id = `extended-${provider}-credential-form`;
        const formTitle = extendedElement('h3', 'card-title');
        formTitle.dataset.providerFormCopy = 'api_key_title';
        formTitle.dataset.providerName = definition.name;
        formTitle.textContent = t('provider.form.api_key_title', {provider: definition.name});
        panel.append(formTitle, extendedElement('p', 'card-copy provider-tool-copy', 'provider.ext.add_description'));
        const fields = extendedElement('div', 'extended-provider-fields');
        const key = extendedField(fields, provider, 'api_key', 'api_key', '', {type: 'password', required: true});
        if (provider === 'meta') key.setAttribute('aria-describedby', 'extended-meta-contributor-notice');
        key.placeholder = t('provider.ext.key_placeholder'); key.dataset.i18nPlaceholder = 'provider.ext.key_placeholder';
        if (provider === 'cloudflare') extendedField(fields, provider, 'account_id', 'provider.ext.account', '0123456789abcdef0123456789abcdef', {required: true});
        if (provider === 'opencode') extendedField(fields, provider, 'plan', 'provider.ext.plan', '', {value: 'zen', options: ['zen', 'go']});
        form.append(fields);
        const advanced = extendedElement('details', 'tool-panel provider-settings-panel provider-secondary-disclosure extended-provider-advanced');
        advanced.dataset.disclosureKind = 'settings';
        advanced.append(extendedElement('summary', 'provider-disclosure-summary', 'providers.advanced_settings'));
        const settingsHeader = extendedElement('div', 'provider-settings-header');
        settingsHeader.append(extendedElement('p', 'card-copy provider-tool-copy', 'provider.ext.connection_description'));
        const reset = extendedElement('button', 'btn btn-secondary btn-small', 'provider.ext.reset_connection');
        reset.type = 'button';
        settingsHeader.append(reset); advanced.append(settingsHeader);
        const settings = extendedElement('div', 'extended-provider-fields');
        if (definition.base) {
            const endpoint = extendedField(settings, provider, 'base_url', 'provider.form.endpoint_label', definition.base, {type: 'url'});
            if (provider === 'opencode') fields.querySelector('[name="plan"]').addEventListener('change', event => {
                endpoint.value = ''; endpoint.placeholder = event.target.value === 'go' ? 'https://opencode.ai/zen/go/v1' : definition.base;
            });
        }
        if (provider === 'kilo') extendedField(settings, provider, 'organization_id', 'provider.ext.organization', '00000000-0000-0000-0000-000000000000');
        if (provider === 'kiro') {
            advanced.append(extendedElement('p', 'card-copy', 'provider.ext.kiro_notice'));
            extendedField(settings, provider, 'region', 'provider.ext.region', '', {value: 'us-east-1', options: ['us-east-1', 'eu-central-1']});
            extendedField(settings, provider, 'profile_arn', 'provider.ext.profile', 'arn:aws:codewhisperer:us-east-1:123456789012:profile/example');
        }
        settings.querySelectorAll('input, select').forEach(input => input.setAttribute('form', form.id));
        reset.addEventListener('click', () => {
            if (form.dataset.saving === 'true') return;
            settings.querySelectorAll('input, select').forEach(input => {
                input.value = input.name === 'region' ? 'us-east-1' : '';
                input.dispatchEvent(new Event('input', {bubbles: true}));
            });
        });
        advanced.append(settings);
        const actions = extendedElement('div', 'page-actions');
        const save = extendedElement('button', 'btn', 'runtime.save_credential'); save.type = 'submit';
        actions.append(save); form.append(actions);
        form.addEventListener('submit', event => saveExtendedProvider(event, provider, form));
        panel.append(form); tools.append(panel, buildExtendedProviderImport(provider));
        workspace.append(tools, advanced); page.append(workspace);
    });
}

function appendExtendedCredentialFields(form, configuration) {
    const labels = {account_id: 'provider.ext.account', organization_id: 'provider.ext.organization',
        plan: 'provider.ext.plan', region: 'provider.ext.region', profile_arn: 'provider.ext.profile'};
    const placeholders = {account_id: '0123456789abcdef0123456789abcdef',
        organization_id: '00000000-0000-0000-0000-000000000000', profile_arn: 'arn:aws:codewhisperer:us-east-1:123456789012:profile/example'};
    const body = form.querySelector('.credential-edit-form-body');
    Object.entries(labels).forEach(([name, key]) => {
        if (!configuration.editable_fields?.includes(name)) return;
        const options = name === 'plan' ? ['zen', 'go'] : name === 'region' ? ['us-east-1', 'eu-central-1'] : undefined;
        const input = extendedField(body, 'edit', name, key, placeholders[name] || '', {
            value: configuration[name] || '', options, required: name === 'account_id'
        });
        input.classList.add('message-modal-input');
        input.parentElement.classList.add('message-modal-field');
    });
    const plan = form.elements.plan;
    const endpoint = form.elements.base_url;
    if (plan && endpoint) plan.addEventListener('change', () => {
        endpoint.value = plan.value === 'go' ? 'https://opencode.ai/zen/go/v1' : 'https://opencode.ai/zen/v1';
        endpoint.dispatchEvent(new Event('input', {bubbles: true}));
    });
    const error = body.querySelector('[data-credential-edit-error]');
    if (error) body.append(error);
}

buildExtendedProviderWorkspaces();
