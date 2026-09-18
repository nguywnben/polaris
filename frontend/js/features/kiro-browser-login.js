// PKCE and tokens stay on the server; only an explicit Save completes sign-in.
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
    const pending = extendedElement('section', 'provider-browser-pending hidden');
    pending.tabIndex = -1;
    const linkHeader = extendedElement('div', 'auth-link-header');
    const linkLabel = extendedElement('span', 'auth-link-label', 'provider.portal.link_label');
    linkLabel.id = 'kiroBrowserLinkLabel'; pending.setAttribute('aria-labelledby', linkLabel.id);
    const copy = extendedElement('button', 'btn btn-secondary', 'provider.portal.copy');
    copy.id = 'kiroBrowserCopyLink'; copy.type = 'button';
    linkHeader.append(linkLabel, copy);
    const linkCard = extendedElement('div', 'endpoint-code-card auth-link-card');
    const link = extendedElement('a');
    link.target = '_blank'; link.rel = 'noopener noreferrer';
    linkCard.append(link);
    copy.addEventListener('click', () => { if (flow && link.hasAttribute('href')) copyTextWithStatus(link.href); });
    const actions = extendedElement('div', 'page-actions');
    const manualForm = extendedElement('form', 'extended-provider-form oauth-completion-panel'); manualForm.noValidate = true;
    const callbackGroup = extendedElement('div', 'form-group');
    const callbackLabel = extendedElement('label', '', 'provider.portal.manual');
    const callbackHelp = extendedElement('p', 'card-copy provider-tool-copy', 'provider.portal.manual_help');
    callbackHelp.id = 'kiroBrowserCallbackHelp';
    const input = extendedElement('textarea');
    input.id = 'extended-kiro-browser-callback_url'; input.name = 'callback_url';
    input.rows = 3; callbackLabel.htmlFor = input.id;
    input.placeholder = 'http://localhost:4283/oauth/callback?code=…&state=…';
    input.maxLength = 6144; input.autocomplete = 'off'; input.autocapitalize = 'none'; input.spellcheck = false;
    input.setAttribute('aria-describedby', callbackHelp.id);
    callbackGroup.append(callbackLabel, callbackHelp, input); manualForm.append(callbackGroup);
    const submit = extendedElement('button', 'btn', 'runtime.save_credential'); submit.type = 'submit';
    actions.append(submit); manualForm.append(actions);
    pending.append(linkHeader, linkCard, manualForm); panel.append(pending);
    const saveResult = createProviderCredentialSaveResult(panel, 'kiroBrowser');
    const remote = !['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
    const callbackOrigin = remote ? 'http://localhost:4283' : location.origin;
    if (remote) panel.append(extendedElement('p', 'card-copy', 'provider.portal.remote'));
    let flow = null, busy = false, expiresAt = 0;
    const setBusy = value => {
        busy = value;
        [start, submit].forEach(button => { button.disabled = value; });
    };
    const reset = () => {
        flow = null; input.value = ''; link.removeAttribute('href'); link.textContent = '';
        pending.classList.add('hidden'); region.disabled = false;
    };
    async function request(action, payload) {
        const response = await fetch(`./api/providers/kiro/browser/${action}`, {
            method: 'POST', headers: getAuthHeaders(), body: JSON.stringify(payload)
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) { const error = new Error('kiro-login'); error.terminal = [401, 403, 404, 409].includes(response.status); throw error; }
        return data;
    }
    manualForm.addEventListener('submit', async event => {
        event.preventDefault(); if (!flow || busy || !manualForm.reportValidity()) return;
        if (Date.now() >= expiresAt) { reset(); showStatus(t('provider.auth.error'), 'error'); return; }
        setBusy(true);
        try {
            if (input.value.trim()) {
                await request('callback', {flow_id: flow, callback_url: input.value.trim()});
                input.value = '';
            }
            const result = await request('complete', {flow_id: flow});
            if (result.credential_saved) {
                reset(); showProviderCredentialSaveResult('kiroBrowser', result);
                showStatus(providerCredentialResultCopy(result).title, 'success');
                await AppState.primaryCreds.refresh();
            } else if (result.status === 'error') {
                reset(); showStatus(t(result.reason === 'unsupported_method' ? 'provider.portal.unsupported' : 'provider.auth.error'), 'error');
            } else {
                showStatus(t('provider.authorization_pending', {provider: 'Kiro'}), 'info');
            }
        } catch (error) {
            if (error.terminal) reset();
            showStatus(t('provider.auth.error'), 'error');
        } finally { setBusy(false); }
    });
    form.addEventListener('submit', async event => {
        event.preventDefault(); if (busy) return;
        saveResult.classList.add('hidden');
        setBusy(true); copy.disabled = true; region.disabled = true;
        try {
            if (flow) {
                await request('cancel', {flow_id: flow});
                reset(); region.disabled = true;
            }
            const result = await request('start', {callback_origin: callbackOrigin, region: region.value});
            const url = new URL(result.authorization_url);
            if (url.origin !== 'https://app.kiro.dev' || url.pathname !== '/signin' || url.username || url.password) throw new Error('invalid-url');
            flow = result.flow_id; expiresAt = Date.now() + result.expires_in * 1000;
            link.href = url.href; link.textContent = url.href;
            pending.classList.remove('hidden'); pending.focus({preventScroll: true});
        } catch (error) {
            if (!flow || error.terminal) reset();
            showStatus(t('provider.auth.error'), 'error');
        }
        finally { setBusy(false); copy.disabled = false; region.disabled = Boolean(flow); }
    });
    return panel;
}
