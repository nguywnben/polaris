const ABOUT_TIERS = Object.freeze(['core', 'advanced', 'compatibility', 'experimental']);
const ABOUT_STATES = Object.freeze(['active', 'available', 'disabled', 'blocked']);

function aboutBoundedText(value, maximum, fallback = '') {
    return typeof value === 'string' && value.length > 0 && value.length <= maximum
        ? value
        : fallback;
}

function normalizeAboutVersion(value) {
    const normalized = aboutBoundedText(value, 80, '').trim();
    return normalized && !/^v?unknown$/i.test(normalized)
        ? normalized.replace(/^v(?=\d)/i, '')
        : null;
}

function validateAboutVersion(payload) {
    if (!payload || payload.success !== true) throw new Error(t('about.load_failed'));
    const source = ['container', 'git', 'development'].includes(payload.source)
        ? payload.source
        : 'development';
    return Object.freeze({
        version: normalizeAboutVersion(payload.version),
        revision: aboutBoundedText(payload.full_hash, 128, t('about.not_available')),
        date: aboutBoundedText(payload.date, 80, t('about.not_available')),
        source
    });
}

function validateCapabilitySnapshot(payload) {
    if (
        !payload || payload.schema_version !== 1 || payload.profile !== 'self_hosted'
        || !Array.isArray(payload.capabilities) || payload.capabilities.length > 128
    ) {
        throw new Error(t('about.load_failed'));
    }
    const capabilities = payload.capabilities.map((item) => {
        if (
            !item || typeof item !== 'object'
            || !/^[a-z][a-z0-9]*(?:[._][a-z0-9]+)*$/.test(item.id || '')
            || !ABOUT_TIERS.includes(item.tier) || !ABOUT_STATES.includes(item.state)
        ) {
            throw new Error(t('about.load_failed'));
        }
        return Object.freeze({
            id: item.id,
            name: aboutBoundedText(item.name, 80, item.id),
            tier: item.tier,
            state: item.state
        });
    });
    return Object.freeze(capabilities);
}

function aboutFact(labelKey, value, technical = false) {
    const row = document.createElement('div');
    const term = document.createElement('dt');
    const description = document.createElement('dd');
    term.textContent = t(labelKey);
    description.textContent = value;
    if (technical) description.className = 'technical-value';
    row.append(term, description);
    return row;
}

function renderAboutVersion(version) {
    const facts = document.getElementById('aboutBuildFacts');
    if (!facts) return;
    facts.replaceChildren(
        aboutFact(
            'about.version',
            version.version ? `v${version.version}` : t('unknown_version'),
            true
        ),
        aboutFact('about.revision', version.revision, true),
        aboutFact('about.build_date', version.date, true),
        aboutFact('about.version_source', t(`about.source_${version.source}`))
    );
    facts.setAttribute('aria-busy', 'false');
}

function visibleAboutTiers(capabilities) {
    return ABOUT_TIERS.filter((tier) => capabilities.some((item) => item.tier === tier));
}

function renderAboutCapabilities(capabilities) {
    const container = document.getElementById('aboutSupportTiers');
    if (!container) return;
    const rows = visibleAboutTiers(capabilities).map((tier) => {
        const row = document.createElement('article');
        row.className = `support-tier support-tier-${tier}`;
        row.setAttribute('role', 'listitem');
        const copy = document.createElement('div');
        const title = document.createElement('h3');
        const description = document.createElement('p');
        const status = document.createElement('p');
        title.textContent = t(`about.tier_${tier}`);
        description.textContent = t(`about.tier_${tier}_description`);
        status.className = 'support-tier-status';
        const counts = Object.fromEntries(ABOUT_STATES.map((state) => [
            state,
            formatConsoleNumber(capabilities.filter((item) => item.tier === tier && item.state === state).length)
        ]));
        status.textContent = t('about.tier_status', counts);
        copy.append(title, description);
        row.append(copy, status);
        return row;
    });
    container.replaceChildren(...rows);
    container.setAttribute('aria-busy', 'false');
}

async function loadAboutPage(options = {}) {
    const preserveContent = options.preserveContent ?? Boolean(AppState.aboutLoaded);
    clearPageState('aboutState');
    try {
        const [versionResponse, capabilityResponse] = await Promise.all([
            fetch('./api/version/info'),
            fetch('./api/capabilities', {headers: getAuthHeaders()})
        ]);
        const [versionPayload, capabilityPayload] = await Promise.all([
            versionResponse.json(), capabilityResponse.json()
        ]);
        if (!versionResponse.ok || !capabilityResponse.ok) throw new Error(t('about.load_failed'));
        AppState.aboutVersion = validateAboutVersion(versionPayload);
        AppState.aboutCapabilities = validateCapabilitySnapshot(capabilityPayload);
        renderAboutVersion(AppState.aboutVersion);
        renderAboutCapabilities(AppState.aboutCapabilities);
        AppState.aboutLoaded = true;
    } catch (error) {
        const message = error?.message || t('about.load_failed');
        showPageState('aboutState', {
            kind: preserveContent ? 'stale' : 'error',
            title: t(preserveContent ? 'warning' : 'error'),
            message,
            actionLabel: t('refresh'),
            onAction: () => loadAboutPage({preserveContent: Boolean(AppState.aboutLoaded)})
        });
    }
}

globalThis.document?.addEventListener?.('omni:locale-change', () => {
    if (AppState.aboutVersion) renderAboutVersion(AppState.aboutVersion);
    if (Array.isArray(AppState.aboutCapabilities)) {
        renderAboutCapabilities(AppState.aboutCapabilities);
    }
});
