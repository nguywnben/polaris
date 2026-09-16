// Action results stay in the credential workspace; no secondary information dialogs.
function bindCredentialManagementActions(state) {
    const {modal, context, manager, read, close, syncOverview, result, signal} = state;
    const {filename} = context;
    const button = action => modal.querySelector(`[data-management-action="${action}"]`);
    const confirm = modal.querySelector('[data-management-delete-confirm]');
    const payload = modal.querySelector('[data-management-payload]');
    const hidePayload = () => {
        payload.replaceChildren();
        button('hide').hidden = true;
        button('reveal').hidden = false;
    };
    modal.querySelector('[data-management-sensitive]').addEventListener('toggle', event => {
        if (!event.target.open) hidePayload();
    });
    modal.addEventListener('click', async event => {
        const trigger = event.target.closest('[data-management-action]');
        if (!trigger || state.isBusy()) return;
        const action = trigger.dataset.managementAction;
        if (action === 'delete' || action === 'cancel-delete') {
            confirm.hidden = action !== 'delete';
            if (action === 'delete') button('cancel-delete').focus();
            else button('delete').focus();
            return;
        }
        if (action === 'hide') { hidePayload(); button('reveal').focus(); return; }
        if (action === 'reauthenticate') { await close(); reauthenticateCredentialByContext(context); return; }
        if (action === 'download') {
            if (manager.type === 'primary') downloadPrimaryCred(filename);
            else downloadCred(filename);
            return;
        }
        state.setBusy(true);
        const controls = Array.from(modal.querySelectorAll('button:not([data-dialog-close]), input, select, textarea')).filter(node => !node.disabled);
        controls.forEach(node => { node.disabled = true; });
        result.classList.remove('hidden');
        result.classList.remove('credential-management-error');
        result.textContent = t(action === 'test' ? 'testing_model_please_wait' : 'loading');
        result.setAttribute('aria-busy', 'true');
        try {
            if (action === 'reveal') {
                const data = await read(`./api/credentials/detail/${encodeURIComponent(filename)}?${manager.getModeParam()}`);
                if (state.isClosed()) return;
                if (!modal.querySelector('[data-management-sensitive]').open) { result.classList.add('hidden'); return; }
                payload.innerHTML = buildCredentialContentHtml(filename, data.content || {});
                button('hide').hidden = false;
                button('reveal').hidden = true;
                result.classList.add('hidden');
            } else if (action === 'toggle' || action === 'confirm-delete') {
                const operation = action === 'confirm-delete' ? 'delete'
                    : manager.data[filename]?.status.disabled ? 'enable' : 'disable';
                if (!(await manager.action(filename, operation))) throw new Error(t('unknown_error'));
                if (state.isClosed()) return;
                if (operation === 'delete') { state.setBusy(false); await close(); return; }
                syncOverview();
                result.textContent = t('status_action_success', {action: t(operation === 'enable' ? 'action_enable' : 'action_disable')});
            } else if (action === 'verify' || action === 'preview') {
                const route = action === 'verify' ? 'verify' : 'configure-preview';
                const data = await read(`./api/credentials/${route}/${encodeURIComponent(filename)}?${manager.getModeParam()}`, {method: 'POST'});
                if (state.isClosed()) return;
                result.innerHTML = action === 'verify' ? buildCredentialVerificationHtml(filename, data) : '';
                if (action === 'preview') result.textContent = data.message || t('status_action_success', {action: t('btn_setup_preview')});
                await manager.refresh({preserveContent: true});
                if (!state.isClosed()) { syncOverview(); await state.reloadDiagnostics(); }
            } else if (action === 'test') {
                const model = modal.querySelector('[data-management-model-select]')?.value;
                if (!model) return;
                const test = manager.type === 'primary' ? testPrimaryCredential : testCredential;
                const outcome = await test(filename, model, signal);
                if (!state.isClosed()) {
                    result.innerHTML = outcome.html;
                    syncOverview();
                    await state.reloadDiagnostics();
                }
            }
        } catch (error) {
            if (!state.isClosed()) {
                result.textContent = error.message || t('unknown_error');
                result.classList.add('credential-management-error');
            }
        } finally {
            state.setBusy(false);
            result.removeAttribute('aria-busy');
            controls.forEach(node => { node.disabled = false; });
            if (!state.isClosed() && action === 'reveal' && button('reveal').hidden) button('hide').focus();
        }
    });
}

function reauthenticateCredentialByContext(context) {
    if (!context.providerVariant || context.credentialSource === 'environment') return;
    selectProviderWorkspace(context.providerVariant);
    navigate('/providers', true);
    document.getElementById(PROVIDER_WORKSPACES[context.providerVariant]?.panelId)?.scrollIntoView({block: 'start'});
}
