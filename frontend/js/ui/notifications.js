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
    )).filter(element => !element.hidden && element.getAttribute('aria-hidden') !== 'true');
}

function mountModal(modal) {

    modalReturnFocus.set(modal, document.activeElement);
    document.body.appendChild(modal);
    const focusHandler = (event) => {
        if (event.key !== 'Tab') return;
        const focusable = getModalFocusableElements(modal);
        if (!focusable.length) {
            event.preventDefault();
            return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    };
    modal.addEventListener('keydown', focusHandler);
    modalFocusHandlers.set(modal, focusHandler);
    queueMicrotask(() => {
        if (!modal.isConnected || modal.contains(document.activeElement)) return;
        getModalFocusableElements(modal)[0]?.focus();
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

function showStatus(message, type = 'info') {

    const displayMessage = ensureTerminalPunctuation(message);

    const statusSection = document.getElementById('statusSection');

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

        window._statusTimeout = setTimeout(() => {

            if (statusDiv.parentElement === statusSection) statusDiv.remove();

        }, 5000);

    } else {

        showMessageModal(t('dialog_tip'), displayMessage, 'info');

    }

}
