// Polaris management console: console.

function setSetupSecretVisibility(input, visible) {
    if (!input) return;
    input.type = visible ? 'text' : 'password';
    document.getElementById(`${input.id}Toggle`)?.setAttribute('aria-pressed', String(visible));
}

function toggleSetupSecret(button) {
    const input = document.getElementById(button.getAttribute('aria-controls'));
    if (!input || input.matches(':disabled')) return;
    setSetupSecretVisibility(input, input.type === 'password');
}

function setupPasswordChecks(password, confirmation) {
    // Mirrors validate_owner_password; parity is guarded by test_password_checklist.py.
    const common = ['administrator', 'letmein123456', 'polaris', 'password1234', 'qwerty123456'];
    const characters = Array.from(password);
    // Case-fold variants that can map to characters in the server's ASCII blocklist.
    const folded = password.toLowerCase().replace(/ſ/g, 's').replace(/ß/g, 'ss');
    return {
        length: characters.length >= 12 && characters.length <= 256,
        variety: new Set(characters).size >= 4,
        uncommon: characters.length > 0 && !common.includes(folded),
        match: characters.length > 0 && password === confirmation
    };
}

function renderSetupPasswordChecks() {
    const password = document.getElementById('setupPassword')?.value || '';
    const confirmation = document.getElementById('setupPasswordConfirm')?.value || '';
    const checks = setupPasswordChecks(password, confirmation);
    if (checks.match) {
        const confirmInput = document.getElementById('setupPasswordConfirm');
        confirmInput.removeAttribute('aria-invalid');
        confirmInput.removeAttribute('data-validation-error');
    }
    document.querySelectorAll('[data-password-check]').forEach(item => {
        const met = String(checks[item.dataset.passwordCheck]);
        if (item.dataset.met === met) return;
        item.dataset.met = met;
        const state = item.querySelector('[data-password-check-state]');
        state.dataset.i18n = met === 'true' ? 'password_check_met' : 'password_check_pending';
        state.textContent = t(state.dataset.i18n);
    });
    return checks;
}

const SETUP_CHECK_ELEMENTS = {

    data: 'setupCheckData',

    address: 'setupCheckAddress',

    transport: 'setupCheckTransport',

    setup_token: 'setupCheckSetupToken',

    owner: 'setupCheckOwner'

};

function setSetupText(id, value) {

    const element = document.getElementById(id);

    if (element) element.textContent = value || '—';

}

let setupVerificationRevision = 0;

function setSetupAction(action) {
    const message = document.getElementById('setupPreflightAction');
    if (!message) return;
    message.dataset.i18n = `setup_action_${action || 'loading'}`;
    message.textContent = t(message.dataset.i18n);
    message.classList.remove('hidden');
}

function invalidateSetupVerification() {
    setupVerificationRevision += 1;
    const ownerFields = document.getElementById('setupOwnerFields');
    if (ownerFields) ownerFields.disabled = true;
    ['setupPassword', 'setupPasswordConfirm'].forEach(id => {
        setSetupSecretVisibility(document.getElementById(id), false);
    });
    const tokenCheck = document.getElementById('setupCheckSetupToken');
    if (tokenCheck && tokenCheck.dataset.status !== 'fail'
        && !document.getElementById('setupTokenGroup')?.classList.contains('hidden')) {
        tokenCheck.dataset.status = 'pending';
        tokenCheck.querySelector('[data-setup-check-message]').textContent = t('setup_token_entry_required');
        setSetupAction('enter_setup_token');
    }
}

function renderSetupStatus(data, {tokenVerified = false} = {}) {

    if (!data || typeof data !== 'object') return;

    AppState.setupRequired = Boolean(data.setup_required);

    AppState.authenticated = Boolean(data.authenticated);

    const setupTokenGroup = document.getElementById('setupTokenGroup');

    if (setupTokenGroup) {

        setupTokenGroup.classList.toggle('hidden', !data.setup_token_required);

    }

    setSetupText('setupBaseUrl', data.base_url);

    setSetupText('setupListener', data.listener);

    const tokenReady = !data.setup_token_required || tokenVerified;
    const nextAction = data.next_action === 'create_owner' && !tokenReady
        ? 'enter_setup_token' : data.next_action;
    setSetupAction(nextAction);

    for (const [checkName, elementId] of Object.entries(SETUP_CHECK_ELEMENTS)) {

        const check = data.checks?.[checkName];

        const element = document.getElementById(elementId);

        if (!element || !check) continue;

        element.dataset.status = ['pass', 'fail', 'pending'].includes(check.status)

            ? check.status

            : 'pending';

        const message = element.querySelector('[data-setup-check-message]');

        if (message) message.textContent = t(check.code || 'setup_check_pending');

    }

    const ownerFields = document.getElementById('setupOwnerFields');

    // A persisted installation checkpoint is not proof of the current token.
    if (ownerFields) ownerFields.disabled = data.state !== 'resumed'
        || data.next_action !== 'create_owner' || !tokenReady;
    renderSetupPasswordChecks();

    if (AppState.setupRequired) AppState.authenticated = false;

    if (!AppState.authenticated) {
        resetIdentityConsoleState();
        resetConditionalNavigation();
    }

}

async function runSetupPreflight({announce = true} = {}) {

    const setupTokenInput = document.getElementById('setupToken');

    const preflightButton = document.getElementById('setupPreflightButton');

    const tokenRequired = document.getElementById('setupTokenGroup')?.classList.contains('hidden') === false;
    const tokenConfigurationFailed = document.getElementById('setupCheckSetupToken')?.dataset.status === 'fail';
    invalidateSetupVerification();
    const verificationRevision = setupVerificationRevision;
    if (tokenRequired && !tokenConfigurationFailed && !setupTokenInput?.value.trim()) {
        showStatus(t('setup_action_enter_setup_token'), 'warning');
        return false;
    }

    if (preflightButton) {

        preflightButton.disabled = true;

        preflightButton.setAttribute('aria-busy', 'true');

    }

    try {

        const response = await fetch('./api/auth/setup/preflight', {

            method: 'POST',

            headers: getAuthHeaders(),

            body: JSON.stringify({setup_token: setupTokenInput?.value || undefined})

        });

        const data = await response.json();

        // Ignore a response for a token edited while the check was in flight.
        if (verificationRevision !== setupVerificationRevision) return false;

        const tokenVerified = response.ok && data.checks?.setup_token?.status === 'pass'
            && data.checks?.setup_token?.code === 'setup_token_verified';
        if (data && data.state) renderSetupStatus(data, {tokenVerified});

        if (!response.ok) {

            showStatus(data.detail || data.error || t('setup_preflight_failed'), 'error');

            return false;

        }

        if (data.state === 'configured') {

            AppState.setupRequired = false;

            navigate(data.next_action === 'open_dashboard' ? '/dashboard' : '/login', false);

            return true;

        }

        if (data.state === 'resumed' && data.next_action === 'create_owner' && announce) {

            showStatus(t('setup_action_create_owner'), 'success');

        }

        return data.state === 'resumed';

    } catch (error) {

        showStatus(t('status_net_error', {error: error.message}), 'error');

        return false;

    } finally {

        if (preflightButton) {

            preflightButton.disabled = false;

            preflightButton.removeAttribute('aria-busy');

        }

    }

}

async function refreshSetupStatus() {

    try {

        const response = await fetch('./api/auth/setup/status', {headers: getAuthHeaders(false)});

        const data = await response.json();

        if (!response.ok) throw new Error(data.detail || t('setup_status_failed'));

        renderSetupStatus(data);

        if (data.state === 'fresh' && data.next_action === 'run_preflight') {

            await runSetupPreflight({announce: false});

        }

        return AppState.setupRequired;

    } catch (error) {

        renderSetupStatus({

            state: 'invalid',

            next_action: 'retry_status',

            setup_required: true,

            setup_token_required: false,

            authenticated: false

        });

        showStatus(t('setup_status_failed'), 'error');

        return true;

    }

}

async function completeInitialSetup() {

    const ownerFields = document.getElementById('setupOwnerFields');

    if (ownerFields?.disabled) {

        await runSetupPreflight();

        return;

    }

    const passwordInput = document.getElementById('setupPassword');

    const confirmInput = document.getElementById('setupPasswordConfirm');

    const setupTokenInput = document.getElementById('setupToken');

    const password = passwordInput?.value || '';

    const confirmPassword = confirmInput?.value || '';

    const setupToken = setupTokenInput?.value || '';

    const checks = renderSetupPasswordChecks();

    if (!checks.length) {

        showStatus(t('password_check_length'), 'error');

        return;

    }

    if (!checks.variety || !checks.uncommon) {
        passwordInput.setAttribute('aria-invalid', 'true');
        passwordInput.setAttribute('data-validation-error', '');
        showStatus(t(!checks.variety ? 'password_check_variety' : 'password_check_uncommon'), 'error');
        return;
    }

    if (password !== confirmPassword) {

        confirmInput.setAttribute('aria-invalid', 'true');
        confirmInput.setAttribute('data-validation-error', '');
        showStatus(t('password_match_error'), 'error');

        return;

    }

    try {

        const response = await fetch('./api/auth/setup', {

            method: 'POST',

            headers: getAuthHeaders(),

            body: JSON.stringify({

                password,

                confirm_password: confirmPassword,

                setup_token: setupToken || undefined

            })

        });

        const data = await response.json();

        if (response.ok) {

            resetIdentityConsoleState();

            AppState.setupRequired = false;

            AppState.authenticated = true;

            showStatus(t('setup_completed'), 'success');

            navigate('/dashboard');

            await refreshTeamAccessNavigation();

            await fetchAndDisplayVersion();

        } else {

            showStatus(data.detail || data.error || t('setup_failed'), 'error');

            await refreshSetupStatus();

        }

    } catch (error) {

        showStatus(t('status_net_error', {error: error.message}), 'error');

    } finally {

        if (passwordInput) passwordInput.value = '';

        if (confirmInput) confirmInput.value = '';

        if (setupTokenInput) setupTokenInput.value = '';

        [passwordInput, confirmInput, setupTokenInput].forEach(input => {
            setSetupSecretVisibility(input, false);
            input?.removeAttribute('aria-invalid');
            input?.removeAttribute('data-validation-error');
        });
        renderSetupPasswordChecks();
        invalidateSetupVerification();

    }

}

let loginInProgress = false;

async function login() {
    if (loginInProgress) return;
    const passwordInput = document.getElementById('loginPassword');
    const submitButton = document.getElementById('loginSubmitButton');
    const toggleButton = document.getElementById('loginPasswordToggle');
    const password = passwordInput.value;

    if (!password) {

        showStatus(t('please_enter_the_password'), 'error');

        return;

    }

    loginInProgress = true;
    passwordInput.readOnly = true;
    toggleButton.disabled = true;
    submitButton.disabled = true;
    submitButton.setAttribute('aria-busy', 'true');
    submitButton.dataset.i18n = 'login_pending';
    submitButton.textContent = t('login_pending');

    try {

        const response = await fetch('./api/auth/login', {

            method: 'POST',

            headers: getAuthHeaders(),

            body: JSON.stringify({ password })

        });

        const data = await response.json();

        if (response.ok) {

            resetIdentityConsoleState();

            AppState.authenticated = true;

            showStatus(t('login_successful_dup'), 'success');

            navigate('/dashboard');
            passwordInput.value = '';

            await refreshTeamAccessNavigation();

            await fetchAndDisplayVersion();

        } else {

            if (response.status === 428) {

                AppState.setupRequired = true;

                navigate('/setup', false);

                return;

            }

            if (response.status === 401) {

                passwordInput.setAttribute('aria-invalid', 'true');
                passwordInput.setAttribute('data-validation-error', '');
                showStatus(t('login_failed_incorrect_password'), 'error');

                return;

            }

            showStatus(data.detail || data.error || t('login_failed'), 'error');

        }

    } catch (error) {

        showStatus(t('status_net_error', {error: error.message}), 'error');

    } finally {
        loginInProgress = false;
        passwordInput.readOnly = false;
        setSetupSecretVisibility(passwordInput, false);
        toggleButton.disabled = false;
        submitButton.disabled = false;
        submitButton.removeAttribute('aria-busy');
        submitButton.dataset.i18n = 'login_submit';
        submitButton.textContent = t('login_submit');
    }

}

async function autoLogin() {

    if (AppState.setupRequired) {

        navigate('/setup', false);

        return false;

    }

    if (AppState.authenticated) {

        navigate(window.location.pathname, false);

        await refreshTeamAccessNavigation();

        return true;

    }

    navigate('/login', false);

    return false;

}

async function logout() {

    try {

        await fetch('./api/auth/logout', {method: 'POST', headers: getAuthHeaders(false)});

    } catch (error) {

        console.warn('Failed to notify the server about sign-out.', error);

    }

    AppState.authenticated = false;

    resetIdentityConsoleState();

    resetConditionalNavigation();

    showStatus(t('logged_out'), 'info');

    const passwordInput = document.getElementById('loginPassword');

    if (passwordInput) passwordInput.value = '';

    navigate('/login', false);

}

// =====================================================================

// =====================================================================
