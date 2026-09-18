function autoSetKeepaliveUrl() {

    const url = `${window.location.protocol}//${window.location.host}`;

    document.getElementById('keepaliveUrl').value = url;

}



let mobileMenuReturnFocus = null;

function setMobileMenuState(isOpen, {restoreFocus = false} = {}) {
    const sidebar = document.querySelector('.dashboard-sidebar');
    const overlay = document.querySelector('.sidebar-overlay');
    const menuButton = document.querySelector('.mobile-menu-btn');
    if (!sidebar || !overlay) return;

    const mobileLayout = window.innerWidth <= 960;
    const open = mobileLayout && isOpen;
    const wasOpen = sidebar.classList.contains('open');
    if (open && !wasOpen) mobileMenuReturnFocus = document.activeElement;

    sidebar.classList.toggle('open', open);
    sidebar.inert = mobileLayout && !open;
    const main = document.getElementById('mainContent');
    if (main) main.inert = open;
    if (open) {
        sidebar.setAttribute('role', 'dialog');
        sidebar.setAttribute('aria-modal', 'true');
    } else {
        sidebar.removeAttribute('role');
        sidebar.removeAttribute('aria-modal');
    }
    if (mobileLayout) sidebar.setAttribute('aria-hidden', String(!open));
    else sidebar.removeAttribute('aria-hidden');
    overlay.classList.toggle('open', open);
    document.body.classList.toggle('mobile-menu-open', open);
    overlay.style.display = open ? 'block' : 'none';
    overlay.setAttribute('aria-hidden', String(!open));

    if (menuButton) {
        menuButton.setAttribute('aria-expanded', String(open));
        menuButton.setAttribute('aria-label', t(open ? 'close_navigation' : 'open_navigation'));
    }

    if (open) {
        window.requestAnimationFrame(() => {
            if (sidebar.classList.contains('open')) sidebar.querySelector('.tab.active')?.focus();
        });
    } else {
        const returnTarget = mobileMenuReturnFocus;
        mobileMenuReturnFocus = null;
        if (restoreFocus && wasOpen && returnTarget?.focus) returnTarget.focus();
    }
}

function toggleMobileMenu() {
    const sidebar = document.querySelector('.dashboard-sidebar');
    const isOpen = sidebar?.classList.contains('open') === true;
    setMobileMenuState(!isOpen, {restoreFocus: isOpen});
}

function syncMobileNavigationState() {
    const sidebar = document.querySelector('.dashboard-sidebar');
    setMobileMenuState(sidebar?.classList.contains('open') === true);
}

document.addEventListener('keydown', (event) => {
    const sidebar = document.querySelector('.dashboard-sidebar');
    if (!sidebar?.classList.contains('open') || !sidebar.contains(event.target)) return;
    trapModalFocus(sidebar, event);
    if (event.key === 'Escape') {
        setMobileMenuState(false, {restoreFocus: true});
    }
});

document.addEventListener('DOMContentLoaded', syncMobileNavigationState);
