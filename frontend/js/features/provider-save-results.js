// Keep only display metadata: backend prose and credential payloads never enter result copy.
const providerSaveResults = new WeakMap();

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
    view.dataset.uiAction = 'switch-tab'; view.dataset.tab = 'pool';
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
    renderProviderCredentialSaveResult(result, state);
    result.classList.remove('hidden');
}

function renderProviderCredentialSaveResult(result, state) {
    const copy = providerCredentialResultCopy(state);
    const prefix = result.dataset.providerSaveResult;
    document.getElementById(`${prefix}SaveResultTitle`).textContent = copy.title;
    document.getElementById(`${prefix}SaveResultText`).textContent = copy.body;
    result.classList.toggle('info', copy.variant === 'info');
    result.querySelector('[data-tab="pool"]').textContent = translateProviderCopy('View', getActiveLocale());
}

document.addEventListener('polaris:locale-change', () => {
    document.querySelectorAll('[data-provider-save-result]').forEach(result => {
        const state = providerSaveResults.get(result);
        if (state) renderProviderCredentialSaveResult(result, state);
    });
});
