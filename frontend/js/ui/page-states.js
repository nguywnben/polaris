// Shared loading outcomes for console regions that fetch data asynchronously.

function resolvePageStateHost(target) {
    return typeof target === 'string' ? document.getElementById(target) : target;
}

function clearPageState(target) {
    const host = resolvePageStateHost(target);
    if (!host) return;
    host.replaceChildren();
    host.hidden = true;
}

function showPageState(target, options = {}) {
    const host = resolvePageStateHost(target);
    if (!host) return null;

    const kind = ['empty', 'error', 'stale', 'success', 'info'].includes(options.kind)
        ? options.kind
        : 'info';
    const state = document.createElement('div');
    state.className = `page-state page-state-${kind}`;
    state.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    state.setAttribute('aria-live', kind === 'error' ? 'assertive' : 'polite');
    state.setAttribute('aria-atomic', 'true');

    if (options.title) {
        const title = document.createElement('strong');
        title.className = 'page-state-title';
        title.textContent = String(options.title);
        state.append(title);
    }

    if (options.message) {
        const message = document.createElement('p');
        message.className = 'page-state-message';
        message.textContent = String(options.message);
        state.append(message);
    }

    if (options.actionLabel && typeof options.onAction === 'function') {
        const action = document.createElement('button');
        action.type = 'button';
        action.className = 'btn btn-secondary btn-small page-state-action';
        action.textContent = String(options.actionLabel);
        action.addEventListener('click', async () => {
            action.disabled = true;
            try {
                await options.onAction();
            } finally {
                if (action.isConnected) action.disabled = false;
            }
        });
        state.append(action);
    }

    host.replaceChildren(state);
    host.hidden = false;
    return state;
}

function setRegionBusy(target, busy) {
    const region = typeof target === 'string' ? document.getElementById(target) : target;
    if (!region) return;
    region.setAttribute('aria-busy', busy ? 'true' : 'false');
}
