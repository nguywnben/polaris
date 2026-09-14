function linkifyText(text) {

    if (!text) return text;

    const urlPattern = /(https?:\/\/[^\s"'<>()[\]{}]+)|(www\.[^\s"'<>()[\]{}]+)/gi;

    return text.replace(urlPattern, function(url) {

        let href = url;

        if (url.startsWith('www.')) {

            href = 'https://' + url;

        }

        const safeHref = href.replaceAll('&amp;', '&');
        return `<a href="${escapeAttribute(safeHref)}" target="_blank" rel="noopener noreferrer" class="message-link" title="${escapeAttribute(`${t('click_to_open_link')} ${t('right_click_to_copy_link')}`)}">${url}</a>`;

    });

}

function showMessageModal(title, message, type = 'info', options = {}) {

    const modal = document.createElement('div');

    modal.className = 'message-modal-overlay';
    const safeType = String(type || 'info').replace(/[^\w-]/g, '') || 'info';
    const safeTitle = escapeHtml(title);
    const safeTitleAttribute = escapeAttribute(title);
    const normalizedMessage = normalizeDialogMessage(message);
    const bodyContent = options.html
        ? String(message || '')
        : `<div class="message-modal-copy">${linkifyText(escapeHtml(normalizedMessage)).replace(/\n/g, '<br>')}</div>`;

    modal.innerHTML = `

        <div class="message-modal informational ${safeType}" role="dialog" aria-modal="true" aria-label="${safeTitleAttribute}">

            <div class="message-modal-header">

                <h3>${safeTitle}</h3>

            </div>

            <div class="message-modal-body">

                ${bodyContent}

            </div>

            <div class="message-modal-footer">

                <button type="button" class="message-modal-btn" data-dialog-close>${escapeHtml(t('btn_close'))}</button>

            </div>

        </div>

    `;

    let closed = false;

    const close = () => {

        if (closed) return;

        closed = true;

        document.removeEventListener('keydown', escHandler);

        void unmountModal(modal);

    };

    modal.addEventListener('click', function(e) {

        if (e.target === modal || e.target.closest('[data-dialog-close]')) close();

    });

    const escHandler = function(e) {

        if (e.key === 'Escape') close();

    };

    document.addEventListener('keydown', escHandler);

    void mountModal(modal);

    return modal;

}

function normalizeDialogMessage(message) {

    return String(message || '').replace(/\\n/g, '\n');

}

function renderDialogMessage(message, options = {}) {

    const escaped = escapeHtml(normalizeDialogMessage(message));

    if (options.compact) {

        return escaped
            .replace(/\n{2,}/g, '<span class="message-modal-break"></span>')
            .replace(/\n/g, '<br>');

    }

    return escaped.replace(/\n/g, '<br>');

}

function stringifyModalDetail(value) {

    if (value === undefined || value === null || value === '') return '';

    if (typeof value === 'string') return normalizeDialogMessage(value);

    try {

        return JSON.stringify(value, null, 2);

    } catch {

        return String(value);

    }

}

function buildMessageResultDetails(label, value, options = {}) {

    const text = stringifyModalDetail(value);

    if (!text) return '';

    return `
        <details class="message-result-details"${options.open ? ' open' : ''}>
            <summary>${escapeHtml(label || t('runtime.details'))}</summary>
            <pre>${escapeHtml(text)}</pre>
        </details>
    `;

}

function buildApiResultHtml(options = {}) {

    const introHtml = options.intro
        ? `<div class="message-result-intro">${renderDialogMessage(ensureTerminalPunctuation(options.intro))}</div>`
        : '';

    const headingHtml = options.heading
        ? `<div class="message-result-heading">${escapeHtml(options.heading)}</div>`
        : '';

    const summaryHtml = options.rows?.length
        ? `
            <div class="message-result-section">
                <div class="message-result-section-title">${escapeHtml(options.summaryLabel || t('runtime.summary'))}</div>
                <div class="message-result-summary">${renderMessageResultRows(options.rows)}</div>
            </div>
        `
        : '';

    const noteHtml = options.note
        ? `<div class="message-result-note">${renderDialogMessage(ensureTerminalPunctuation(options.note))}</div>`
        : '';

    const detailsHtml = buildMessageResultDetails(
        options.detailsLabel || t('runtime.details'),
        options.details,
        { open: options.detailsOpen }
    );

    return `
        <div class="message-result-panel">
            ${introHtml}
            ${headingHtml}
            ${summaryHtml}
            ${noteHtml}
            ${options.extraHtml || ''}
            ${detailsHtml}
        </div>
    `;

}

function buildCredentialTestErrorHtml(filename, data, response) {

    const diagnostic = data?.diagnostic;
    if (diagnostic && diagnostic.schema_version === 1 && diagnostic.message) {
        const category = String(diagnostic.category || t('unknown_error')).replaceAll('_', ' ');
        const providerStatus = diagnostic.provider_status || data.status_code || response.status;
        const safeDetails = {
            schema_version: diagnostic.schema_version,
            code: diagnostic.code,
            category: diagnostic.category,
            retryable: diagnostic.retryable === true,
            ...(diagnostic.provider_status ? {provider_status: diagnostic.provider_status} : {}),
            ...(diagnostic.provider_code ? {provider_code: diagnostic.provider_code} : {}),
        };

        return buildApiResultHtml({
            intro: diagnostic.message,
            rows: [
                [t('table_filename'), filename],
                [t('provider_diagnostic_category'), category],
                [t('provider_diagnostic_provider_status'), providerStatus],
                diagnostic.provider_code
                    ? [t('provider_diagnostic_provider_code'), diagnostic.provider_code]
                    : null,
                data.provider ? [t('provider'), getCredentialProviderMeta(data, 'usage').name] : null,
                data.model ? [t('modal.model'), data.model] : null,
            ].filter(Boolean),
            summaryLabel: t('modal.error_summary'),
            note: diagnostic.remediation
                ? `${t('provider_diagnostic_next_step')}: ${diagnostic.remediation}`
                : '',
            detailsLabel: t('error_details'),
            details: safeDetails,
        });
    }

    let parsedError = null;
    const rawErrorValue = data?.error || data?.detail || data?.message || '';
    if (rawErrorValue) {
        try {
            parsedError = typeof rawErrorValue === 'string' ? JSON.parse(rawErrorValue) : rawErrorValue;
        } catch {
            parsedError = null;
        }
    }

    const errorRoot = parsedError?.error || parsedError || {};
    const firstDetail = Array.isArray(errorRoot.details) ? errorRoot.details[0] || {} : {};
    const metadata = firstDetail.metadata || {};
    const httpCode = errorRoot.code || data.status_code || response.status;
    const statusText = errorRoot.status || data.message || data.detail || data.error || t('unknown_error');
    const reason = firstDetail.reason || '';
    const permission = metadata.permission || '';
    const resource = metadata.resource || '';
    const troubleshooterUrl = safeHttpUrl(metadata.troubleshooter_url);
    const rawDetails = parsedError
        ? JSON.stringify(parsedError, null, 2)
        : String(data.detail || data.error || data.message || `${t('http_code_prefix')} ${httpCode}`);

    const summaryRows = [
        [t('table_filename'), filename],
        [t('http_code_prefix'), httpCode],
        [t('credential_status_label').replace(':', ''), statusText],
        data.provider ? [t('provider'), getCredentialProviderMeta(data, 'usage').name] : null,
        data.model ? [t('modal.model'), data.model] : null,
        reason ? [t('modal.reason'), reason] : null,
        permission ? [t('runtime.permission'), permission] : null,
        resource ? [t('runtime.resource'), resource] : null,
    ].filter(Boolean);

    const troubleshooterHtml = troubleshooterUrl
        ? `<div class="message-result-actions"><a class="message-link" href="${escapeAttribute(troubleshooterUrl)}" target="_blank" rel="noopener noreferrer">${t('open_troubleshooter')}</a></div>`
        : '';

    return buildApiResultHtml({
        intro: t('credentials.test_failed', {error: statusText}),
        rows: summaryRows,
        summaryLabel: t('modal.error_summary'),
        extraHtml: troubleshooterHtml,
        detailsLabel: t('error_details'),
        details: rawDetails,
        detailsOpen: true,
    });

}

function buildCredentialTestResultHtml(filename, data, response, options = {}) {

    const logicalStatus = data.status_code || response.status;
    const diagnostic = data?.diagnostic?.schema_version === 1 ? data.diagnostic : null;
    const isLimited = logicalStatus === 429 && data.success === true;
    const statusMessage = isLimited
        ? (diagnostic?.message || t('credential_rate_limited'))
        : (data.message || t('credential_available'));

    return buildApiResultHtml({
        intro: isLimited
            ? statusMessage
            : t('test_successful'),
        rows: [
            [t('status'), isLimited
                ? String(diagnostic?.category || t('runtime.rate_limited')).replaceAll('_', ' ')
                : t('success')],
            [t('table_filename'), filename],
            [t('http_code_prefix'), logicalStatus || response.status],
            [t('credential_status_label').replace(':', ''), statusMessage],
            data.provider ? [t('provider'), getCredentialProviderMeta(data, 'usage').name] : null,
            data.model ? [t('modal.model'), data.model] : null,
            options.mode ? [t('runtime.mode'), options.mode] : null,
            diagnostic?.category
                ? [t('provider_diagnostic_category'), String(diagnostic.category).replaceAll('_', ' ')]
                : null,
            diagnostic?.provider_code
                ? [t('provider_diagnostic_provider_code'), diagnostic.provider_code]
                : null,
        ].filter(Boolean),
        summaryLabel: t('modal.model_test_title'),
        note: diagnostic?.remediation
            ? `${t('provider_diagnostic_next_step')}: ${diagnostic.remediation}`
            : '',
    });

}

function normalizeVerificationMessage(message) {

    return String(message || '')
        .replace(/^verification successful\.?\s*/i, '')
        .replace(/^validation successful\.?\s*/i, '')
        .trim();

}

function buildCredentialVerificationHtml(filename, data) {

    const rows = [
        [t('status'), t('success')],
        [t('table_filename'), filename],
        data.project_id ? [t('modal.project_id'), data.project_id] : null,
        data.subscription_tier ? [t('tier'), data.subscription_tier] : null,
        data.credit_amount !== undefined && data.credit_amount !== null ? [t('credits_label'), data.credit_amount] : null,
        data.provider ? [t('provider'), getCredentialProviderMeta({ provider: data.provider }, 'usage').name] : null,
        Number.isFinite(Number(data.model_count)) ? [t('modal.available_models'), Number(data.model_count)] : null,
    ].filter(Boolean);

    const detailMessage = normalizeVerificationMessage(data.message);

    return buildApiResultHtml({
        intro: t('credentials.verified'),
        rows,
        summaryLabel: t('credential_verification_title'),
        note: detailMessage,
    });

}

function renderMessageResultRows(rows) {

    return rows.filter(Boolean).map(([label, value]) => `
        <div class="message-result-row">
            <div class="message-result-label">${escapeHtml(label)}</div>
            <div class="message-result-value">${escapeHtml(String(value))}</div>
        </div>
    `).join('');

}
