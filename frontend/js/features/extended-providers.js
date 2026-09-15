// Provider-specific connection metadata stays with each key, never in System Settings.
const EXTENDED_PROVIDER_UI = Object.freeze({
    kimi: {name: 'Kimi API Platform', logo: 'kimi-api-platform.png', site: 'https://platform.kimi.ai/', base: 'https://api.moonshot.ai/v1'},
    kiro: {name: 'Kiro', logo: 'kiro-logo.png', site: 'https://kiro.dev/'},
    cloudflare: {name: 'Cloudflare Workers AI', logo: 'cloudflare-logo.png', site: 'https://www.cloudflare.com/products/workers-ai/', base: 'https://api.cloudflare.com/client/v4'},
    nvidia: {name: 'NVIDIA NIM', logo: 'nvidia-logo.png', site: 'https://developer.nvidia.com/nim', base: 'https://integrate.api.nvidia.com/v1'},
    opencode: {name: 'OpenCode', logo: 'opencode-logo.png', site: 'https://opencode.ai/', base: 'https://opencode.ai/zen/v1'},
    poolside: {name: 'Poolside Platform', logo: 'poolside-platform-logo.png', site: 'https://platform.poolside.ai/', base: 'https://inference.poolside.ai/v1'},
    kimchi: {name: 'Kimchi Coding', logo: 'kimchi-logo.png', site: 'https://kimchi.dev/', base: 'https://llm.kimchi.dev/openai/v1'},
    kilo: {name: 'Kilo', logo: 'kilo-logo.png', site: 'https://kilo.ai/', base: 'https://api.kilo.ai/api/gateway'}
});

function extendedElement(tag, className = '', key = '') {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (key) { element.dataset.i18n = key; element.textContent = t(key); }
    return element;
}

function extendedLogo(id, definition) {
    const frame = extendedElement('div', `provider-logo-frame extended-logo-${id}`);
    const image = document.createElement('img');
    image.src = `/frontend/assets/providers/${definition.logo}`;
    image.alt = definition.name;
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
    if (options) options.forEach(item => input.add(new Option(item, item)));
    else {
        input.type = type;
        input.placeholder = placeholder;
        input.autocomplete = type === 'password' ? 'new-password' : 'off';
        input.spellcheck = false;
        input.maxLength = name === 'api_key' ? 4096 : 2048;
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
        form.querySelector('[data-extended-saved]').classList.remove('hidden');
    } catch (error) {
        showStatus(error.message || t('unknown_error'), 'error');
    } finally {
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
        const heading = extendedElement('div', 'provider-workspace-heading');
        const intro = document.createElement('div');
        const title = document.createElement('h2'); title.textContent = definition.name;
        const website = extendedElement('a', 'provider-site-link');
        website.href = definition.site; website.target = '_blank'; website.rel = 'noopener noreferrer';
        website.textContent = definition.site;
        intro.append(title, extendedElement('p', '', `provider.ext.${provider}`), website);
        heading.append(extendedLogo(provider, definition), intro); workspace.append(heading);

        const form = extendedElement('form', 'tool-panel extended-provider-form'); form.noValidate = true;
        const formTitle = extendedElement('h3', 'card-title');
        formTitle.dataset.providerFormCopy = 'api_key_title';
        formTitle.dataset.providerName = definition.name;
        formTitle.textContent = t('provider.form.api_key_title', {provider: definition.name});
        form.append(formTitle);
        const fields = extendedElement('div', 'extended-provider-fields');
        const key = extendedField(fields, provider, 'api_key', 'api_key', '', {type: 'password', required: true});
        key.placeholder = t('provider.ext.key_placeholder'); key.dataset.i18nPlaceholder = 'provider.ext.key_placeholder';
        if (provider === 'cloudflare') extendedField(fields, provider, 'account_id', 'provider.ext.account', '0123456789abcdef0123456789abcdef', {required: true});
        if (provider === 'opencode') extendedField(fields, provider, 'plan', 'provider.ext.plan', '', {value: 'zen', options: ['zen', 'go']});
        form.append(fields);
        const advanced = extendedElement('details', 'provider-secondary-disclosure extended-provider-advanced');
        advanced.append(extendedElement('summary', 'provider-disclosure-summary', 'providers.advanced_settings'));
        const settings = extendedElement('div', 'extended-provider-fields');
        if (provider !== 'kiro') advanced.append(extendedElement('p', 'card-copy', 'provider.ext.settings'));
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
        advanced.append(settings); form.append(advanced);
        const actions = extendedElement('div', 'page-actions');
        const save = extendedElement('button', 'btn', 'runtime.save_credential'); save.type = 'submit';
        const imports = extendedElement('button', 'btn btn-secondary', 'providers.import_credentials');
        imports.type = 'button'; imports.dataset.uiAction = 'switch-tab'; imports.dataset.tab = 'pool';
        actions.append(save, imports); form.append(actions);
        const result = extendedElement('div', 'provider-save-result hidden'); result.dataset.extendedSaved = '';
        result.append(extendedElement('p', '', 'provider.ext.saved'));
        const view = extendedElement('button', 'btn btn-secondary', 'provider.ext.open_pool');
        view.type = 'button'; view.dataset.uiAction = 'switch-tab'; view.dataset.tab = 'pool'; result.append(view);
        form.append(result); form.addEventListener('submit', event => saveExtendedProvider(event, provider, form));
        workspace.append(form); page.append(workspace);
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
        extendedField(body, 'edit', name, key, placeholders[name] || '', {
            value: configuration[name] || '', options, required: name === 'account_id'
        });
    });
}

buildExtendedProviderWorkspaces();
