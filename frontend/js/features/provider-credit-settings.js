const ANTIGRAVITY_CREDIT_PAGE_SIZE = 20;

const antigravityCreditState = {
    page: 1,
    total: 0,
    items: [],
    selectedFilename: '',
    loaded: false,
    loading: false
};

function getAntigravityCreditElements() {
    return {
        section: document.getElementById('antigravityCreditSettings'),
        loading: document.getElementById('antigravityCreditLoading'),
        content: document.getElementById('antigravityCreditContent'),
        empty: document.getElementById('antigravityCreditEmpty'),
        error: document.getElementById('antigravityCreditError'),
        select: document.getElementById('antigravityCreditSelect'),
        toggle: document.getElementById('antigravityCreditToggleBtn'),
        refresh: document.getElementById('antigravityCreditRefreshBtn'),
        previous: document.getElementById('antigravityCreditPrevBtn'),
        next: document.getElementById('antigravityCreditNextBtn'),
        pageInfo: document.getElementById('antigravityCreditPageInfo'),
        state: document.getElementById('antigravityCreditState')
    };
}

function selectedAntigravityCreditItem() {
    return antigravityCreditState.items.find(
        (item) => item.filename === antigravityCreditState.selectedFilename
    ) || null;
}

function setAntigravityCreditError(message) {
    const element = getAntigravityCreditElements().error;
    if (!element) return;
    element.textContent = message || '';
    element.classList.toggle('hidden', !message);
}

function renderAntigravityCreditSettings() {
    const elements = getAntigravityCreditElements();
    if (!elements.section) return;

    const hasItems = antigravityCreditState.items.length > 0;
    elements.section.setAttribute('aria-busy', String(antigravityCreditState.loading));
    elements.loading?.classList.toggle('hidden', !antigravityCreditState.loading);
    elements.content?.classList.toggle('hidden', !hasItems);
    elements.empty?.classList.toggle(
        'hidden', !antigravityCreditState.loaded || antigravityCreditState.total !== 0
    );

    if (elements.select && hasItems) {
        const options = antigravityCreditState.items.map((item) => {
            const option = document.createElement('option');
            const account = item.user_email || item.filename;
            const creditState = t(
                item.enable_credit ? 'credential_state_on' : 'credential_state_off'
            );
            option.value = item.filename;
            option.textContent = `${account} — ${t('credential_badge_credits', {state: creditState})}`;
            return option;
        });
        elements.select.replaceChildren(...options);
        if (!antigravityCreditState.items.some(
            (item) => item.filename === antigravityCreditState.selectedFilename
        )) {
            antigravityCreditState.selectedFilename = antigravityCreditState.items[0].filename;
        }
        elements.select.value = antigravityCreditState.selectedFilename;
    }

    const selected = selectedAntigravityCreditItem();
    if (elements.toggle) {
        const enabling = !selected?.enable_credit;
        const labelKey = enabling ? 'btn_enable_credit' : 'btn_disable_credit';
        elements.toggle.dataset.i18n = labelKey;
        elements.toggle.textContent = t(labelKey);
        elements.toggle.title = t(
            enabling ? 'btn_enable_credit_title' : 'btn_disable_credit_title'
        );
        elements.toggle.disabled = antigravityCreditState.loading || !selected;
    }
    if (elements.select) elements.select.disabled = antigravityCreditState.loading || !hasItems;
    if (elements.refresh) elements.refresh.disabled = antigravityCreditState.loading;

    const totalPages = Math.max(
        1, Math.ceil(antigravityCreditState.total / ANTIGRAVITY_CREDIT_PAGE_SIZE)
    );
    if (elements.previous) {
        elements.previous.disabled = antigravityCreditState.loading || antigravityCreditState.page <= 1;
    }
    if (elements.next) {
        elements.next.disabled = antigravityCreditState.loading
            || antigravityCreditState.page >= totalPages;
    }
    if (elements.pageInfo) {
        const start = antigravityCreditState.total
            ? ((antigravityCreditState.page - 1) * ANTIGRAVITY_CREDIT_PAGE_SIZE) + 1
            : 0;
        const end = Math.min(
            antigravityCreditState.total,
            start + antigravityCreditState.items.length - 1
        );
        elements.pageInfo.textContent = t('status_page_info', {
            page: antigravityCreditState.page,
            total: totalPages,
            start,
            end,
            count: antigravityCreditState.total
        });
    }
    if (elements.state) {
        elements.state.textContent = selected
            ? t('credential_badge_credits', {
                state: t(selected.enable_credit ? 'credential_state_on' : 'credential_state_off')
            })
            : '';
    }
}

async function loadAntigravityCreditSettings({page = antigravityCreditState.page} = {}) {
    if (!getAntigravityCreditElements().section || antigravityCreditState.loading) return;

    antigravityCreditState.loading = true;
    setAntigravityCreditError(null);
    renderAntigravityCreditSettings();
    try {
        const safePage = Math.max(1, Number.parseInt(page, 10) || 1);
        const query = new URLSearchParams({
            mode: 'provider',
            provider_filter: 'google_antigravity',
            status_filter: 'all',
            offset: String((safePage - 1) * ANTIGRAVITY_CREDIT_PAGE_SIZE),
            limit: String(ANTIGRAVITY_CREDIT_PAGE_SIZE)
        });
        const response = await fetch(`./api/credentials/status?${query.toString()}`, {
            headers: getAuthHeaders()
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.detail || payload.error || t('unknown_error'));
        if (!Array.isArray(payload.items)) throw new Error(t('unknown_error'));

        const items = payload.items.map((item) => ({
            filename: String(item.filename || ''),
            user_email: String(item.user_email || ''),
            enable_credit: item.enable_credit === true
        })).filter((item) => item.filename);
        antigravityCreditState.page = safePage;
        antigravityCreditState.total = Math.max(0, Number(payload.total) || 0);
        antigravityCreditState.items = items;
        antigravityCreditState.loaded = true;
        if (!items.some((item) => item.filename === antigravityCreditState.selectedFilename)) {
            antigravityCreditState.selectedFilename = items[0]?.filename || '';
        }
    } catch (error) {
        setAntigravityCreditError(t('status_load_failed', {
            error: error.message || t('unknown_error')
        }));
    } finally {
        antigravityCreditState.loading = false;
        renderAntigravityCreditSettings();
    }
}

async function toggleAntigravityCredentialCredit() {
    const selected = selectedAntigravityCreditItem();
    if (!selected || antigravityCreditState.loading) return;

    const action = selected.enable_credit ? 'disable_credit' : 'enable_credit';
    const enabling = action === 'enable_credit';
    const confirmed = await showConfirmModal(
        t(enabling ? 'confirm_batch_enable_credit' : 'confirm_batch_disable_credit', {count: 1}),
        {
            title: t(
                enabling ? 'confirm_batch_enable_credit_title' : 'confirm_batch_disable_credit_title'
            ),
            confirmLabel: t(enabling ? 'btn_enable_credit' : 'btn_disable_credit')
        }
    );
    if (!confirmed) return;

    antigravityCreditState.loading = true;
    setAntigravityCreditError(null);
    renderAntigravityCreditSettings();
    try {
        const response = await fetch('./api/credentials/action?mode=provider', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({filename: selected.filename, action})
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.detail || payload.error || t('unknown_error'));
        selected.enable_credit = enabling;
        showStatus(payload.message || t('status_action_success', {action}), 'success');
    } catch (error) {
        const message = error.message || t('unknown_error');
        setAntigravityCreditError(t('status_action_failed', {error: message}));
        showStatus(t('status_action_failed', {error: message}), 'error');
    } finally {
        antigravityCreditState.loading = false;
        renderAntigravityCreditSettings();
    }
}

function initializeAntigravityCreditSettings() {
    const elements = getAntigravityCreditElements();
    if (!elements.section || elements.section.dataset.initialized === 'true') return;
    elements.section.dataset.initialized = 'true';
    elements.select?.addEventListener('change', (event) => {
        antigravityCreditState.selectedFilename = event.target.value;
        renderAntigravityCreditSettings();
    });
    elements.toggle?.addEventListener('click', () => void toggleAntigravityCredentialCredit());
    elements.refresh?.addEventListener('click', () => void loadAntigravityCreditSettings());
    elements.previous?.addEventListener('click', () => {
        void loadAntigravityCreditSettings({page: antigravityCreditState.page - 1});
    });
    elements.next?.addEventListener('click', () => {
        void loadAntigravityCreditSettings({page: antigravityCreditState.page + 1});
    });
    document.addEventListener('click', (event) => {
        const trigger = event.target?.closest?.(
            '[data-tab="providers"], #providerSelectorGoogleAntigravity'
        );
        if (trigger && !antigravityCreditState.loaded) void loadAntigravityCreditSettings();
    });
    if (['/providers', '/oauth', '/upload'].includes(window.location.pathname)) {
        void loadAntigravityCreditSettings();
    }
}

document.addEventListener('DOMContentLoaded', initializeAntigravityCreditSettings, {once: true});
document.addEventListener('polaris:locale-change', renderAntigravityCreditSettings);
