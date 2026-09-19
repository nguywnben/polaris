// A credential is one information surface, not a launcher for other dialogs.
function credentialManagementButton(action, label, extra = '') {
    return `<button type="button" class="btn btn-secondary" data-management-action="${action}" ${extra}>${escapeHtml(t(label))}</button>`;
}

function credentialManagementSection(name, title, content = '', refresh = true) {
    return `<section class="credential-management-section" aria-labelledby="management-${name}-title">
        <div class="credential-management-section-heading">
            <h4 id="management-${name}-title">${escapeHtml(t(title))}</h4>
            ${refresh ? `<button type="button" class="btn btn-secondary btn-small" data-management-load="${name}">${escapeHtml(t('refresh'))}</button>` : ''}
        </div>
        <div data-management-${name}>${content}</div>
    </section>`;
}

function buildCredentialManagementHtml(context, credInfo, capabilities) {
    const button = credentialManagementButton;
    return `<div class="message-modal credential-management-modal" role="dialog" aria-modal="true" aria-labelledby="credentialManagementTitle">
        <header class="message-modal-header">
            <div class="credential-management-identity">
                <img src="${escapeAttribute(context.logo)}" alt="" width="36" height="36">
                <div><h3 id="credentialManagementTitle">${escapeHtml(context.providerName)}</h3>
                    <p data-management-name>${escapeHtml(getCredentialAccountLabel(credInfo))}</p></div>
            </div>
        </header>
        <div class="message-modal-body">
            <div class="credential-management-overview">
                <div class="credential-management-badges" data-management-state></div>
                <dl class="credential-management-facts">
                    <div><dt>${escapeHtml(t('table_filename'))}</dt><dd>${escapeHtml(context.filename)}</dd></div>
                    ${credInfo.credential_type === 'oauth' && credInfo.user_email ? `<div><dt>${escapeHtml(t('modal.email'))}</dt><dd>${escapeHtml(credInfo.user_email)}</dd></div>` : ''}
                </dl>
                <div class="credential-management-toolbar">
                    ${capabilities.disable ? button('toggle', credInfo.status?.disabled ? 'action_enable' : 'action_disable') : ''}
                    ${capabilities.verify ? button('verify', 'btn_verify_id') : ''}
                    ${capabilities.reauthenticate ? button('reauthenticate', 'credential_reauthenticate_action') : ''}
                    ${capabilities.preview ? button('preview', 'btn_setup_preview') : ''}
                    ${capabilities.credit ? button('credit', credInfo.enable_credit ? 'action_disable_credit' : 'action_enable_credit') : ''}
                </div>
                ${capabilities.credit ? `<div data-management-credit-confirm hidden>
                    <p class="field-hint">${escapeHtml(t('providers.antigravity.credit_description'))}</p>
                    <div class="credential-management-toolbar">${button('confirm-credit', 'btn_confirm')}${button('cancel-credit', 'btn_cancel')}</div>
                </div>` : ''}
                ${credInfo.source === 'environment' ? `<p class="field-hint">${escapeHtml(t('settings.managed_environment'))}</p>` : ''}
            </div>
            <div class="credential-management-content">
                ${capabilities.quota ? credentialManagementSection('quota', 'quota_details') : ''}
                ${capabilities.models || capabilities.test ? credentialManagementSection('models', 'available_models_title') : ''}
                <div class="credential-management-result hidden" data-management-result role="status" aria-live="polite"></div>
                ${capabilities.edit ? credentialManagementSection('configuration', 'credentials.management.configuration') : ''}
                ${credentialManagementSection('errors', 'credentials.management.diagnostics')}
                ${capabilities.reveal || capabilities.export ? `<details class="credential-management-sensitive" data-management-sensitive>
                    <summary>${escapeHtml(t('credentials.management.sensitive'))}</summary>
                    <p class="field-hint">${escapeHtml(t('modal.credential_payload_intro'))}</p>
                    <div class="credential-management-toolbar">
                        ${button('reveal', 'credentials.management.reveal')}
                        ${button('hide', 'credentials.management.hide', 'hidden')}
                        ${capabilities.export ? button('download', 'btn_download') : ''}
                    </div>
                    <div data-management-payload></div>
                </details>` : ''}
                ${capabilities.delete ? `<div class="credential-management-danger">
                    ${button('delete', 'action_delete')}
                    <div data-management-delete-confirm hidden>
                        <p>${escapeHtml(t('confirm_delete_cred'))}</p>
                        <strong>${escapeHtml(context.filename)}</strong>
                        <div class="credential-management-toolbar">${button('confirm-delete', 'action_delete')}${button('cancel-delete', 'btn_cancel')}</div>
                    </div>
                </div>` : ''}
            </div>
        </div>
        <footer class="message-modal-footer"><button type="button" class="message-modal-btn" data-dialog-close>${escapeHtml(t('btn_close'))}</button></footer>
    </div>`;
}

async function showCredentialManagement(pathId, manager, credInfo, capabilities) {
    const provider = getCredentialProviderMeta(credInfo, manager.type);
    const context = {...getCredentialModalContext(pathId, manager), logo: provider.logo};
    const {filename} = context;
    const modal = document.createElement('div');
    modal.className = 'message-modal-overlay';
    modal.innerHTML = buildCredentialManagementHtml(context, credInfo, capabilities);
    const lifetime = new AbortController();
    const result = modal.querySelector('[data-management-result]');
    let saving = false;
    let running = false;
    let closed = false;
    const endpoint = name => `./api/credentials/${name}/${encodeURIComponent(filename)}?${manager.getModeParam()}`;
    const read = async (url, options = {}) => {
        const response = await fetch(url, {headers: getAuthHeaders(), signal: lifetime.signal, ...options});
        const data = await response.json();
        if (!response.ok || data.success === false) throw new Error(data.detail || data.error || data.message || t('unknown_error'));
        return data;
    };
    const syncOverview = () => {
        const latest = manager.data[filename] || credInfo;
        const disabled = Boolean(latest.status?.disabled);
        modal.querySelector('[data-management-name]').textContent = getCredentialAccountLabel(latest);
        modal.querySelector('[data-management-state]').innerHTML = `
            <span class="status-badge ${disabled ? 'disabled' : 'enabled'}">${escapeHtml(t(disabled ? 'status_disabled' : 'status_enabled'))}</span>
            ${renderCredentialAuthenticationBadge(provider, latest)}`;
        const toggle = modal.querySelector('[data-management-action="toggle"]');
        if (toggle) toggle.textContent = t(disabled ? 'action_enable' : 'action_disable');
        const credit = modal.querySelector('[data-management-action="credit"]');
        if (credit) credit.textContent = t(latest.enable_credit ? 'action_disable_credit' : 'action_enable_credit');
    };
    const close = async () => {
        if (closed || saving) return;
        closed = true;
        lifetime.abort();
        await unmountModal(modal);
        modal.replaceChildren(); // Forget explicitly revealed secrets and entered replacements.
        const checkbox = Array.from(document.querySelectorAll('[data-credential-select]')).find(node => node.dataset.filename === filename);
        checkbox?.closest('.cred-card')?.querySelector('[data-credential-command="manage"]')?.focus();
    };
    syncOverview();
    modal.addEventListener('keydown', event => { if (event.key === 'Escape') { event.stopPropagation(); void close(); } });
    modal.addEventListener('click', event => { if (event.target === modal || event.target.closest('[data-dialog-close]')) void close(); });
    await mountModal(modal);

    // Load each safe information section independently; one failure must not hide the rest.
    const load = async name => {
        const scope = AppState.credentialCardIndex[pathId]?.quotaCacheScope;
        const host = modal.querySelector(`[data-management-${name}]`);
        const refresh = modal.querySelector(`[data-management-load="${name}"]`);
        if (!host || host.getAttribute('aria-busy') === 'true' || closed) return;
        setRegionBusy(host, true);
        if (refresh) refresh.disabled = true;
        try {
            if (name === 'configuration') {
                await showCredentialEditModal(pathId, {container: host, signal: lifetime.signal, isBusy: () => running,
                    onSaving: value => { saving = value; refresh.disabled = value; },
                    onSaved: () => { syncOverview(); void Promise.all(['models', 'quota', 'errors'].map(load)); }});
            } else if (name === 'models') {
                const data = await read(endpoint('models'));
                if (!closed) {
                    renderCredentialManagementModels(host, data.model_ids || [], capabilities.test);
                    if (Array.isArray(data.model_ids)) {
                        updateCredentialModelCount(pathId, filename, scope, data.model_ids.length, manager);
                    }
                }
            } else if (name === 'quota') {
                const data = await read(endpoint('quota'));
                if (closed) return;
                if (!cacheCredentialQuota(pathId, filename, scope, {data, summary: summarizeCredentialQuota(data)})) return;
                updateCredentialQuotaPreview(pathId, filename);
                renderCredentialManagementQuota(host, filename, data, context);
            } else if (name === 'errors') {
                const data = await read(endpoint('errors'));
                if (closed) return;
                const content = document.createElement('div');
                content.innerHTML = buildCredentialErrorsHtml(filename, data);
                host.replaceChildren(content.querySelector('.message-error-list, .modal-empty-state'));
            }
        } catch (error) {
            if (!closed) {
                host.innerHTML = `<p class="credential-management-error" role="alert">${escapeHtml(error.message || t('unknown_error'))}</p>`;
                if (name === 'quota') {
                    cacheCredentialQuota(pathId, filename, scope, {error: error.message});
                    updateCredentialQuotaPreview(pathId, filename);
                }
            }
        } finally {
            setRegionBusy(host, false);
            if (refresh) refresh.disabled = false;
        }
    };
    modal.querySelectorAll('[data-management-load]').forEach(button => button.addEventListener('click', () => {
        if (!running && !saving) void load(button.dataset.managementLoad);
    }));
    bindCredentialManagementActions({modal, context, manager, capabilities, read, close, syncOverview,
        isClosed: () => closed, isBusy: () => running || saving,
        setBusy: value => { running = value; }, result, signal: lifetime.signal,
        reloadDiagnostics: () => load('errors')});
    await Promise.all(['quota', 'models', 'configuration', 'errors'].map(load));
    return modal;
}

function renderCredentialManagementModels(host, models, canTest) {
    const ids = Array.isArray(models) ? models.filter(id => typeof id === 'string') : [];
    host.innerHTML = ids.length ? `<p class="field-hint">${escapeHtml(t('modal.models_intro'))}</p>
        <input type="search" data-management-search placeholder="${escapeAttribute(t('modal.filter_models'))}" aria-label="${escapeAttribute(t('modal.filter_available_models'))}">
        <div class="credential-model-list">${ids.map(id => `<button type="button" class="credential-model-item" data-management-model="${escapeAttribute(id)}" title="${escapeAttribute(t('modal.copy_model_id'))}">${escapeHtml(id)}</button>`).join('')}</div>
        <p data-management-model-empty hidden>${escapeHtml(t('modal.no_models_match'))}</p>
        ${canTest ? `<div class="credential-management-test"><label><span>${escapeHtml(t('modal.model'))}</span><select data-management-model-select>${ids.map(id => `<option value="${escapeAttribute(id)}">${escapeHtml(id)}</option>`).join('')}</select></label>${credentialManagementButton('test', 'btn_test_model')}</div>` : ''}`
        : `<p class="modal-empty-state">${escapeHtml(t('modal.no_models_available'))}</p>`;
    host.querySelectorAll('[data-management-model]').forEach(button => button.addEventListener('click', () => copyTextWithStatus(button.dataset.managementModel)));
    host.querySelector('[data-management-search]')?.addEventListener('input', event => {
        let visible = 0;
        host.querySelectorAll('[data-management-model]').forEach(button => {
            button.hidden = !button.dataset.managementModel.toLowerCase().includes(event.target.value.trim().toLowerCase());
            if (!button.hidden) visible++;
        });
        host.querySelector('[data-management-model-empty]').hidden = visible > 0;
    });
}

function renderCredentialManagementQuota(host, filename, data, context) {
    const content = document.createElement('div');
    content.innerHTML = buildCredentialQuotaHtml(filename, data, context);
    host.innerHTML = renderCredentialQuotaFacts(data, context);
    const quotas = content.querySelector('.modal-quota-grid, .modal-empty-state');
    if (quotas) host.append(quotas);
    if (data.account_metadata_status === 'unavailable') {
        const notice = document.createElement('p');
        notice.className = 'field-hint';
        notice.textContent = t('quota.facts.account_unavailable');
        host.append(notice);
    }
}
