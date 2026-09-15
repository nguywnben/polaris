// Bounded server pages; provider summaries are independent of the visible page.
const UsagePages = {current: null, historical: null, revision: 0, busy: false, period: null};

async function loadUsagePages(requested = {}) {
    const revision = ++UsagePages.revision;
    const period = getUsagePeriodConfig().value;
    UsagePages.busy = true;
    try {
        const pages = await Promise.all(['current', 'historical'].map(async group => {
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
        [UsagePages.current, UsagePages.historical] = pages;
        UsagePages.period = period;
        AppState.usagePage = Math.floor(pages[0].offset / pages[0].page_size) + 1;
        AppState.historicalUsagePage = Math.floor(pages[1].offset / pages[1].page_size) + 1;
        AppState.usageStatsData = {...pages[0].data, ...pages[1].data};
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
    section?.setAttribute('aria-busy', 'true');
    try {
        if (await loadUsagePages({[group]: next})) {
            renderUsageList();
            renderProviderHealthMatrix();
        }
    } catch (_error) {
        showStatus(t('failed_to_load_usage_statistics'), 'error');
    } finally {
        section?.removeAttribute('aria-busy');
    }
}

function getProviderUsageEntries() {
    if (!UsagePages.current) return getCurrentUsageEntriesWithTraffic();
    return (UsagePages.current.provider_totals || []).map((stats, index) => [`provider-${index}`, stats]);
}
