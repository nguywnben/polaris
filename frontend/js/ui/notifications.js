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

function getModalFocusableElements(modal) {
    return Array.from(modal.querySelectorAll(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
    )).filter(element => !element.hidden && element.getAttribute('aria-hidden') !== 'true' && element.getClientRects().length > 0);
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
    const focusHandler = event => trapModalFocus(modal, event);
    modal.addEventListener('keydown', focusHandler);
    modalFocusHandlers.set(modal, focusHandler);
    queueMicrotask(() => {
        if (!modal.isConnected || modal.contains(document.activeElement)) return;
        focusModalSurface(modal);
    });
    return Promise.resolve();

}

function unmountModal(modal) {

    const focusHandler = modalFocusHandlers.get(modal);
    if (focusHandler) modal.removeEventListener('keydown', focusHandler);
    const returnTarget = modalReturnFocus.get(modal);
    modal.remove();
    modalFocusHandlers.delete(modal);
    modalReturnFocus.delete(modal);
    if (returnTarget?.isConnected && typeof returnTarget.focus === 'function') returnTarget.focus();
    return Promise.resolve();

}

function elevateStatusSection(statusSection) {
    // Native modal dialogs sit above every z-index. Keep their live region inside
    // the active dialog (outside content is inert), then promote it without focus.
    const dialogs = [...document.querySelectorAll('dialog:modal')];
    const activeDialog = dialogs.find(dialog => dialog.contains(document.activeElement)) || dialogs.at(-1);
    const parent = activeDialog || document.body;
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
        statusDiv.textContent = displayMessage;
        statusSection.replaceChildren(statusDiv);
        elevateStatusSection(statusSection);

        window._statusTimeout = setTimeout(() => {

            if (statusDiv.parentElement === statusSection) {
                statusDiv.remove();
                if (typeof statusSection.hidePopover === 'function' && statusSection.matches(':popover-open')) {
                    statusSection.hidePopover();
                }
                document.body.appendChild(statusSection);
            }

        }, 5000);

    }

}
