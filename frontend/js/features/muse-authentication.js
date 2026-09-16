// The server owns OAuth state. A user click is required for every check/save.
function buildMuseOAuthPanel(advanced) {
    const settings = extendedElement('div', 'provider-auth-settings');
    const help = extendedElement('p', 'card-copy provider-tool-copy', 'provider.muse.settings_help');
    help.id = 'museSettingsHelp';
    const credentialLabel = extendedField(settings, 'muse', 'credential_label', 'credential_display_name', t('form.credential_name'));
    credentialLabel.dataset.i18nPlaceholder = 'form.credential_name';
    credentialLabel.maxLength = 128;
    credentialLabel.setAttribute('aria-describedby', help.id);
    settings.prepend(help); advanced.append(settings);
    const panel = extendedElement('section', 'tool-panel');
    const title = extendedElement('h3', 'card-title'); title.textContent = 'Muse Code OAuth';
    panel.append(title, extendedElement('p', 'card-copy provider-tool-copy', 'provider.muse.help'));
    const start = extendedElement('button', 'btn', 'provider.ui.get_link');
    start.id = 'museStartLogin'; start.type = 'button'; panel.append(start);
    const pending = extendedElement('section', 'provider-browser-pending hidden');
    pending.id = 'musePending'; pending.tabIndex = -1;
    const header = extendedElement('div', 'auth-link-header');
    const label = extendedElement('span', 'auth-link-label', 'provider.portal.link_label');
    label.id = 'museLoginLinkLabel';
    pending.setAttribute('aria-labelledby', label.id);
    const copy = extendedElement('button', 'btn btn-secondary', 'provider.portal.copy');
    copy.type = 'button'; header.append(label, copy);
    const linkCard = extendedElement('div', 'endpoint-code-card auth-link-card');
    const link = extendedElement('a');
    link.id = 'museLoginLink'; link.target = '_blank'; link.rel = 'noopener noreferrer';
    linkCard.append(link);
    const codeRow = extendedElement('div', 'provider-device-code-inline');
    const codeLabel = extendedElement('span', '', 'provider.ui.device_code');
    const code = extendedElement('strong', 'provider-device-code'); code.id = 'museDeviceCode';
    codeRow.append(codeLabel, code);
    const actions = extendedElement('div', 'page-actions');
    const save = extendedElement('button', 'btn', 'runtime.save_credential');
    save.type = 'button'; save.id = 'museCompleteLogin';
    actions.append(save);
    pending.append(header, linkCard, codeRow, actions); panel.append(pending);
    const resultPanel = createProviderCredentialSaveResult(panel, 'museOAuth');
    let flow = null, busy = false, expiresAt = 0, waitUntil = 0;
    const reset = () => {
        flow = null; link.textContent = ''; code.textContent = ''; link.removeAttribute('href');
        pending.classList.add('hidden');
    };
    async function request(action, payload) {
        const response = await fetch(`./api/providers/muse-code/oauth/${action}`, {
            method: 'POST', headers: getAuthHeaders(), body: JSON.stringify(payload)
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const error = new Error('muse-login');
            error.terminal = [401, 403, 404, 409].includes(response.status);
            throw error;
        }
        return data;
    }
    async function run(operation) {
        if (busy) return;
        busy = true; panel.setAttribute('aria-busy', 'true');
        [start, save, copy, credentialLabel].forEach(button => { button.disabled = true; });
        const restoreFocus = pending.contains(document.activeElement);
        try { await operation(); }
        catch (error) {
            if (error.terminal) reset();
            showStatus(t('provider.muse.error'), 'error');
        } finally {
            busy = false; panel.removeAttribute('aria-busy');
            [start, save, copy, credentialLabel].forEach(button => { button.disabled = false; });
            if (restoreFocus && !flow) start.focus({preventScroll: true});
        }
    }
    copy.addEventListener('click', () => { if (flow && link.hasAttribute('href')) copyTextWithStatus(link.href); });
    start.addEventListener('click', () => run(async () => {
        resultPanel.classList.add('hidden');
        if (flow) {
            try { await request('cancel', {flow_id: flow}); }
            catch (error) { if (!error.terminal) throw error; }
            reset();
        }
        const result = await request('start', {credential_label: credentialLabel.value.trim()});
        const url = new URL(result.verification_uri);
        if (url.origin !== 'https://auth.meta.com' || url.pathname !== '/oauth/device/'
            || url.username || url.password || url.hash
            || !/^[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(result.user_code)
            || url.searchParams.get('code') !== result.user_code
            || [...url.searchParams].length !== 1
            || !/^muse_code_[A-Za-z0-9_-]{43}$/.test(result.flow_id)
            || !Number.isInteger(result.expires_in) || result.expires_in < 1 || result.expires_in > 900
            || !Number.isInteger(result.interval) || result.interval < 1 || result.interval > 600) throw new Error('invalid-flow');
        flow = result.flow_id; expiresAt = Date.now() + result.expires_in * 1000;
        waitUntil = Date.now() + result.interval * 1000;
        link.textContent = url.href; link.href = url.href; code.textContent = result.user_code;
        pending.classList.remove('hidden'); pending.focus({preventScroll: true});
    }));
    save.addEventListener('click', () => run(async () => {
        if (!flow || Date.now() >= expiresAt) { reset(); throw new Error('expired'); }
        if (Date.now() < waitUntil) {
            showStatus(t('provider.authorization_pending', {provider: 'Muse Code'}), 'info'); return;
        }
        const result = await request('complete', {flow_id: flow});
        if (result.credential_saved === true) {
            reset(); showProviderCredentialSaveResult('museOAuth', result);
            showStatus(providerCredentialResultCopy(result).title, 'success');
            await AppState.primaryCreds.refresh();
        } else if (result.status === 'pending' && Number.isInteger(result.interval) && result.interval >= 1 && result.interval <= 600) {
            waitUntil = Date.now() + result.interval * 1000;
            showStatus(t('provider.authorization_pending', {provider: 'Muse Code'}), 'info');
        } else throw new Error('invalid-result');
    }));
    return panel;
}
