// Polaris management console: console.

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

function renderSetupStatus(data) {

    if (!data || typeof data !== 'object') return;

    AppState.setupRequired = Boolean(data.setup_required);

    AppState.authenticated = Boolean(data.authenticated);

    const setupTokenGroup = document.getElementById('setupTokenGroup');

    if (setupTokenGroup) {

        setupTokenGroup.classList.toggle('hidden', !data.setup_token_required);

    }

    setSetupText('setupBaseUrl', data.base_url);

    setSetupText('setupListener', data.listener);

    setSetupText('setupPreflightAction', t(`setup_action_${data.next_action || 'loading'}`));

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

    if (ownerFields) ownerFields.disabled = data.state !== 'resumed' || data.next_action !== 'create_owner';

    if (AppState.setupRequired) AppState.authenticated = false;

    if (!AppState.authenticated) {
        resetIdentityConsoleState();
        resetConditionalNavigation();
    }

}

async function runSetupPreflight({focusOwner = true} = {}) {

    const setupTokenInput = document.getElementById('setupToken');

    const preflightButton = document.getElementById('setupPreflightButton');

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

        if (data && data.state) renderSetupStatus(data);

        if (!response.ok) {

            if (!data?.state && setupTokenInput) setupTokenInput.value = '';

            showStatus(data.detail || data.error || t('setup_preflight_failed'), 'error');

            return false;

        }

        if (data.state === 'configured') {

            AppState.setupRequired = false;

            navigate(data.next_action === 'open_dashboard' ? '/dashboard' : '/login', false);

            return true;

        }

        if (data.state === 'resumed' && focusOwner) {

            document.getElementById('setupPassword')?.focus();

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

            await runSetupPreflight({focusOwner: false});

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

    if (password.length < 12) {

        showStatus(t('password_min_error'), 'error');

        return;

    }

    if (password !== confirmPassword) {

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

    }

}

async function login() {

    const password = document.getElementById('loginPassword').value;

    if (!password) {

        showStatus(t('please_enter_the_password'), 'error');

        return;

    }

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

            await refreshTeamAccessNavigation();

            await fetchAndDisplayVersion();

        } else {

            if (response.status === 428) {

                AppState.setupRequired = true;

                navigate('/setup', false);

                return;

            }

            if (response.status === 401) {

                showStatus(t('login_failed_incorrect_password'), 'error');

                return;

            }

            showStatus(data.detail || data.error || t('login_failed'), 'error');

        }

    } catch (error) {

        showStatus(t('status_net_error', {error: error.message}), 'error');

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
