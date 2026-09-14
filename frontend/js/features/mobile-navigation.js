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
        window.requestAnimationFrame(() => sidebar.querySelector('.tab.active')?.focus());
    } else if (!open) {
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
    const sidebarOpen = document.querySelector('.dashboard-sidebar')?.classList.contains('open');
    if (event.key === 'Escape' && sidebarOpen) {
        setMobileMenuState(false, {restoreFocus: true});
    }
});

document.addEventListener('DOMContentLoaded', syncMobileNavigationState);
