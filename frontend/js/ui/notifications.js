// Polaris management console: ui.

function ensureTerminalPunctuation(message) {

    const value = String(message ?? '');
    const trimmedEnd = value.trimEnd();

    if (!trimmedEnd) return value;

    const visibleText = trimmedEnd
        .replace(/<br\s*\/?>/gi, ' ')
        .replace(/<[^>]+>/g, '')
        .trim();

    if (!visibleText || /[.!?;:…]$/.test(visibleText)) return value;

    return value.slice(0, trimmedEnd.length) + '.' + value.slice(trimmedEnd.length);

}

const modalReturnFocus = new WeakMap();
const modalFocusHandlers = new WeakMap();
const mountedModals = [];
const modalBackgroundStates = new Map();

function syncModalBackground() {
    for (const [element, inert] of modalBackgroundStates) element.inert = inert;
    modalBackgroundStates.clear();
    const active = mountedModals.at(-1);
    document.body.classList.toggle('has-custom-modal', Boolean(active));
    if (!active) return;
    for (const element of document.body.children) {
        if (element === active || element.id === 'statusSection' || element.matches('script, style, link')) continue;
        modalBackgroundStates.set(element, element.inert);
        element.inert = true;
    }
}

function getModalFocusableElements(modal) {
    return Array.from(modal.querySelectorAll(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], summary, [tabindex]:not([tabindex="-1"])'
    )).filter(element => !element.hidden && !element.closest('[inert]') && element.getAttribute('aria-hidden') !== 'true' && element.getClientRects().length > 0);
}

function trapModalFocus(modal, event) {
    if (event.key !== 'Tab' || event.defaultPrevented) return;
    const focusable = getModalFocusableElements(modal);
    if (!focusable.length) {
        event.preventDefault();
        return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const atSurface = !focusable.includes(document.activeElement);
    if (event.shiftKey && (document.activeElement === first || atSurface)) {
        event.preventDefault();
        last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || atSurface)) {
        event.preventDefault();
        first.focus();
    }
}

function focusModalSurface(modal) {
    const surface = modal.querySelector('[role="dialog"], [role="alertdialog"]') || modal;
    surface.setAttribute('tabindex', '-1');
    surface.focus({preventScroll: true});
}

document.addEventListener('keydown', event => {
    const dialog = event.target.closest?.('dialog:modal');
    if (dialog) trapModalFocus(dialog, event);
});

function mountModal(modal) {

    modalReturnFocus.set(modal, document.activeElement);
    document.body.appendChild(modal);
    mountedModals.push(modal);
    syncModalBackground();
    const statusSection = document.getElementById('statusSection');
    if (statusSection?.childElementCount) elevateStatusSection(statusSection);
    const focusHandler = event => trapModalFocus(modal, event);
    modal.addEventListener('keydown', focusHandler);
    modalFocusHandlers.set(modal, focusHandler);
    queueMicrotask(() => {
        if (!modal.isConnected || mountedModals.at(-1) !== modal || modal.contains(document.activeElement)) return;
        focusModalSurface(modal);
    });
    return Promise.resolve();

}

function unmountModal(modal) {

    const focusHandler = modalFocusHandlers.get(modal);
    if (focusHandler) modal.removeEventListener('keydown', focusHandler);
    const returnTarget = modalReturnFocus.get(modal);
    const statusSection = modal.querySelector('#statusSection');
    if (statusSection) document.body.append(statusSection);
    modal.remove();
    const index = mountedModals.indexOf(modal);
    if (index !== -1) mountedModals.splice(index, 1);
    syncModalBackground();
    if (statusSection?.childElementCount) elevateStatusSection(statusSection);
    modalFocusHandlers.delete(modal);
    modalReturnFocus.delete(modal);
    if (returnTarget?.isConnected && !returnTarget.closest('[inert]') && typeof returnTarget.focus === 'function') {
        returnTarget.focus({preventScroll: true});
    } else if (mountedModals.length) {
        focusModalSurface(mountedModals.at(-1));
    }
    return Promise.resolve();

}

function elevateStatusSection(statusSection) {
    // Native modal dialogs sit above every z-index. Keep their live region inside
    // the active dialog (outside content is inert), then promote it without focus.
    const dialogs = [...document.querySelectorAll('dialog:modal')];
    const activeDialog = dialogs.find(dialog => dialog.contains(document.activeElement)) || dialogs.at(-1);
    const parent = activeDialog
        || mountedModals.at(-1)?.querySelector('[role="dialog"], [role="alertdialog"]')
        || document.body;
    if (typeof statusSection.hidePopover === 'function' && statusSection.matches(':popover-open')) {
        statusSection.hidePopover();
    }
    if (statusSection.parentElement !== parent) parent.appendChild(statusSection);
    if (typeof statusSection.showPopover === 'function') {
        statusSection.setAttribute('popover', 'manual');
        statusSection.showPopover();
    }
}

// A modal opened after a toast must not cover that existing notification.
document.addEventListener('toggle', event => {
    if (!(event.target instanceof HTMLDialogElement)) return;
    const statusSection = document.getElementById('statusSection');
    if (statusSection?.childElementCount) elevateStatusSection(statusSection);
}, true);

function showStatus(message, type = 'info') {

    const displayMessage = ensureTerminalPunctuation(message);

    let statusSection = document.getElementById('statusSection');
    if (!statusSection) {
        statusSection = document.createElement('div');
        statusSection.id = 'statusSection';
        document.body.appendChild(statusSection);
    }

    if (statusSection) {

        if (window._statusTimeout) {

            clearTimeout(window._statusTimeout);

        }

        const statusDiv = document.createElement('div');
        const statusType = ['success', 'error', 'warning', 'info'].includes(type)
            ? type
            : 'info';
        statusSection.setAttribute('aria-live', statusType === 'error' ? 'assertive' : 'polite');
        statusSection.setAttribute('aria-atomic', 'true');
        statusDiv.className = `status ${statusType}`;
        statusDiv.setAttribute('role', statusType === 'error' ? 'alert' : 'status');
        const copy = document.createElement('span');
        copy.className = 'toast-message';
        copy.textContent = displayMessage;
        const dismiss = document.createElement('button');
        dismiss.type = 'button';
        dismiss.className = 'toast-dismiss';
        dismiss.setAttribute('aria-label', t('btn_close'));
        dismiss.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6"/></svg>';
        statusDiv.append(copy, dismiss);
        statusSection.replaceChildren(statusDiv);
        elevateStatusSection(statusSection);

        const returnFocus = document.activeElement;
        const remove = () => {
            if (statusDiv.parentElement === statusSection) {
                const restoreFocus = statusDiv.contains(document.activeElement);
                clearTimeout(window._statusTimeout);
                statusDiv.remove();
                if (typeof statusSection.hidePopover === 'function' && statusSection.matches(':popover-open')) {
                    statusSection.hidePopover();
                }
                document.body.appendChild(statusSection);
                if (restoreFocus && returnFocus?.isConnected && !returnFocus.closest('[inert]')) {
                    returnFocus.focus({preventScroll: true});
                }
            }
        };
        const pause = () => clearTimeout(window._statusTimeout);
        const resume = () => {
            if (statusDiv.parentElement !== statusSection) return;
            pause();
            if (!statusDiv.matches(':hover') && !statusDiv.contains(document.activeElement)) {
                window._statusTimeout = setTimeout(remove, 5000);
            }
        };
        dismiss.addEventListener('click', remove);
        statusDiv.addEventListener('pointerenter', pause);
        statusDiv.addEventListener('pointerleave', resume);
        statusDiv.addEventListener('focusin', pause);
        statusDiv.addEventListener('focusout', () => queueMicrotask(resume));
        resume();

    }

}
