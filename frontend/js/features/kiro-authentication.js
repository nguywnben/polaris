// No access/refresh tokens enter the browser. Only a session-bound flow reference.
function buildKiroOAuthPanel() {
    const panel = extendedElement('section', 'tool-panel');
    const title = extendedElement('h3', 'card-title'); title.textContent = 'Kiro OAuth';
    panel.append(title, extendedElement('p', 'card-copy provider-tool-copy', 'provider.auth.login_help'));
    const form = extendedElement('form', 'extended-provider-form'); form.noValidate = true;
    form.id = 'kiroOAuthForm';
    const fields = extendedElement('div', 'extended-provider-fields');
    const method = extendedField(fields, 'kiro-oauth', 'method', 'provider.auth.method', '', {
        value: 'google', options: ['google', 'github', 'builder-id', 'identity-center']
    });
    [...method.options].forEach(option => {
        option.textContent = {google: 'Google', github: 'GitHub', 'builder-id': 'AWS Builder ID', 'identity-center': 'IAM Identity Center'}[option.value];
    });
    extendedField(fields, 'kiro-oauth', 'region', 'provider.ext.region', '', {value: 'us-east-1', options: ['us-east-1', 'eu-central-1']});
    const tokenRegion = extendedField(fields, 'kiro-oauth', 'token_region', 'provider.auth.token_region', 'us-east-1', {value: 'us-east-1'});
    tokenRegion.maxLength = 32;
    const startUrl = extendedField(fields, 'kiro-oauth', 'start_url', 'provider.auth.start_url', 'https://example.awsapps.com/start', {type: 'url'});
    const syncFields = () => {
        tokenRegion.disabled = !['builder-id', 'identity-center'].includes(method.value);
        tokenRegion.parentElement.classList.toggle('hidden', tokenRegion.disabled);
        startUrl.disabled = method.value !== 'identity-center'; startUrl.required = !startUrl.disabled;
        startUrl.parentElement.classList.toggle('hidden', startUrl.disabled);
    };
    method.addEventListener('change', syncFields); syncFields();
    const actions = extendedElement('div', 'page-actions');
    const start = extendedElement('button', 'btn btn-small', 'runtime.get_authorization_code'); start.type = 'submit';
    actions.append(start); form.append(fields, actions); panel.append(form);
    const pending = extendedElement('div', 'provider-upload-section hidden');
    const code = extendedElement('p', 'provider-device-code'); code.setAttribute('role', 'status');
    const link = extendedElement('a', 'provider-site-link');
    link.target = '_blank'; link.rel = 'noopener noreferrer';
    const check = extendedElement('button', 'btn btn-small', 'runtime.check_authorization'); check.type = 'button';
    const cancel = extendedElement('button', 'btn btn-secondary btn-small', 'cancel'); cancel.type = 'button';
    const pendingActions = extendedElement('div', 'page-actions'); pendingActions.append(link, check, cancel);
    pending.append(code, pendingActions); panel.append(pending);
    let flow = null;
    let busy = false;
    let waitUntil = 0;
    let expiresAt = 0;
    async function request(action, payload) {
        const response = await fetch(`./api/providers/kiro/oauth/${action}`, {
            method: 'POST', headers: getAuthHeaders(), body: JSON.stringify(payload)
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error('kiro-authorization-failed');
        return data;
    }
    function finish() {
        flow = null; pending.classList.add('hidden'); code.textContent = ''; link.removeAttribute('href');
    }
    async function run(operation, button = check, busyKey = 'runtime.validating') {
        if (busy) return;
        busy = true; panel.setAttribute('aria-busy', 'true');
        const controls = [...panel.querySelectorAll('input, select, button')].filter(input => !input.disabled);
        controls.forEach(input => { input.disabled = true; });
        const label = button.textContent; button.textContent = t(busyKey);
        try { await operation(); }
        catch { showStatus(t('provider.auth.error'), 'error'); }
        finally {
            busy = false; controls.forEach(input => { input.disabled = false; });
            syncFields(); panel.removeAttribute('aria-busy');
            button.textContent = label;
        }
    }
    form.addEventListener('submit', event => {
        event.preventDefault();
        if (!form.reportValidity()) return;
        const payload = Object.fromEntries(new FormData(form));
        run(async () => {
            if (flow) { await request('cancel', {flow_id: flow}); finish(); }
            const result = await request('start', payload);
            const url = new URL(result.verification_uri);
            if (url.protocol !== 'https:' || url.username || url.password) throw new Error('invalid-url');
            flow = result.flow_id; link.href = url.href; link.textContent = url.origin; code.textContent = result.user_code;
            waitUntil = Date.now() + result.interval * 1000; expiresAt = Date.now() + result.expires_in * 1000;
            pending.classList.remove('hidden');
            showStatus(t('provider.device_code_ready', {provider: 'Kiro'}), 'success');
        }, start, 'runtime.generating');
    });
    check.addEventListener('click', () => run(async () => {
        if (!flow || Date.now() >= expiresAt) { finish(); throw new Error('expired'); }
        if (Date.now() < waitUntil) {
            showStatus(t('provider.authorization_pending', {provider: 'Kiro'}), 'info'); return;
        }
        const result = await request('complete', {flow_id: flow});
        if (result.status === 'pending') {
            waitUntil = Date.now() + result.interval * 1000;
            showStatus(t('provider.authorization_pending', {provider: 'Kiro'}), 'info');
        } else if (result.credential_saved === true) {
            finish(); showStatus(t('provider.ext.saved'), 'success');
            await AppState.primaryCreds.refresh();
        }
    }));
    cancel.addEventListener('click', () => run(async () => {
        try { if (flow) await request('cancel', {flow_id: flow}); }
        finally { finish(); }
    }, cancel));
    return panel;
}
