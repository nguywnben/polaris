// Bounded server pages; provider summaries are independent of the visible page.
const UsagePages = {current: null, historical: null, revision: 0, busy: false, period: null};

async function loadUsagePages(requested = {}) {
    const revision = ++UsagePages.revision;
    const period = getUsagePeriodConfig().value;
    UsagePages.busy = true;
    try {
        const periodChanged = UsagePages.period !== period;
        const requestedGroups = Object.keys(requested).filter(group => group === 'current' || group === 'historical');
        const groups = periodChanged || !UsagePages.current || !UsagePages.historical
            ? ['current', 'historical']
            : (requestedGroups.length ? requestedGroups : ['current', 'historical']);
        const pages = await Promise.all(groups.map(async group => {
            const size = group === 'current' ? AppState.usagePageSize : AppState.historicalUsagePageSize;
            const oldPage = group === 'current' ? AppState.usagePage : AppState.historicalUsagePage;
            const page = UsagePages.period === period ? (requested[group] || oldPage || 1) : 1;
            const query = new URLSearchParams({period, timezone_offset_minutes: new Date().getTimezoneOffset(),
                page_size: size || 10, offset: (page - 1) * (size || 10), group, order: 'name'});
            const fetchPage = async () => {
                const response = await fetch(`./api/usage/stats/page?${query}`, {headers: getAuthHeaders()});
                if (!response.ok) throw new Error(t('failed_to_load_usage_statistics'));
                const payload = await response.json();
                if (!payload.success || !payload.data || !Number.isInteger(payload.total_items)) {
                    throw new Error(t('failed_to_load_usage_statistics'));
                }
                return payload;
            };
            let payload = await fetchPage();
            // A deletion may remove the last page between visits. Clamp once, never loop.
            if (!Object.keys(payload.data).length && payload.total_items > 0 && page > 1) {
                query.set('offset', Math.floor((payload.total_items - 1) / (size || 10)) * (size || 10));
                payload = await fetchPage();
            }
            return payload;
        }));
        if (revision !== UsagePages.revision || period !== getUsagePeriodConfig().value) return false;
        const loadedPages = Object.fromEntries(groups.map((group, index) => [group, pages[index]]));
        if (loadedPages.current) UsagePages.current = loadedPages.current;
        if (loadedPages.historical) UsagePages.historical = loadedPages.historical;
        UsagePages.period = period;
        AppState.usagePage = Math.floor(UsagePages.current.offset / UsagePages.current.page_size) + 1;
        AppState.historicalUsagePage = Math.floor(UsagePages.historical.offset / UsagePages.historical.page_size) + 1;
        AppState.usageStatsData = {...UsagePages.current.data, ...UsagePages.historical.data};
        return true;
    } finally {
        if (revision === UsagePages.revision) UsagePages.busy = false;
    }
}

async function moveUsagePage(group, delta) {
    if (UsagePages.busy) return;
    const payload = UsagePages[group];
    if (!payload) return;
    const page = Math.floor(payload.offset / payload.page_size) + 1;
    const last = Math.max(1, Math.ceil(payload.total_items / payload.page_size));
    const next = Math.min(last, Math.max(1, page + delta));
    if (next === page) return;
    const section = document.getElementById(group === 'current' ? 'usageList' : 'historicalUsageList');
    const prefix = group === 'current' ? 'usage' : 'historicalUsage';
    const prevButton = document.getElementById(`${prefix}PrevPageBtn`);
    const nextButton = document.getElementById(`${prefix}NextPageBtn`);
    const pressedButton = delta < 0 ? prevButton : nextButton;
    if (prevButton) prevButton.disabled = true;
    if (nextButton) nextButton.disabled = true;
    pressedButton?.setAttribute('aria-busy', 'true');
    section?.setAttribute('aria-busy', 'true');
    try {
        if (await loadUsagePages({[group]: next})) {
            renderUsageList(group);
        }
    } catch (_error) {
        showStatus(t('failed_to_load_usage_statistics'), 'error');
    } finally {
        section?.removeAttribute('aria-busy');
        pressedButton?.removeAttribute('aria-busy');
        const current = UsagePages[group] || payload;
        if (prevButton) prevButton.disabled = current.offset <= 0;
        if (nextButton) nextButton.disabled = current.offset + current.page_size >= current.total_items;
    }
}

function getProviderUsageEntries() {
    if (!UsagePages.current) return getCurrentUsageEntriesWithTraffic();
    return (UsagePages.current.provider_totals || []).map((stats, index) => [`provider-${index}`, stats]);
}
