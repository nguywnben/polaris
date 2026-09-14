async function verifyCredential(filename) {

    try {

        showStatus(t('verifying_project_id_please_wait'), 'info');

        const response = await fetch(`./api/credentials/verify/${encodeURIComponent(filename)}`, {

            method: 'POST',

            headers: getAuthHeaders()

        });

        const data = await response.json();

        if (response.ok && data.success) {

            showStatus(data.message || t('credentials.verified'), 'success');

            showMessageModal(t('credential_verification_title'), buildCredentialVerificationHtml(filename, data), 'success', {html: true});

            await AppState.creds.refresh();

        } else {

            const errorMsg = data.message || t('verification_failed');

            showStatus(errorMsg, 'error');

            showMessageModal(t('credential_verification_title'), t('verification_failednnerrormsg', {errorMsg: errorMsg}), 'error');

        }

    } catch (error) {

        const errorMsg = t('verification_failed_errormessage', {error_message: error.message});

        showStatus(errorMsg, 'error');

        showMessageModal(t('credential_verification_title'), errorMsg, 'error');

    }

}

async function verifyProviderCredential(filename) {

    try {

        showStatus(t('verifying_primary_project_id_pl'), 'info');

        const response = await fetch(`./api/credentials/verify/${encodeURIComponent(filename)}?mode=provider`, {

            method: 'POST',

            headers: getAuthHeaders()

        });

        const data = await response.json();

        if (response.ok && data.success) {

            showStatus(data.message || t('credentials.verified'), 'success');

            showMessageModal(t('credential_verification_title'), buildCredentialVerificationHtml(filename, data), 'success', {html: true});

            await AppState.primaryCreds.refresh();

        } else {

            const errorMsg = data.message || t('verification_failed');

            showStatus(errorMsg, 'error');

            showMessageModal(t('credential_verification_title'), t('verification_failednnerrormsg', {errorMsg: errorMsg}), 'error');

        }

    } catch (error) {

        const errorMsg = t('verification_failed_errormessage', {error_message: error.message});

        showStatus(errorMsg, 'error');

        showMessageModal(t('credential_verification_title'), errorMsg, 'error');

    }

}

async function testCredential(filename, model, signal) {

    try {

        showStatus(t('testing_model_please_wait'), 'info');

        const response = await fetch(`./api/credentials/test/${encodeURIComponent(filename)}`, {

            method: 'POST',

            headers: getAuthHeaders(),

            body: JSON.stringify({ model }),

            signal

        });

        const data = await response.json();

        const logicalStatus = data.status_code || response.status;
        const isLimited = logicalStatus === 429 && data.success === true;

        if (response.status === 200 || isLimited) {

            const resultHtml = buildCredentialTestResultHtml(filename, data, response, { mode: 'Code Assist' });

            showStatus(
                isLimited ? (data?.diagnostic?.message || t('credential_rate_limited')) : t('test_successful'),
                isLimited ? 'warning' : 'success'
            );

            await AppState.creds.refresh();

            return {
                html: resultHtml,
                type: isLimited ? 'info' : 'success'
            };

        }

        else {

            const errorDetails = buildCredentialTestErrorHtml(filename, data, response);

            const message = data?.diagnostic?.message || data.message || `${t('http_code_prefix')} ${data.status_code || response.status}`;

            showStatus(t('credentials.test_failed', {error: message}), 'error');

            return {
                html: errorDetails,
                type: 'error'
            };

        }

    } catch (error) {

        if (signal?.aborted || error?.name === 'AbortError') {

            showStatus(t('credential_test_cancelled'), 'info');

            return {type: 'info', html: ''};

        }

        const errorMsg = t('test_failed_errormessage', {error_message: error.message});

        showStatus(errorMsg, 'error');

        return {
            type: 'error',
            html: buildApiResultHtml({
                intro: t('verification_failed'),
                rows: [
                    ['Result', 'Failed'],
                    [t('table_filename'), filename],
                    ['Model', model],
                ],
                summaryLabel: t('modal.error_summary'),
                note: errorMsg,
            })
        };

    }

}

async function testPrimaryCredential(filename, model, signal) {

    try {

        showStatus(t('testing_model_please_wait'), 'info');

        const response = await fetch(`./api/credentials/test/${encodeURIComponent(filename)}?mode=provider`, {

            method: 'POST',

            headers: getAuthHeaders(),

            body: JSON.stringify({ model }),

            signal

        });

        const data = await response.json();

        const logicalStatus = data.status_code || response.status;
        const isLimited = logicalStatus === 429 && data.success === true;

        if (response.status === 200 || isLimited) {

            const resultHtml = buildCredentialTestResultHtml(filename, data, response, { mode: 'Provider' });

            showStatus(
                isLimited ? (data?.diagnostic?.message || t('credential_rate_limited')) : t('test_successful'),
                isLimited ? 'warning' : 'success'
            );

            await AppState.primaryCreds.refresh();

            return {
                html: resultHtml,
                type: isLimited ? 'info' : 'success'
            };

        }

        else {

            const errorDetails = buildCredentialTestErrorHtml(filename, data, response);

            const message = data?.diagnostic?.message || data.message || `${t('http_code_prefix')} ${data.status_code || response.status}`;

            showStatus(t('credentials.test_failed', {error: message}), 'error');

            return {
                html: errorDetails,
                type: 'error'
            };

        }

    } catch (error) {

        if (signal?.aborted || error?.name === 'AbortError') {

            showStatus(t('credential_test_cancelled'), 'info');

            return {type: 'info', html: ''};

        }

        const errorMsg = t('test_failed_errormessage', {error_message: error.message});

        showStatus(errorMsg, 'error');

        return {
            type: 'error',
            html: buildApiResultHtml({
                intro: t('verification_failed'),
                rows: [
                    ['Result', 'Failed'],
                    [t('table_filename'), filename],
                    ['Model', model],
                ],
                summaryLabel: t('modal.error_summary'),
                note: errorMsg,
            })
        };

    }

}

async function configurePreviewChannel(filename) {

    try {

        showStatus(t('configuring_preview_channel_please'), 'info');

        const response = await fetch(`./api/credentials/configure-preview/${encodeURIComponent(filename)}`, {

            method: 'POST',

            headers: getAuthHeaders()

        });

        const data = await response.json();

        if (response.ok && data.success) {

            const successMsg = `${t('status_action_success', {action: t('btn_setup_preview')})}\n${t('table_filename')}: ${filename}\n${t('credential_status_label')} ${data.message}`;

            showStatus(successMsg.replace(/\n/g, '<br>'), 'success');

            showMessageModal(t('preview_configuration_title'), `${t('status_action_success', {action: t('btn_setup_preview')})}\n\n${t('table_filename')}: ${filename}\n\n${data.message}\n\n${t('runtime.setting_id')}: ${data.setting_id || 'N/A'}\n${t('runtime.binding_id')}: ${data.binding_id || 'N/A'}`, 'success');

            await AppState.creds.refresh();

        } else {

            const errorMsg = data.message || t('configuration_failed');

            const errorDetail = data.error || '';

            const step = data.step || '';

            let alertMsg = `${t('status_action_failed', {error: t('btn_setup_preview')})}\n\n${t('table_filename')}: ${filename}\n\n${errorMsg}`;

            if (step) {

                alertMsg += t('nfailed_step_step', {step: step});

            }

            if (errorDetail) {

                alertMsg += t('nnerror_details_errordetail', {errorDetail: errorDetail});

            }

            showStatus(errorMsg, 'error');

            showMessageModal(t('preview_configuration_title'), alertMsg, 'error');

        }

    } catch (error) {

        const errorMsg = t('failed_to_configure_preview_channel', {error_message: error.message});

        showStatus(errorMsg, 'error');

        showMessageModal(t('preview_configuration_title'), errorMsg, 'error');

    }

}

async function togglePrimaryQuotaDetails(pathId) {

    const context = getCredentialModalContext(pathId, AppState.primaryCreds);
    const { filename } = context;

    if (!filename) return;

    showStatus(t('card_loading_quota'), 'info');

    try {

        const { response, data } = await fetchPrimaryQuota(filename);

        if (response.ok && data.success) {

            AppState.quotaPreviewCache[filename] = {
                summary: summarizeCredentialQuota(data),
                data,
            };

            updateCredentialQuotaPreview(pathId, filename);

            showMessageModal(t('quota_details'), buildCredentialQuotaHtml(filename, data, context), 'info', {html: true});

        } else {

            const errorMsg = data.error || t('failed_to_get_quota_information');

            AppState.quotaPreviewCache[filename] = { error: errorMsg };

            updateCredentialQuotaPreview(pathId, filename);

            showStatus(errorMsg, 'error');

            showMessageModal(t('quota_details'), errorMsg, 'error');

        }

    } catch (error) {

        const errorMsg = t('failed_to_get_quota_information_err', {error_message: error.message});

        AppState.quotaPreviewCache[filename] = { error: errorMsg };

        updateCredentialQuotaPreview(pathId, filename);

        showStatus(errorMsg, 'error');

        showMessageModal(t('quota_details'), errorMsg, 'error');

    }

}

async function fetchPrimaryQuota(filename) {

    const response = await fetch(`./api/credentials/quota/${encodeURIComponent(filename)}?mode=provider`, {

        method: 'GET',

        headers: getAuthHeaders()

    });

    const data = await response.json();

    return { response, data };

}

async function loadPrimaryQuotaPreview(pathId) {

    const { filename } = getCredentialModalContext(pathId, AppState.primaryCreds);

    if (!filename) return;

    AppState.quotaPreviewCache[filename] = { loading: true };

    updateCredentialQuotaPreview(pathId, filename);

    try {

        const { response, data } = await fetchPrimaryQuota(filename);

        if (response.ok && data.success) {

            AppState.quotaPreviewCache[filename] = {
                summary: summarizeCredentialQuota(data),
                data,
            };

        } else {

            AppState.quotaPreviewCache[filename] = {
                error: data.error || t('failed_to_get_quota_information'),
            };

        }

    } catch (error) {

        AppState.quotaPreviewCache[filename] = {
            error: t('failed_to_get_quota_information_err', {error_message: error.message}),
        };

    } finally {

        updateCredentialQuotaPreview(pathId, filename);

    }

}

// =====================================================================

// =====================================================================

async function toggleErrorDetails(pathId) {

    await toggleErrorDetailsCommon(pathId, AppState.creds);

}

async function togglePrimaryErrorDetails(pathId) {

    await toggleErrorDetailsCommon(pathId, AppState.primaryCreds);

}

async function toggleErrorDetailsCommon(pathId, manager) {

    const { filename, manager: resolvedManager } = getCredentialModalContext(pathId, manager);

    if (!filename) return;

    showStatus(t('card_loading_errors'), 'info');

    try {

        const modeParam = resolvedManager.type === 'primary' ? 'mode=provider' : 'mode=code_assist';

        const response = await fetch(`./api/credentials/errors/${encodeURIComponent(filename)}?${modeParam}`, {

            method: 'GET',

            headers: getAuthHeaders()

        });

        const data = await response.json();

        if (response.ok) {

            showMessageModal(t('btn_view_errors'), buildCredentialErrorsHtml(filename, data), 'info', {html: true});

        } else {

            const errorMsg = data.detail || data.error || t('failed_to_fetch_error_message');

            showStatus(t('failed_to_fetch_error_message_error', {errorMsg: errorMsg}), 'error');

            showMessageModal(t('btn_view_errors'), errorMsg, 'error');

        }

    } catch (error) {

        const errorMsg = t('failed_to_fetch_error_information_e', {error_message: error.message});

        showStatus(errorMsg, 'error');

        showMessageModal(t('btn_view_errors'), errorMsg, 'error');

    }

}

function highlightHttpLinks(text) {

    const urlRegex = /(https?:\/\/[^\s<>"]+)/gi;

    return text.replace(urlRegex, function(url) {

        return t('a_hrefurl_target_blank_stylecolor_0', {url: url, url: url, url: url});

    });

}
