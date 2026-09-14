const ACTIVITY_VIEWS = Object.freeze({
    traces: {tabId: 'activityTracesTab', panelId: 'activityTracesPanel', loader: 'traces'},
    audit: {tabId: 'activityAuditTab', panelId: 'activityAuditPanel', loader: 'audit'},
    runtime: {tabId: 'activityRuntimeTab', panelId: 'activityRuntimePanel', loader: 'runtime_logs'}
});
const ACTIVITY_OUTCOMES = new Set(['', 'succeeded', 'failed', 'denied', 'cancelled']);
const ACTIVITY_ACTORS = new Set(['', 'local_owner', 'oidc_user', 'panel_session', 'root_key', 'virtual_key', 'system']);
const ACTIVITY_REQUEST_ID_PATTERN = /^[A-Za-z0-9._:-]{0,128}$/;
const ACTIVITY_DIMENSION_PATTERN = /^[A-Za-z0-9._:/+@*-]{0,128}$/;
const MAX_ACTIVITY_LOG_FILTER_LENGTH = 8192;
const ACTIVITY_TRACE_OUTCOMES = Object.freeze({
    succeeded: ['succeeded'],
    failed: ['client_error', 'upstream_error', 'unavailable', 'internal_error'],
    denied: ['denied', 'rate_limited'],
    cancelled: ['cancelled']
});
const ACTIVITY_AUDIT_OUTCOMES = Object.freeze({
    succeeded: ['succeeded'],
    failed: ['failed', 'not_found', 'conflict', 'invalid', 'timed_out'],
    denied: ['denied'],
    cancelled: ['cancelled']
});

const ActivityFilterState = {
    filters: Object.freeze({started_after: '', started_before: '', outcome: '', provider: '', actor_type: '', request_id: ''}),
    revision: 0,
    appliedRevision: {traces: -1, audit: -1, runtime: -1}
};

function normalizeActivityView(view) {
    return Object.hasOwn(ACTIVITY_VIEWS, view) ? view : 'traces';
}

function activityViewFromLocation(pathname = window.location.pathname, search = window.location.search) {
    if (pathname === '/audit') return 'audit';
    if (pathname === '/logs') return 'runtime';
    return normalizeActivityView(new URLSearchParams(search).get('view'));
}

function normalizeActivityFilters(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    const filters = {
        started_after: String(value.started_after || ''),
        started_before: String(value.started_before || ''),
        outcome: String(value.outcome || ''),
        provider: String(value.provider || '').trim(),
        actor_type: String(value.actor_type || ''),
        request_id: String(value.request_id || '').trim()
    };
    const after = filters.started_after ? Date.parse(filters.started_after) : null;
    const before = filters.started_before ? Date.parse(filters.started_before) : null;
    if ((after !== null && !Number.isFinite(after))
        || (before !== null && !Number.isFinite(before))
        || (after !== null && before !== null && after > before)
        || !ACTIVITY_OUTCOMES.has(filters.outcome)
        || !ACTIVITY_DIMENSION_PATTERN.test(filters.provider)
        || !ACTIVITY_ACTORS.has(filters.actor_type)
        || !ACTIVITY_REQUEST_ID_PATTERN.test(filters.request_id)) return null;
    return Object.freeze(filters);
}

function readActivityFilters() {
    const dateValue = (id) => {
        const value = document.getElementById(id)?.value || '';
        const timestamp = value ? Date.parse(value) : NaN;
        return Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : value;
    };
    return normalizeActivityFilters({
        started_after: dateValue('activityStartedAfter'),
        started_before: dateValue('activityStartedBefore'),
        outcome: document.getElementById('activityOutcome')?.value || '',
        provider: document.getElementById('activityProvider')?.value || '',
        actor_type: document.getElementById('activityActorType')?.value || '',
        request_id: document.getElementById('activityRequestId')?.value || ''
    });
}

function mergeActivityTraceFilters(filters, common = ActivityFilterState.filters) {
    return {
        ...filters,
        outcomes: common.outcome ? [...ACTIVITY_TRACE_OUTCOMES[common.outcome]] : [],
        providers: common.provider ? [common.provider] : [],
        request_id: common.request_id,
        started_after: common.started_after,
        started_before: common.started_before
    };
}

function mergeActivityAuditFilters(filters, common = ActivityFilterState.filters) {
    return {
        ...filters,
        outcomes: common.outcome ? [...ACTIVITY_AUDIT_OUTCOMES[common.outcome]] : [],
        actor_types: common.actor_type ? [common.actor_type] : [],
        request_id: common.request_id,
        occurred_after: common.started_after,
        occurred_before: common.started_before
    };
}

function activityLogLineMatches(line, common = ActivityFilterState.filters) {
    const text = String(line || '').slice(0, MAX_ACTIVITY_LOG_FILTER_LENGTH);
    const lower = text.toLowerCase();
    for (const value of [common.request_id, common.provider, common.actor_type]) {
        if (value && !lower.includes(value.toLowerCase())) return false;
    }
    const outcomePatterns = {
        succeeded: /\b(success|succeeded|completed)\b/i,
        failed: /\b(error|failed|failure|unavailable|timed?\s*out)\b/i,
        denied: /\b(denied|rate[_ -]?limited|forbidden)\b/i,
        cancelled: /\bcancell?ed\b/i
    };
    if (common.outcome && !outcomePatterns[common.outcome].test(text)) return false;
    if (common.started_after || common.started_before) {
        const match = text.match(/^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]/);
        const timestamp = match ? Date.parse(match[1].replace(' ', 'T')) : NaN;
        if (!Number.isFinite(timestamp)) return false;
        if (common.started_after && timestamp < Date.parse(common.started_after)) return false;
        if (common.started_before && timestamp > Date.parse(common.started_before)) return false;
    }
    return true;
}

async function loadActivityView(view) {
    const selectedView = normalizeActivityView(view);
    const stale = ActivityFilterState.appliedRevision[selectedView] !== ActivityFilterState.revision;
    if (stale && selectedView === 'traces' && typeof loadTraceConsole === 'function') {
        await loadTraceConsole(true);
    } else if (stale && selectedView === 'audit' && typeof loadAuditConsole === 'function') {
        await loadAuditConsole(true);
    } else {
        await triggerTabDataLoad(ACTIVITY_VIEWS[selectedView].loader, {force: stale});
    }
    ActivityFilterState.appliedRevision[selectedView] = ActivityFilterState.revision;
    if (selectedView === 'runtime' && typeof filterLogs === 'function') filterLogs();
}

function setActivityView(view, {load = true} = {}) {
    const selectedView = normalizeActivityView(view);
    AppState.activeActivityView = selectedView;
    for (const [name, definition] of Object.entries(ACTIVITY_VIEWS)) {
        const selected = name === selectedView;
        const tab = document.getElementById(definition.tabId);
        const panel = document.getElementById(definition.panelId);
        if (tab) {
            tab.setAttribute('aria-selected', String(selected));
            tab.tabIndex = selected ? 0 : -1;
        }
        if (panel) panel.hidden = !selected;
    }
    if (load) return loadActivityView(selectedView);
}

function activityUrl(view) {
    return view === 'traces' ? '/activity' : `/activity?view=${encodeURIComponent(view)}`;
}

function switchActivityView(view) {
    const selectedView = normalizeActivityView(view);
    const nextUrl = activityUrl(selectedView);
    if (`${window.location.pathname}${window.location.search}` !== nextUrl) history.pushState(null, '', nextUrl);
    return setActivityView(selectedView);
}

function loadActivityConsole() {
    return loadActivityView(normalizeActivityView(AppState.activeActivityView));
}

function setActivityFilterStatus(key) {
    const status = document.getElementById('activityFilterStatus');
    if (status) status.textContent = key ? t(key) : '';
}

function resetActivityPagination() {
    if (typeof TraceConsoleState !== 'undefined') {
        TraceConsoleState.cursor = null;
        TraceConsoleState.cursorStack = [];
        TraceConsoleState.nextCursor = null;
    }
    if (typeof AuditConsoleState !== 'undefined') {
        AuditConsoleState.cursor = null;
        AuditConsoleState.cursorStack = [];
        AuditConsoleState.nextCursor = null;
    }
}

function commitActivityFilters(filters) {
    ActivityFilterState.filters = filters;
    ActivityFilterState.revision += 1;
    resetActivityPagination();
    setActivityFilterStatus('activity.filters_applied');
    return setActivityView(AppState.activeActivityView);
}

function applyActivityFilters(event) {
    event?.preventDefault();
    const form = document.getElementById('activityFilterForm');
    if (!form?.reportValidity()) return;
    const filters = readActivityFilters();
    if (!filters) {
        setActivityFilterStatus('activity.invalid_filters');
        return;
    }
    return commitActivityFilters(filters);
}

function clearActivityFilters() {
    document.getElementById('activityFilterForm')?.reset();
    const filters = normalizeActivityFilters({});
    if (filters) return commitActivityFilters(filters);
}

function investigateActivityRequest(requestId, view = 'traces', {navigateToActivity = false} = {}) {
    const value = String(requestId || '').trim();
    if (!value || !ACTIVITY_REQUEST_ID_PATTERN.test(value)) return false;
    const filters = normalizeActivityFilters({...ActivityFilterState.filters, request_id: value});
    if (!filters) return false;
    ActivityFilterState.filters = filters;
    ActivityFilterState.revision += 1;
    resetActivityPagination();
    const input = document.getElementById('activityRequestId');
    if (input) input.value = value;
    setActivityFilterStatus('activity.filters_applied');
    if (navigateToActivity) {
        AppState.activeActivityView = normalizeActivityView(view);
        navigate('/activity');
    } else {
        void switchActivityView(view);
    }
    return true;
}

function initActivityTabs() {
    document.getElementById('activityFilterForm')?.addEventListener('submit', applyActivityFilters);
    for (const [name, definition] of Object.entries(ACTIVITY_VIEWS)) {
        const tab = document.getElementById(definition.tabId);
        tab?.addEventListener('keydown', (event) => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault();
            const names = Object.keys(ACTIVITY_VIEWS);
            const currentIndex = names.indexOf(name);
            let nextIndex = currentIndex;
            if (event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + names.length) % names.length;
            if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % names.length;
            if (event.key === 'Home') nextIndex = 0;
            if (event.key === 'End') nextIndex = names.length - 1;
            const nextView = names[nextIndex];
            switchActivityView(nextView);
            document.getElementById(ACTIVITY_VIEWS[nextView].tabId)?.focus();
        });
    }
    setActivityView(activityViewFromLocation(), {load: false});
}

document.addEventListener('DOMContentLoaded', initActivityTabs);
