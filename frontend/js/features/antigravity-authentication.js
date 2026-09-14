async function startPrimaryAuth() {

    const btn = document.getElementById('getPrimaryAuthBtn');

    btn.disabled = true;

    btn.textContent = t('generating_authentication_link');

    try {

        showStatus(t('generating_primary_authenticati'), 'info');

        const response = await fetch('./api/auth/start', {

            method: 'POST',

            headers: getAuthHeaders(),

            body: JSON.stringify({ mode: 'provider' })

        });

        const data = await response.json();

        if (response.ok) {

            AppState.primaryAuthState = data.state;

            AppState.primaryAuthInProgress = true;

            AppState.primaryCredentialFilename = '';

            const authUrlLink = document.getElementById('primaryAuthUrl');

            authUrlLink.href = data.auth_url;

            authUrlLink.textContent = data.auth_url;

            document.getElementById('primaryAuthUrlSection').classList.remove('hidden');
            document.getElementById('primarySaveResult')?.classList.add('hidden');
            document.getElementById('primaryCredsSection')?.classList.add('hidden');
            const primaryCallbackUrlInput = document.getElementById('primaryCallbackUrlInput');
            if (primaryCallbackUrlInput) primaryCallbackUrlInput.value = '';
            updatePrimaryCallbackUrlPlaceholder(data.callback_url);
            setPrimaryCallbackUrlSectionVisible(true);
            const primaryCredsContent = document.getElementById('primaryCredsContent');
            if (primaryCredsContent) primaryCredsContent.textContent = '';

            showStatus(t('primary_authentication_link_gen'), 'success');

        } else {
            const requestError = createProviderRequestError(response, data);
            showStatus(t('error_dataerror_failed_to_generate', {
                data_error: formatProviderRequestError(requestError)
            }), 'error');

        }

    } catch (error) {

        showStatus(t('status_net_error', {error: formatProviderRequestError(error)}), 'error');

    } finally {

        btn.disabled = false;

        btn.textContent = t('get_primary_authentication_link');

    }

}

function setPrimaryCallbackUrlSectionVisible(visible, focusInput = false) {
    const section = document.getElementById('primaryCallbackUrlSection');
    const input = document.getElementById('primaryCallbackUrlInput');
    if (!section) return;
    section.classList.toggle('hidden', !visible);
    if (visible && focusInput && input) {
        input.focus();
        input.select();
    }
}

function updatePrimaryCallbackUrlPlaceholder(callbackUrl = '') {
    const input = document.getElementById('primaryCallbackUrlInput');
    if (!input) return;

    const callbackBase = callbackUrl || 'http://localhost:4283/callback';
    input.placeholder = `${callbackBase}?state=...&code=...`;
}

function getPrimaryCallbackUrl() {
    return document.getElementById('primaryCallbackUrlInput')?.value.trim() || '';
}

function validateCallbackUrl(callbackUrl) {
    if (!callbackUrl) {
        showStatus(t('please_enter_the_callback_url'), 'error');
        return false;
    }

    if (!callbackUrl.startsWith('http://') && !callbackUrl.startsWith('https://')) {
        showStatus(t('please_enter_a_valid_url_starting_w'), 'error');
        return false;
    }

    if (!callbackUrl.includes('code=') || !callbackUrl.includes('state=')) {
        showStatus(t('this_is_not_a_valid_callback_url_pl'), 'error');
        return false;
    }

    return true;
}

async function completePrimaryCredentialSave(data) {
    const credentialSaved = data.credential_saved !== false;
    const credentialAction = data.credential_action || 'created';
    const resultTitle = credentialAction === 'skipped'
        ? t('provider_credential_skipped_title')
        : credentialAction === 'replaced'
            ? t('provider_credential_replaced_title')
            : t('provider_credential_saved_title');
    const fileSuffix = data.file_path ? ` File: ${data.file_path}.` : '';
    const resultBody = data.message
        ? `${data.message}${data.message.endsWith('.') ? '' : '.'}${fileSuffix}`
        : credentialSaved
            ? t('provider_credential_saved_body', {data_file_path: data.file_path})
            : t('provider_credential_skipped_body', {data_file_path: data.file_path});

    const primaryCredsSection = document.getElementById('primaryCredsSection');
    const primaryCredsContent = document.getElementById('primaryCredsContent');
    const primaryCredsDownloadBtn = document.getElementById('primaryCredsDownloadBtn');

    if (credentialSaved) {
        primaryCredsContent.textContent = JSON.stringify(data.credentials, null, 2);
        primaryCredsSection.classList.remove('hidden');
        primaryCredsDownloadBtn?.classList.remove('hidden');
        AppState.primaryCredentialFilename = getDownloadFilename(data.file_path, `primary-credential-${Date.now()}.json`);
    } else {
        primaryCredsContent.textContent = '';
        primaryCredsSection.classList.add('hidden');
        primaryCredsDownloadBtn?.classList.add('hidden');
        AppState.primaryCredentialFilename = '';
    }

    AppState.primaryAuthInProgress = false;
    setPrimaryCallbackUrlSectionVisible(false);
    resetProviderTransientSecrets('antigravity.oauth');

    const saveResult = document.getElementById('primarySaveResult');
    const saveResultTitle = document.getElementById('primarySaveResultTitle');
    const saveResultText = document.getElementById('primarySaveResultText');
    if (saveResult && saveResultText) {
        if (saveResultTitle) saveResultTitle.textContent = resultTitle;
        saveResultText.textContent = resultBody;
        saveResult.classList.remove('hidden');
    }

    try {
        await AppState.primaryCreds.refresh();
        await refreshUsageStats();
    } catch (refreshError) {
        console.warn('Credential flow completed, but pool refresh failed:', refreshError);
    }

    showStatus(resultBody, credentialSaved ? 'success' : 'info');
}

async function getPrimaryCredentials() {

    if (!AppState.primaryAuthInProgress) {

        showStatus(t('please_obtain_the_primary_authe'), 'error');

        return;

    }

    const btn = document.getElementById('getPrimaryCredsBtn');

    btn.disabled = true;

    btn.textContent = t('checking_provider_authorization');

    try {

        const callbackUrl = getPrimaryCallbackUrl();
        if (callbackUrl) {
            if (!validateCallbackUrl(callbackUrl)) return;
            await savePrimaryCredentialsFromCallbackUrl(callbackUrl, btn);
            return;
        }

        showStatus(t('checking_provider_authorization'), 'info');

        const state = AppState.primaryAuthState;
        const statusResponse = await fetch(`./api/auth/status?state=${encodeURIComponent(state)}`, {
            headers: getAuthHeaders()
        });
        const statusData = await statusResponse.json().catch(() => ({}));

        if (!statusResponse.ok) {
            showStatus(t('error_dataerror_failed_to_get_authe', {data_error: statusData.detail || statusData.error || t('unknown_error')}), 'error');
            return;
        }

        if (statusData.status === 'not_found') {
            AppState.primaryAuthInProgress = false;
            showStatus(t('provider_authorization_expired'), 'error');
            return;
        }

        if (statusData.status !== 'completed') {
            setPrimaryCallbackUrlSectionVisible(true, true);
            showStatus(t('provider_authorization_pending'), 'info');
            return;
        }

        btn.textContent = t('saving_provider_credentials');

        showStatus(t('saving_provider_credentials'), 'info');

        const response = await fetch('./api/auth/callback', {

            method: 'POST',

            headers: getAuthHeaders(),

            body: JSON.stringify({ mode: 'provider' })

        });

        const data = await response.json();

        if (response.ok) {

            await completePrimaryCredentialSave(data);

        } else {
            const requestError = createProviderRequestError(response, data);
            showStatus(t('error_dataerror_failed_to_get_authe', {
                data_error: formatProviderRequestError(requestError)
            }), 'error');

        }

    } catch (error) {

        showStatus(t('status_net_error', {error: formatProviderRequestError(error)}), 'error');

    } finally {

        btn.disabled = false;

        btn.textContent = t('fetch_primary_credentials');

    }

}

async function savePrimaryCredentialsFromCallbackUrl(callbackUrl, btn = document.getElementById('getPrimaryCredsBtn')) {
    try {
        if (btn) btn.textContent = t('saving_provider_credentials');
        showStatus(t('saving_provider_credentials_from_callback'), 'info');

        const response = await fetch('./api/auth/callback-url', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ callback_url: callbackUrl, mode: 'provider' })
        });

        const data = await response.json().catch(() => ({}));

        if (response.ok) {
            await completePrimaryCredentialSave(data);
            const input = document.getElementById('primaryCallbackUrlInput');
            if (input) input.value = '';
        } else {
            showStatus(formatProviderRequestError(createProviderRequestError(response, data)), 'error');
        }
    } catch (error) {
        showStatus(t('failed_to_retrieve_credentials_from_dup', {
            error_message: formatProviderRequestError(error)
        }), 'error');
    }
}

function getDownloadFilename(filePath, fallback) {

    const rawName = String(filePath || '').split(/[\\/]/).pop().trim();

    return rawName || fallback;

}

function downloadPrimaryCredentials() {

    const content = document.getElementById('primaryCredsContent').textContent;

    const blob = new Blob([content], { type: 'application/json' });

    const url = window.URL.createObjectURL(blob);

    const a = document.createElement('a');

    a.href = url;

    a.download = getDownloadFilename(AppState.primaryCredentialFilename, `primary-credential-${Date.now()}.json`);

    a.click();

    window.URL.revokeObjectURL(url);

}

// =====================================================================

// =====================================================================

function toggleProjectIdSection() {

    const section = document.getElementById('projectIdSection');

    const icon = document.getElementById('projectIdToggleIcon');

    if (section.style.display === 'none') {

        section.style.display = 'block';

        icon.style.transform = 'rotate(90deg)';

        icon.textContent = '';

    } else {

        section.style.display = 'none';

        icon.style.transform = 'rotate(0deg)';

        icon.textContent = '';

    }

}

function toggleCallbackUrlSection() {

    const section = document.getElementById('callbackUrlSection');

    const icon = document.getElementById('callbackUrlToggleIcon');

    if (section.style.display === 'none') {

        section.style.display = 'block';

        icon.style.transform = 'rotate(180deg)';

        icon.textContent = '';

    } else {

        section.style.display = 'none';

        icon.style.transform = 'rotate(0deg)';

        icon.textContent = '';

    }

}

async function processCallbackUrl() {

    const callbackUrl = document.getElementById('callbackUrlInput').value.trim();

    if (!callbackUrl) {

        showStatus(t('please_enter_the_callback_url'), 'error');

        return;

    }

    if (!callbackUrl.startsWith('http://') && !callbackUrl.startsWith('https://')) {

        showStatus(t('please_enter_a_valid_url_starting_w'), 'error');

        return;

    }

    if (!callbackUrl.includes('code=') || !callbackUrl.includes('state=')) {

        showStatus(t('this_is_not_a_valid_callback_url_pl'), 'error');

        return;

    }

    showStatus(t('retrieving_credentials_from_callbac'), 'info');

    try {

        const projectId = document.getElementById('projectId')?.value.trim() || null;

        const response = await fetch('./api/auth/callback-url', {

            method: 'POST',

            headers: getAuthHeaders(),

            body: JSON.stringify({ callback_url: callbackUrl, project_id: projectId })

        });

        const result = await response.json();

        if (result.credentials) {

            showStatus(result.message || t('credentials_fetched_successfully_fr'), 'success');

            const credentialsContent = document.getElementById('credentialsContent');
            const pre = document.createElement('pre');
            pre.textContent = JSON.stringify(result.credentials, null, 2);
            credentialsContent.replaceChildren(pre);

            document.getElementById('credentialsSection').classList.remove('hidden');

        } else if (result.requires_manual_project_id) {

            showStatus(t('manual_project_id_specification_req'), 'error');

        } else if (result.requires_project_selection) {

            let msg = t('brstrongavailable_projectsstrongbr');

            result.available_projects.forEach(p => {

                msg += `- ${p.name} (ID: ${p.project_id})<br>`;

            });

            showStatus(t('multiple_projects_detected_please_s') + msg, 'error');

        } else {

            showStatus(result.detail || result.error || t('failed_to_fetch_credentials_from_ca'), 'error');

        }

        document.getElementById('callbackUrlInput').value = '';

    } catch (error) {

        showStatus(t('failed_to_retrieve_credentials_from_dup', {error_message: error.message}), 'error');

    }

}

// =====================================================================

// =====================================================================
