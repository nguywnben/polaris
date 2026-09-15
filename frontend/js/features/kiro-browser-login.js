// Portal-style login: PKCE and tokens stay on the server; callback capture is automatic.
function buildKiroOAuthPanel(advanced) {
    const panel = extendedElement('section', 'tool-panel');
    const title = extendedElement('h3', 'card-title'); title.textContent = 'Kiro OAuth';
    panel.append(title, extendedElement('p', 'card-copy provider-tool-copy', 'provider.portal.help'));
    const form = extendedElement('form', 'extended-provider-form');
    form.id = 'kiroBrowserForm'; form.noValidate = true;
    const start = extendedElement('button', 'btn', 'provider.ui.get_link'); start.type = 'submit';
    form.append(start); panel.append(form);
    const settings = extendedElement('fieldset', 'provider-auth-settings');
    const legend = extendedElement('legend'); legend.textContent = 'Kiro OAuth';
    const fields = extendedElement('div', 'extended-provider-fields');
    const region = extendedField(fields, 'kiro-browser', 'region', 'provider.ext.region', '', {
        value: 'us-east-1', options: ['us-east-1', 'eu-central-1']
    });
    region.setAttribute('form', form.id);
    settings.append(legend, fields); advanced.append(settings);
    const pending = extendedElement('section', 'provider-device-flow provider-browser-pending hidden');
    pending.tabIndex = -1;
    const status = extendedElement('p', 'card-copy', 'provider.portal.pending'); status.setAttribute('role', 'status');
    status.id = 'kiroBrowserStatus'; pending.setAttribute('aria-labelledby', status.id);
    const expiry = extendedElement('p', 'card-copy');
    const linkHeader = extendedElement('div', 'auth-link-header');
    const linkLabel = extendedElement('span', '', 'provider.portal.link_label');
    const copy = extendedElement('button', 'btn btn-secondary', 'provider.portal.copy');
    copy.id = 'kiroBrowserCopyLink'; copy.type = 'button';
    linkHeader.append(linkLabel, copy);
    const linkCard = extendedElement('div', 'endpoint-code-card auth-link-card');
    const link = extendedElement('a');
    link.target = '_blank'; link.rel = 'noopener noreferrer';
    linkCard.append(link);
    copy.addEventListener('click', () => { if (flow && link.hasAttribute('href')) copyTextWithStatus(link.href); });
    const cancel = extendedElement('button', 'btn btn-secondary', 'btn_cancel'); cancel.type = 'button';
    const actions = extendedElement('div', 'page-actions');
    const manualForm = extendedElement('form', 'extended-provider-form oauth-completion-panel'); manualForm.noValidate = true;
    const input = extendedField(manualForm, 'kiro-browser', 'callback_url', 'provider.portal.manual', '', {type: 'url', required: true});
    input.placeholder = 'http://localhost:4283/oauth/callback?code=…&state=…';
    input.maxLength = 6144; input.autocomplete = 'off'; input.spellcheck = false;
    const submit = extendedElement('button', 'btn btn-secondary', 'provider.portal.submit'); submit.type = 'submit';
    actions.append(submit, cancel); manualForm.append(actions);
    pending.append(status, linkHeader, linkCard, expiry, manualForm); panel.append(pending);
    const saveResult = createProviderCredentialSaveResult(panel, 'kiroBrowser');
    const remote = !['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
    const callbackOrigin = remote ? 'http://localhost:4283' : location.origin;
    if (remote) panel.append(extendedElement('p', 'card-copy', 'provider.portal.remote'));
    let flow = null, timer = null, busy = false, expiresAt = 0;
    const stopTimer = () => { clearTimeout(timer); timer = null; };
    const reset = () => {
        stopTimer(); flow = null; input.value = ''; link.removeAttribute('href'); link.textContent = '';
        pending.classList.add('hidden'); form.classList.remove('hidden'); region.disabled = false;
    };
    async function request(action, payload) {
        const response = await fetch(`./api/providers/kiro/browser/${action}`, {
            method: 'POST', headers: getAuthHeaders(), body: JSON.stringify(payload)
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) { const error = new Error('kiro-login'); error.terminal = [401, 403, 404, 409].includes(response.status); throw error; }
        return data;
    }
    function schedule() { stopTimer(); if (flow) timer = setTimeout(poll, 2000); }
    async function poll() {
        if (!flow) return;
        if (Date.now() >= expiresAt) { reset(); showStatus(t('provider.auth.error'), 'error'); return; }
        if (busy || document.hidden) { schedule(); return; }
        busy = true; cancel.disabled = true; submit.disabled = true;
        try {
            const result = await request('complete', {flow_id: flow});
            if (result.credential_saved) {
                reset(); showProviderCredentialSaveResult('kiroBrowser', result);
                showStatus(providerCredentialResultCopy(result).title, 'success');
                await AppState.primaryCreds.refresh();
            } else if (result.status === 'error') {
                reset(); showStatus(t(result.reason === 'unsupported_method' ? 'provider.portal.unsupported' : 'provider.auth.error'), 'error');
            }
        } catch (error) {
            if (error.terminal) { reset(); showStatus(t('provider.auth.error'), 'error'); }
        } finally { busy = false; cancel.disabled = false; submit.disabled = false; schedule(); }
    }
    form.addEventListener('submit', async event => {
        event.preventDefault(); if (busy || flow) return;
        saveResult.classList.add('hidden');
        busy = true; start.disabled = true; region.disabled = true;
        try {
            const result = await request('start', {callback_origin: callbackOrigin, region: region.value});
            const url = new URL(result.authorization_url);
            if (url.origin !== 'https://app.kiro.dev' || url.pathname !== '/signin' || url.username || url.password) throw new Error('invalid-url');
            flow = result.flow_id; expiresAt = Date.now() + result.expires_in * 1000;
            link.href = url.href; link.textContent = url.href;
            expiry.textContent = t('provider.ui.expires_at', {time: new Date(expiresAt).toLocaleTimeString(document.documentElement.lang || 'en', {hour: '2-digit', minute: '2-digit'})});
            form.classList.add('hidden'); pending.classList.remove('hidden'); pending.focus({preventScroll: true});
            schedule();
        } catch { reset(); showStatus(t('provider.auth.error'), 'error'); }
        finally { busy = false; start.disabled = false; region.disabled = Boolean(flow); }
    });
    manualForm.addEventListener('submit', async event => {
        event.preventDefault(); if (!flow || busy || !manualForm.reportValidity()) return;
        busy = true; submit.disabled = true; cancel.disabled = true;
        try { await request('callback', {flow_id: flow, callback_url: input.value.trim()}); input.value = ''; }
        catch { showStatus(t('provider.auth.error'), 'error'); }
        finally { busy = false; submit.disabled = false; cancel.disabled = false; schedule(); }
    });
    cancel.addEventListener('click', async () => {
        if (busy || !flow) return;
        busy = true; cancel.disabled = true;
        try { await request('cancel', {flow_id: flow}); reset(); start.focus({preventScroll: true}); }
        catch { showStatus(t('provider.auth.error'), 'error'); }
        finally { busy = false; cancel.disabled = false; schedule(); }
    });
    window.addEventListener('pagehide', stopTimer);
    window.addEventListener('pageshow', schedule);
    return panel;
}
