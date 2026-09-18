// Keep only display metadata: backend prose and credential payloads never enter result copy.
const providerSaveResults = new WeakMap();
const providerKeyEntries = new Map();

function prepareProviderKeyEntries() {
    const forms = {
        xaiCredentialForm: 'xaiApiKey', googleAiStudioCredentialForm: 'googleAiStudio',
        openaiPlatformCredentialForm: 'openaiPlatform', claudePlatformCredentialForm: 'claudePlatform'
    };
    document.querySelectorAll('.extended-provider-form[id$="-credential-form"]').forEach(form => {
        forms[form.id] = form.id.replace('-credential-form', '');
    });
    for (const [id, prefix] of Object.entries(forms)) {
        const form = document.getElementById(id);
        const result = document.getElementById(`${prefix}SaveResult`);
        if (!form || !result || providerKeyEntries.has(prefix)) continue;
        const open = document.createElement('button');
        open.type = 'button'; open.className = 'btn provider-key-entry-button';
        open.dataset.i18n = prefix === 'extended-cloudflare' ? 'provider.ui.enter_token' : 'provider.ui.enter_key';
        open.textContent = t(open.dataset.i18n);
        open.setAttribute('aria-controls', id); open.setAttribute('aria-expanded', 'false');
        form.before(open); form.classList.add('hidden');
        if (form.contains(result)) form.after(result);
        open.addEventListener('click', () => {
            form.classList.remove('hidden');
            open.setAttribute('aria-expanded', 'true');
            result.classList.add('hidden');
        });
        providerKeyEntries.set(prefix, {form, open});
    }
}

function completeProviderEntry(prefix, result) {
    const keyEntry = providerKeyEntries.get(prefix);
    if (keyEntry) {
        const restoreFocus = keyEntry.form.contains(document.activeElement);
        keyEntry.form.querySelectorAll('input[type="password"]').forEach(input => {
            input.value = ''; setSetupSecretVisibility(input, false);
        });
        keyEntry.form.classList.add('hidden');
        keyEntry.open.setAttribute('aria-expanded', 'false');
        if (restoreFocus) keyEntry.open.focus({preventScroll: true});
    }
    const oauth = {
        primary: ['primaryAuthUrlSection', 'getPrimaryAuthBtn'],
        xaiOauth: ['xaiOauthFields', 'startXaiOauthBtn'],
        claudeOauth: ['claudeOauthFields', 'startClaudeOauthBtn'],
        codexOauth: ['codexOauthFields', 'startCodexOauthBtn']
    }[prefix];
    if (!oauth) return;
    const fields = document.getElementById(oauth[0]);
    if (!fields) return;
    const restoreFocus = fields.contains(document.activeElement);
    if (fields.contains(result)) fields.closest('.tool-panel').append(result);
    fields.classList.add('hidden');
    fields.querySelectorAll('input, textarea').forEach(input => { input.value = ''; });
    fields.querySelectorAll('a').forEach(link => { link.removeAttribute('href'); link.textContent = ''; });
    if (prefix === 'codexOauth') document.getElementById('codexUserCode').textContent = '';
    if (restoreFocus) document.getElementById(oauth[1])?.focus({preventScroll: true});
}

function providerCredentialResultCopy(data = {}) {
    const skipped = data.credential_action === 'skipped' || data.credential_saved === false;
    const title = t(skipped ? 'provider_credential_skipped_title'
        : data.credential_action === 'replaced' ? 'provider_credential_replaced_title'
        : data.credential_action === 'updated' ? 'runtime.credential_updated_title'
        : 'runtime.credential_added_title');
    let body = skipped
        ? t('provider_credential_skipped_body', {data_file_path: data.file_path || data.filename || ''})
        : t('provider.ext.saved');
    if (!skipped && Number.isSafeInteger(data.model_count) && data.model_count >= 0) {
        body += ` ${t('runtime.models_available', {count: formatConsoleNumber(data.model_count)})}`;
    }
    return {title, body, variant: skipped ? 'info' : 'success'};
}

function createProviderCredentialSaveResult(parent, prefix) {
    const result = document.createElement('div');
    result.id = `${prefix}SaveResult`; result.className = 'save-result provider-save-result hidden';
    const copy = document.createElement('div');
    const title = document.createElement('strong'); title.id = `${prefix}SaveResultTitle`;
    const text = document.createElement('p'); text.id = `${prefix}SaveResultText`;
    const view = document.createElement('button'); view.type = 'button'; view.className = 'btn btn-secondary';
    view.dataset.uiAction = 'switch-tab'; view.dataset.tab = 'credentials';
    view.textContent = translateProviderCopy('View', getActiveLocale());
    copy.append(title, text); result.append(copy, view); parent.append(result);
    return result;
}

function showProviderCredentialSaveResult(prefix, data) {
    const result = document.getElementById(`${prefix}SaveResult`);
    if (!result) return;
    // Store a small whitelist for live locale changes, never the response object.
    const state = {credential_action: data.credential_action, credential_saved: data.credential_saved,
        model_count: data.model_count, file_path: data.file_path || data.filename || ''};
    providerSaveResults.set(result, state);
    result.dataset.providerSaveResult = prefix;
    result.classList.add('provider-save-result');
    if (data.credential_saved !== false && data.credential_action !== 'skipped') {
        completeProviderEntry(prefix, result);
    }
    renderProviderCredentialSaveResult(result, state);
    result.classList.remove('hidden');
}

function renderProviderCredentialSaveResult(result, state) {
    const copy = providerCredentialResultCopy(state);
    const prefix = result.dataset.providerSaveResult;
    document.getElementById(`${prefix}SaveResultTitle`).textContent = copy.title;
    document.getElementById(`${prefix}SaveResultText`).textContent = copy.body;
    result.classList.toggle('info', copy.variant === 'info');
    result.querySelector('[data-tab="credentials"]').textContent = translateProviderCopy('View', getActiveLocale());
}

document.addEventListener('polaris:locale-change', () => {
    document.querySelectorAll('[data-provider-save-result]').forEach(result => {
        const state = providerSaveResults.get(result);
        if (state) renderProviderCredentialSaveResult(result, state);
    });
});
