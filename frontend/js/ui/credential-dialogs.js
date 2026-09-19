function getCredentialModalContext(pathId, manager) {

    const context = AppState.credentialCardIndex[pathId] || {};
    const resolvedManager = context.managerType === 'primary' ? AppState.primaryCreds : manager;

    if (context.filename) {

        return { ...context, filename: context.filename, manager: resolvedManager };

    }

    const details = document.getElementById('details-' + pathId)
        || document.getElementById('errors-' + pathId)
        || document.getElementById('quota-' + pathId);

    const filename = details?.querySelector('[data-filename]')?.getAttribute('data-filename') || '';

    return { filename, manager };

}

function buildCredentialContentHtml(filename, content) {

    const rows = renderMessageResultRows([
        [t('table_filename'), filename],
        content?.user_email || content?.email ? [t('modal.email'), content.user_email || content.email] : null,
        content?.project_id ? [t('modal.project_id'), content.project_id] : null,
        content?.expiry ? [t('modal.expiry'), content.expiry] : null,
    ].filter(Boolean));
    const body = JSON.stringify(content, null, 2);

    return `
        <div class="message-result-panel">
            <div class="message-result-intro">${escapeHtml(t('modal.credential_payload_intro'))}</div>
            <div class="message-result-section">
                <div class="message-result-section-title">${escapeHtml(t('modal.credential_summary'))}</div>
                <div class="message-result-summary">${rows}</div>
            </div>
            <div class="message-result-section">
                <div class="message-result-section-title">${escapeHtml(t('modal.credential_payload'))}</div>
                <pre class="message-modal-code">${escapeHtml(body)}</pre>
            </div>
        </div>
    `;

}

function buildCredentialModelsHtml(context) {

    const modelIds = Array.isArray(context.modelIds) ? context.modelIds : [];
    const rows = renderMessageResultRows([
        [t('modal.provider'), context.providerName || t('provider_google_ai_studio')],
        [t('modal.available_models'), modelIds.length],
    ]);
    const modelButtons = modelIds.map((modelId) => `
        <button type="button" class="credential-model-item" data-credential-model="${escapeAttribute(modelId)}" title="${escapeAttribute(t('modal.copy_model_id'))}">
            ${escapeHtml(modelId)}
        </button>
    `).join('');

    return `
        <div class="message-result-panel credential-model-panel">
            <div class="message-result-intro">${escapeHtml(t('modal.models_intro'))}</div>
            <div class="message-result-section">
                <div class="message-result-section-title">${escapeHtml(t('modal.credential_summary'))}</div>
                <div class="message-result-summary">${rows}</div>
            </div>
            <div class="message-result-section">
                <div class="message-result-section-title">${escapeHtml(t('modal.model_ids'))}</div>
                <input type="search" class="credential-model-search" placeholder="${escapeAttribute(t('modal.filter_models'))}" aria-label="${escapeAttribute(t('modal.filter_available_models'))}" autocomplete="off">
                <div class="credential-model-list">${modelButtons}</div>
                <div class="modal-empty-state credential-model-empty hidden">${escapeHtml(t('modal.no_models_match'))}</div>
            </div>
        </div>
    `;

}

function credentialEditField(configuration, field) {
    return Array.isArray(configuration.editable_fields)
        && configuration.editable_fields.includes(field);
}

async function showCredentialEditModal(pathId, options = {}) {
    const context = getCredentialModalContext(pathId, AppState.primaryCreds);
    if (!context.filename || context.manager?.type !== 'primary') return;

    if (!options.container) showStatus(t('status_loading_file_content'), 'info');
    try {
        const endpoint = `./api/credentials/configuration/${encodeURIComponent(context.filename)}?mode=provider`;
        const response = await fetch(endpoint, {headers: getAuthHeaders(), signal: options.signal});
        const configuration = await response.json().catch(() => ({}));
        if (!response.ok || !configuration.editable) {
            throw new Error(configuration.detail || configuration.error || t('unknown_error'));
        }

        const title = `${t('credential_edit_action')} — ${context.providerName}`;
        const modal = document.createElement('div');
        modal.className = 'message-modal-overlay';
        modal.innerHTML = `
            <div class="message-modal credential-edit-modal" role="dialog" aria-modal="true" aria-labelledby="credentialEditTitle">
                <div class="message-modal-header"><h3 id="credentialEditTitle">${escapeHtml(title)}</h3></div>
                <form data-credential-edit-form>
                    <div class="message-modal-body credential-edit-form-body">
                        ${credentialEditField(configuration, 'credential_label') ? `
                            <label class="message-modal-field">
                                <span class="message-modal-field-label">${escapeHtml(t('credential_display_name'))}</span>
                                <input class="message-modal-input" name="credential_label" maxlength="128" required placeholder="${escapeAttribute(t('form.credential_name'))}" value="${escapeAttribute(configuration.credential_label || '')}">
                            </label>` : ''}
                        ${credentialEditField(configuration, 'base_url') ? `
                            <label class="message-modal-field">
                                <span class="message-modal-field-label">${escapeHtml(t('provider.form.endpoint_label'))}</span>
                                <input class="message-modal-input" name="base_url" type="url" maxlength="2048" ${configuration.provider === 'ollama' ? 'required' : ''} placeholder="https://api.example.com" value="${escapeAttribute(configuration.base_url || '')}">
                            </label>` : ''}
                        ${credentialEditField(configuration, 'api_key') ? `
                            <label class="message-modal-field">
                                <span class="message-modal-field-label">${escapeHtml(t('api_key'))}</span>
                                <input class="message-modal-input" name="api_key" type="password" maxlength="4096" autocomplete="new-password" placeholder="${escapeAttribute(t('credential_key_unchanged'))}">
                            </label>` : ''}
                        <div class="credential-edit-error hidden" data-credential-edit-error role="alert"></div>
                    </div>
                    <div class="message-modal-footer">
                        <button type="button" class="message-modal-btn" data-credential-edit-cancel>${escapeHtml(t('btn_cancel'))}</button>
                        <button type="submit" class="message-modal-btn message-modal-btn-primary">${escapeHtml(t('save'))}</button>
                    </div>
                </form>
            </div>`;

        const form = modal.querySelector('[data-credential-edit-form]');
        if (typeof appendExtendedCredentialFields === 'function') appendExtendedCredentialFields(form, configuration);
        if (options.container) {
            if (options.signal?.aborted) return;
            options.container.replaceChildren(form);
        }
        const error = form.querySelector('[data-credential-edit-error]');
        const submit = form.querySelector('button[type="submit"]');
        let saving = false;
        const close = () => {
            if (saving) return;
            if (options.container) {
                form.reset();
                error.classList.add('hidden');
            } else void unmountModal(modal);
        };
        if (options.container) form.querySelector('[data-credential-edit-cancel]').addEventListener('click', close);
        modal.addEventListener('click', (event) => {
            if (event.target === modal || event.target.closest('[data-credential-edit-cancel]')) close();
        });
        modal.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') close();
        });
        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            if (saving || options.isBusy?.()) return;
            const values = new FormData(form);
            const payload = {};
            const label = String(values.get('credential_label') || '').trim();
            const baseUrl = String(values.get('base_url') || '').trim();
            const apiKey = String(values.get('api_key') || '').trim();
            if (credentialEditField(configuration, 'credential_label')
                && label !== String(configuration.credential_label || '')) payload.credential_label = label;
            if (credentialEditField(configuration, 'base_url')
                && baseUrl !== String(configuration.base_url || '')) payload.base_url = baseUrl;
            if (credentialEditField(configuration, 'api_key') && apiKey) payload.api_key = apiKey;
            for (const field of ['account_id', 'organization_id', 'plan', 'region', 'profile_arn']) {
                const value = String(values.get(field) || '').trim();
                if (credentialEditField(configuration, field) && value !== String(configuration[field] || '')) {
                    payload[field] = value;
                }
            }
            if (!Object.keys(payload).length) {
                if (!options.container) void unmountModal(modal);
                return;
            }

            saving = true;
            options.onSaving?.(true);
            const enabledControls = Array.from(form.querySelectorAll('input, select, textarea, button')).filter(control => !control.disabled);
            enabledControls.forEach(control => { control.disabled = true; });
            form.setAttribute('aria-busy', 'true');
            error.classList.add('hidden');
            try {
                const saveResponse = await fetch(endpoint, {
                    method: 'PATCH',
                    headers: getAuthHeaders(),
                    body: JSON.stringify(payload)
                });
                const result = await saveResponse.json().catch(() => ({}));
                if (!saveResponse.ok) throw new Error(result.detail || result.error || t('unknown_error'));
                saving = false;
                if (!options.container) await unmountModal(modal);
                else {
                    Object.assign(configuration, payload);
                    const keyInput = form.elements.api_key;
                    if (keyInput) keyInput.value = '';
                    delete configuration.api_key;
                    form.querySelectorAll('input:not([type="password"])').forEach(input => { input.defaultValue = input.value; });
                    form.querySelectorAll('select').forEach(select => Array.from(select.options).forEach(option => { option.defaultSelected = option.selected; }));
                }
                showStatus(t('status_action_success', {action: t('credential_edit_action')}), 'success');
                await context.manager.refresh({preserveContent: true});
                options.onSaved?.();
            } catch (saveError) {
                saving = false;
                submit.disabled = false;
                form.removeAttribute('aria-busy');
                error.textContent = saveError.message || t('unknown_error');
                error.classList.remove('hidden');
            } finally {
                saving = false;
                enabledControls.forEach(control => { control.disabled = false; });
                form.removeAttribute('aria-busy');
                options.onSaving?.(false);
            }
        });
        if (!options.container) await mountModal(modal);
    } catch (error) {
        if (options.signal?.aborted) return;
        if (options.container) throw error;
        showStatus(t('status_action_failed', {error: error.message || t('unknown_error')}), 'error');
    }
}

function reauthenticateCredential(pathId) {
    const context = getCredentialModalContext(pathId, AppState.primaryCreds);
    reauthenticateCredentialByContext(context);
}

async function showCredentialModels(pathId) {

    showStatus(t('runtime.loading_models'), 'info');

    try {
        const context = await loadCredentialModelOptions(pathId);
        const modelIds = context.modelIds;
        if (modelIds.length === 0) {
            showMessageModal(t('available_models_title'), t('no_models_for_credential'), 'info');
            return;
        }

        const modal = showMessageModal(
            t('available_models_title'),
            buildCredentialModelsHtml({ ...context, modelIds }),
            'info',
            { html: true }
        );
        const search = modal.querySelector('.credential-model-search');
        const items = Array.from(modal.querySelectorAll('[data-credential-model]'));
        const emptyState = modal.querySelector('.credential-model-empty');

        items.forEach((item) => {
            item.addEventListener('click', () => {
                copyTextWithStatus(item.getAttribute('data-credential-model'));
            });
        });

        search?.addEventListener('input', () => {
            const query = search.value.trim().toLowerCase();
            let visibleCount = 0;
            items.forEach((item) => {
                const visible = item.textContent.toLowerCase().includes(query);
                item.hidden = !visible;
                if (visible) visibleCount += 1;
            });
            if (emptyState) emptyState.classList.toggle('hidden', visibleCount > 0);
        });

    } catch (error) {
        const message = error.message || t('modal.models_load_failed');
        showStatus(message, 'error');
        showMessageModal(t('available_models_title'), message, 'error');
    }

}

async function loadCredentialModelOptions(pathId) {

    const context = getCredentialModalContext(pathId, AppState.primaryCreds);
    const { filename, manager } = context;
    if (!filename || !manager) throw new Error(t('modal.credential_unavailable'));

    const response = await fetch(
        `${manager.getEndpoint('models')}/${encodeURIComponent(filename)}?${manager.getModeParam()}`,
        { headers: getAuthHeaders() }
    );
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.detail || data.error || t('modal.models_load_failed'));
    }

    return {
        ...context,
        modelIds: Array.isArray(data.model_ids) ? data.model_ids : [],
    };

}

async function showCredentialModelTest(pathId) {

    showStatus(t('runtime.loading_models'), 'info');

    try {
        const context = await loadCredentialModelOptions(pathId);
        if (context.modelIds.length === 0) {
            showMessageModal(
                t('modal.model_test_title'),
                t('modal.no_models_available'),
                'info'
            );
            return;
        }

        const account = context.accountLabel ? ` (${context.accountLabel})` : '';
        await showModelTestModal(
            t('modal.model_test_intro', { provider: context.providerName, account }),
            {
                title: t('btn_test_model'),
                label: t('modal.model'),
                placeholder: t('modal.select_model'),
                confirmLabel: t('modal.test'),
                options: context.modelIds.map((modelId) => ({ value: modelId, label: modelId })),
                onTest: async (model, signal) => {
                    if (context.manager.type === 'primary') {
                        return testPrimaryCredential(context.filename, model, signal);
                    }
                    return testCredential(context.filename, model, signal);
                },
            }
        );
    } catch (error) {
        const message = error.message || t('modal.models_load_failed');
        showStatus(message, 'error');
        showMessageModal(t('model_test_title'), message, 'error');
    }

}

function quotaLevelFromUsedPercentage(usedPercentage) {

    if (usedPercentage >= 90) return 'danger';
    if (usedPercentage >= 70) return 'warning';
    if (usedPercentage >= 50) return 'info';
    return 'success';

}

function formatQuotaNumber(value) {

    const number = credentialQuotaNumber(value);
    if (number === null) return t('modal.unavailable');
    return Number.isFinite(number) ? formatConsoleNumber(number) : t('modal.unavailable');

}

function formatQuotaResetTime(value) {

    const date = new Date(value || '');
    if (!Number.isFinite(date.getTime())) return t('quota.reset_unavailable');
    return date.toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });

}

function buildAccountBillingQuotaHtml(filename, data, context = {}) {

    const periods = [
        data.monthly ? { id: 'monthly', label: t('modal.monthly_credits'), ...data.monthly } : null,
        data.weekly ? { id: 'weekly', label: t('modal.weekly_usage'), ...data.weekly } : null,
        ...(Array.isArray(data.windows) ? data.windows : []),
    ].filter(Boolean);
    const remainingPercentages = periods
        .map((period) => credentialQuotaNumber(period.remaining_percentage))
        .filter(Number.isFinite);
    const lowestRemaining = remainingPercentages.length ? Math.min(...remainingPercentages) : null;
    const rows = renderMessageResultRows([
        [t('modal.provider'), context.providerName || t('provider_grok')],
        context.accountLabel ? [t('modal.account'), context.accountLabel] : [t('modal.credential'), filename],
        [t('modal.quota_source'), t('modal.grok_billing')],
        [t('modal.billing_periods'), periods.length],
        lowestRemaining !== null ? [t('modal.lowest_remaining'), `${lowestRemaining}%`] : null,
    ].filter(Boolean));

    const cards = periods.map(renderCredentialQuotaWindow).join('');

    return `
        <div class="message-result-panel">
            <div class="message-result-intro">${escapeHtml(t('modal.grok_quota_intro'))}</div>
            <div class="message-result-section">
                <div class="message-result-section-title">${escapeHtml(t('modal.quota_summary'))}</div>
                <div class="message-result-summary">${rows}</div>
            </div>
            <div class="message-result-section">
                <div class="message-result-section-title">${escapeHtml(t('modal.billing_periods'))}</div>
                <div class="modal-quota-grid">${cards}</div>
            </div>
        </div>
    `;

}

function buildAccountRateLimitQuotaHtml(filename, data, context = {}) {

    const windows = Array.isArray(data.windows) ? data.windows : [];
    const isClaudeCode = data.provider_variant === 'claude_code'
        || context.providerVariant === 'claude_code';
    const remainingPercentages = windows
        .map((windowData) => credentialQuotaNumber(windowData.remaining_percentage))
        .filter(Number.isFinite);
    const lowestRemaining = remainingPercentages.length ? Math.min(...remainingPercentages) : null;
    const rawPlan = String(data.plan || '').trim().replace(/[_-]+/g, ' ');
    const plan = rawPlan.replace(/\b\w/g, (character) => character.toUpperCase());
    const isMuseCode = data.provider === 'muse_code' || context.providerVariant === 'muse_code';
    const providerTier = isMuseCode
        ? normalizeCredentialSubscriptionPlan(data.subscription_tier, 'provider_tier') : null;
    const providerPlan = isMuseCode
        ? normalizeCredentialSubscriptionPlan(data.plan, 'provider_plan') : null;
    const availableResetCredits = credentialQuotaNumber(data.reset_credits?.available_count);
    const hasReviewWindows = windows.some((windowData) => String(windowData.id || '').startsWith('review_'));
    const rows = renderMessageResultRows([
        [t('modal.provider'), context.providerName || (isClaudeCode ? 'Claude Code' : 'Codex')],
        context.accountLabel ? [t('modal.account'), context.accountLabel] : [t('modal.credential'), filename],
        providerPlan ? [t('modal.plan'), providerPlan.label] : providerTier ? [t('tier'), providerTier.label]
            : isMuseCode ? null : [t('modal.plan'), plan || t('modal.unknown')],
        [t('modal.usage_windows'), windows.length],
        lowestRemaining !== null ? [t('modal.lowest_remaining'), `${lowestRemaining}%`] : null,
        Number.isFinite(availableResetCredits)
            ? [t('modal.reset_credits'), Math.max(0, availableResetCredits)]
            : null,
        typeof data.limit_reached === 'boolean'
            ? [t('modal.standard_limit'), data.limit_reached ? t('modal.reached') : t('modal.available')]
            : null,
        hasReviewWindows && typeof data.review_limit_reached === 'boolean'
            ? [t('modal.code_review_limit'), data.review_limit_reached ? t('modal.reached') : t('modal.available')]
            : null,
    ].filter(Boolean));

    const cards = windows.map(renderCredentialQuotaWindow).join('');

    return `
        <div class="message-result-panel">
            <div class="message-result-intro">${escapeHtml(t(isMuseCode ? 'modal.quota_summary' : isClaudeCode ? 'modal.claude_quota_intro' : 'modal.codex_quota_intro'))}</div>
            <div class="message-result-section">
                <div class="message-result-section-title">${escapeHtml(t('modal.quota_summary'))}</div>
                <div class="message-result-summary">${rows}</div>
            </div>
            <div class="message-result-section">
                <div class="message-result-section-title">${escapeHtml(t('modal.usage_windows'))}</div>
                ${windows.length ? `<div class="modal-quota-grid">${cards}</div>` : `<div class="modal-empty-state">${escapeHtml(t('status_no_quota_info'))}</div>`}
            </div>
        </div>
    `;

}

function buildCredentialQuotaHtml(filename, data, context = {}) {

    if (data?.quota_type === 'account_billing') {
        return buildAccountBillingQuotaHtml(filename, data, context);
    }

    if (data?.quota_type === 'account_rate_limits') {
        return buildAccountRateLimitQuotaHtml(filename, data, context);
    }

    const models = data.models || {};
    const entries = Object.entries(models);
    const windows = Array.isArray(data.windows) ? data.windows : [];
    const summary = summarizeCredentialQuota(data);
    const resetTimes = entries
        .map(([, quotaData]) => quotaData?.resetTime)
        .filter(Boolean);
    const nextReset = resetTimes.length ? resetTimes.sort()[0] : '';
    const rows = renderMessageResultRows([
        [t('modal.provider'), context.providerName || t('provider_antigravity')],
        context.email ? [t('modal.account'), context.email] : [t('modal.credential'), filename],
        [t('modal.tracked_models'), entries.length],
        summary.label ? [t(windows.length ? 'modal.usage_limit' : 'modal.average_remaining'), summary.label] : null,
        nextReset ? [t('quota.next_reset'), formatQuotaResetTime(nextReset)] : null,
    ].filter(Boolean));

    if (entries.length === 0 && windows.length === 0) {

        return `
            <div class="message-result-panel">
                <div class="message-result-intro">${escapeHtml(t('modal.no_quota_intro'))}</div>
                <div class="message-result-section">
                    <div class="message-result-section-title">${escapeHtml(t('modal.quota_summary'))}</div>
                    <div class="message-result-summary">${rows}</div>
                </div>
                <div class="modal-empty-state">${escapeHtml(t('status_no_quota_info'))}</div>
            </div>
        `;

    }

    const cards = entries.map(([modelName, quotaData]) => {

        const fraction = credentialQuotaNumber(quotaData?.remaining);
        const remaining = fraction === null ? null : Math.min(100, Math.round(fraction * 100));
        return renderCredentialQuotaWindow({label: modelName, remaining_percentage: remaining,
            used_percentage: remaining === null ? null : 100 - remaining,
            reset_time: quotaData?.resetTimeRaw || quotaData?.resetTime});

    }).join('');

    return `
        <div class="message-result-panel">
            <div class="message-result-intro">${escapeHtml(t('modal.model_quota_intro'))}</div>
            <div class="message-result-section">
                <div class="message-result-section-title">${escapeHtml(t('modal.quota_summary'))}</div>
                <div class="message-result-summary">${rows}</div>
            </div>
            <div class="message-result-section">
                <div class="message-result-section-title">${escapeHtml(t('modal.model_quota'))}</div>
                <div class="modal-quota-grid">${cards}${windows.map(renderCredentialQuotaWindow).join('')}</div>
            </div>
        </div>
    `;

}

function summarizeCredentialQuota(data) {

    if (data?.quota_status === 'unavailable') {
        return { level: 'muted', label: t('quota_unavailable') };
    }

    if (data?.quota_type === 'account_billing') {
        const periods = [data.monthly, data.weekly, ...(Array.isArray(data.windows) ? data.windows : [])].filter(Boolean);
        const remainingValues = periods
            .map((period) => credentialQuotaNumber(period.remaining_percentage))
            .filter(Number.isFinite);
        if (!remainingValues.length) return { level: 'muted', label: t('modal.no_quota') };
        const remainingPercentage = Math.min(...remainingValues);
        return {
            level: quotaLevelFromUsedPercentage(100 - remainingPercentage),
            label: t('modal.percent_left', { value: remainingPercentage }),
            periodCount: periods.length,
        };
    }

    if (data?.quota_type === 'account_rate_limits') {
        const windows = Array.isArray(data.windows) ? data.windows : [];
        if (data.summary_mode === 'resource_balances') {
            const remaining = credentialQuotaNumber(data.summary_remaining_percentage);
            return remaining === null ? {level: 'muted', label: t('quota_unavailable')}
                : {level: quotaLevelFromUsedPercentage(100 - remaining), label: t('modal.percent_left', {value: remaining})};
        }
        const remainingValues = windows
            .map((windowData) => credentialQuotaNumber(windowData.remaining_percentage))
            .filter(Number.isFinite);
        if (!remainingValues.length) return { level: 'muted', label: t('modal.no_quota') };
        const remainingPercentage = Math.min(...remainingValues);
        return {
            level: quotaLevelFromUsedPercentage(100 - remainingPercentage),
            label: t('modal.percent_left', { value: remainingPercentage }),
            windowCount: windows.length,
        };
    }

    const models = data?.models || {};
    const entries = Object.entries(models);

    const windows = Array.isArray(data?.windows) ? data.windows : [];
    if (windows.length) {
        const values = [...windows.map(window => credentialQuotaNumber(window.remaining_percentage)),
            ...entries.map(([, quota]) => {
                const fraction = credentialQuotaNumber(quota?.remaining);
                return fraction === null ? null : Math.min(1, fraction) * 100;
            })].filter(Number.isFinite);
        if (!values.length) return {level: 'muted', label: t('quota_unavailable')};
        const remaining = Math.round(Math.min(...values));
        return {level: quotaLevelFromUsedPercentage(100 - remaining),
            label: t('modal.percent_left', {value: remaining}), windowCount: values.length};
    }

    if (!entries.length) {

        return {
            level: 'muted',
            label: t('modal.no_quota'),
        };

    }

    const fractions = entries.map(([, quota]) => credentialQuotaNumber(quota?.remaining)).filter(Number.isFinite);
    if (!fractions.length) return {level: 'muted', label: t('quota_unavailable')};
    const averageRemaining = Math.round(fractions.reduce((total, fraction) => total + Math.min(1, fraction) * 100, 0) / fractions.length);
    const usedPercentage = 100 - averageRemaining;
    const level = quotaLevelFromUsedPercentage(usedPercentage);

    return {
        level,
        label: t('modal.percent_left', { value: averageRemaining }),
        modelCount: fractions.length,
    };

}

function describeCredentialQuotaPreview(summary) {

    if (summary.modelCount) {
        return t('modal.average_quota_preview', { quota: summary.label, count: summary.modelCount });
    }

    if (summary.periodCount > 1) {
        return t('modal.lowest_billing_preview', { quota: summary.label, count: summary.periodCount });
    }

    if (summary.periodCount === 1) {
        return t('modal.billing_preview', { quota: summary.label });
    }

    if (summary.windowCount > 1) {
        return t('modal.lowest_window_preview', { quota: summary.label, count: summary.windowCount });
    }

    if (summary.windowCount === 1) {
        return t('modal.window_preview', { quota: summary.label });
    }

    return t('btn_view_quota_title');

}

function renderCredentialQuotaPreview(pathId, filename, managerType) {

    if (managerType !== 'primary') return '';

    const cached = AppState.quotaPreviewCache[filename] || {};
    const chipState = cached.loading
        ? { level: 'loading', label: t('quota_preview_loading'), title: t('card_loading_quota') }
        : cached.error
            ? { level: 'danger', label: t('quota_unavailable'), title: cached.error }
            : cached.summary
                ? {
                    level: cached.summary.level,
                    label: cached.summary.label,
                    title: describeCredentialQuotaPreview(cached.summary),
                }
                : { level: 'loading', label: t('quota_preview_loading'), title: t('card_loading_quota') };

    return `
        <button type="button" class="cred-quota-preview ${chipState.level}" id="quota-preview-${pathId}" data-quota-preview title="${escapeAttribute(chipState.title)}">
            <span>${escapeHtml(chipState.label)}</span>
        </button>
    `;

}

function updateCredentialQuotaPreview(pathId, filename) {

    updateCredentialSubscriptionBadge(pathId, filename);

    const chip = document.getElementById(`quota-preview-${pathId}`);

    if (!chip) return;

    chip.outerHTML = renderCredentialQuotaPreview(pathId, filename, 'primary');
    const updatedChip = document.getElementById(`quota-preview-${pathId}`);
    if (updatedChip) {
        updatedChip.addEventListener('click', () => loadPrimaryQuotaPreview(pathId));
    }

}

function updateCredentialSubscriptionBadge(pathId, filename) {

    const badge = document.getElementById(`subscription-plan-${pathId}`);
    if (!badge) return;

    const cached = AppState.quotaPreviewCache[filename] || {};
    if (cached.loading || cached.error) return;
    const cardContext = AppState.credentialCardIndex[pathId] || {};
    const isMuse = cardContext.providerVariant === 'muse_code';
    const plan = cached.data?.plan || (isMuse ? cached.data?.subscription_tier : null);
    const kind = isMuse ? (cached.data?.plan ? 'provider_plan' : 'provider_tier') : 'plan';
    const normalized = normalizeCredentialSubscriptionPlan(plan, kind);
    if (!normalized) return;
    credentialSubscriptionSnapshot(pathId, cardContext.providerVariant, plan, kind);
    cardContext.subscriptionPlan = plan;
    cardContext.subscriptionKind = kind;
    if (badge.querySelector('.credential-badge-label')?.textContent === normalized.label
        && badge.classList.contains(normalized.badgeClass)) return;
    badge.outerHTML = renderCredentialSubscriptionBadge(pathId, plan, kind);

}

function renderCredentialErrorDetails(parsedMsg) {

    const error = parsedMsg?.error;
    if (!error) return '';

    const rows = [];

    if (error.status) rows.push([t('modal.status'), error.status]);

    if (Array.isArray(error.details)) {

        error.details.forEach((detail, index) => {

            if (detail['@type']) rows.push([`${t('modal.type')} ${index + 1}`, detail['@type']]);
            if (detail.reason) rows.push([`${t('modal.reason')} ${index + 1}`, detail.reason]);

            if (detail.metadata && typeof detail.metadata === 'object') {

                Object.entries(detail.metadata).forEach(([key, value]) => {
                    rows.push([key, String(value)]);
                });

            }

        });

    }

    if (!rows.length) return '';

    return `<div class="message-error-meta">${renderMessageResultRows(rows)}</div>`;

}

function buildCredentialErrorsHtml(filename, data) {

    const errorCodes = data.error_codes || [];
    const errorMessages = data.error_messages || {};
    const rows = renderMessageResultRows([
        [t('table_filename'), filename],
        [t('modal.stored_errors'), errorCodes.length],
    ]);

    if (errorCodes.length === 0) {

        return `
            <div class="message-result-panel">
                <div class="message-result-intro">${escapeHtml(t('modal.no_errors_intro'))}</div>
                <div class="message-result-section">
                    <div class="message-result-section-title">${escapeHtml(t('modal.error_summary'))}</div>
                    <div class="message-result-summary">${rows}</div>
                </div>
                <div class="modal-empty-state success">
                    <strong>${escapeHtml(t('status_no_errors'))}</strong>
                    <span>${escapeHtml(t('status_credential_normal'))}</span>
                </div>
            </div>
        `;

    }

    const errorCards = errorCodes.map((errorCode) => {

        const messageStr = errorMessages[errorCode] || t('no_details_available');
        let displayMsg = messageStr;
        let detailsHtml = '';

        try {

            const parsedMsg = JSON.parse(messageStr);

            if (parsedMsg?.error?.message) displayMsg = parsedMsg.error.message;

            detailsHtml = renderCredentialErrorDetails(parsedMsg);

        } catch {

            detailsHtml = '';

        }

        return `
            <div class="message-error-card">
                <div class="message-error-title">${escapeHtml(t('error_code_prefix'))} ${escapeHtml(String(errorCode))}</div>
                <div class="message-error-copy">${highlightHttpLinks(escapeHtml(displayMsg))}</div>
                ${detailsHtml}
            </div>
        `;

    }).join('');

    return `
        <div class="message-result-panel">
            <div class="message-result-intro">${escapeHtml(t('modal.errors_intro'))}</div>
            <div class="message-result-section">
                <div class="message-result-section-title">${escapeHtml(t('modal.error_summary'))}</div>
                <div class="message-result-summary">${rows}</div>
            </div>
            <div class="message-result-section">
                <div class="message-result-section-title">${escapeHtml(t('error_details'))}</div>
                <div class="message-error-list">${errorCards}</div>
            </div>
        </div>
    `;

}
