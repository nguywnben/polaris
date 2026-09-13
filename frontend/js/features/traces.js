const TRACE_SAFE_FILTER_STORAGE_KEY = 'omni_gateway_trace_safe_filters_v1';
const TRACE_FIELDS = ['schema_version', 'trace_id', 'request_id', 'protocol', 'started_at', 'completed_at', 'outcome', 'status_code', 'duration_ms', 'requested_model', 'selected_provider', 'input_tokens', 'output_tokens', 'total_tokens', 'cost_usd', 'decisions', 'decisions_truncated'];
const TRACE_DECISION_FIELDS = ['sequence', 'elapsed_ms', 'category', 'action', 'result', 'reason', 'provider', 'model', 'attempt', 'status_code', 'latency_ms', 'candidate_count', 'original_tokens', 'final_tokens', 'input_tokens', 'output_tokens', 'cached_tokens', 'reasoning_tokens', 'cost_usd'];
const TRACE_PROTOCOLS = new Set(['openai_chat', 'openai_responses', 'anthropic_messages', 'anthropic_count_tokens', 'gemini_generate', 'gemini_stream', 'gemini_count_tokens', 'vertex_openai', 'vertex_gemini_generate', 'vertex_gemini_stream', 'vertex_gemini_count_tokens']);
const TRACE_OUTCOMES = new Set(['succeeded', 'client_error', 'denied', 'rate_limited', 'upstream_error', 'unavailable', 'internal_error', 'cancelled']);
const TRACE_CATEGORIES = new Set(['request', 'routing', 'fallback', 'retry', 'cooldown', 'compression', 'guardrail', 'cache', 'quota', 'upstream', 'usage', 'outcome']);
const TRACE_ACTIONS = new Set(['accepted', 'selected', 'unavailable', 'attempted', 'switched', 'scheduled', 'exhausted', 'applied', 'skipped', 'evaluated', 'blocked', 'masked', 'hit', 'miss', 'stored', 'reserved', 'denied', 'committed', 'released', 'succeeded', 'failed', 'recorded', 'completed', 'cancelled']);
const TRACE_RESULTS = new Set(['succeeded', 'failed', 'skipped', 'allowed', 'denied', 'hit', 'miss']);
const TRACE_REASONS = new Set(['none', 'request_received', 'feature_disabled', 'not_eligible', 'healthy_candidate', 'no_candidate', 'provider_fallback', 'credential_switched', 'retryable_status', 'retry_limit', 'cooldown_active', 'quota_cooldown', 'model_cooldown', 'history_within_limit', 'token_budget', 'content_limit', 'policy_unavailable', 'policy_passed', 'pii_masked', 'injection_detected', 'blocked_keyword', 'cache_hit', 'cache_miss', 'cache_stored', 'quota_reserved', 'quota_exceeded', 'budget_exceeded', 'provider_error', 'rate_limited', 'timeout', 'model_unavailable', 'usage_recorded', 'completed', 'client_error', 'server_error', 'cancelled']);
const TRACE_ID_PATTERN = /^[0-9a-f]{32}$/;
const TRACE_REQUEST_ID_PATTERN = /^[A-Za-z0-9._:-]{1,128}$/;
const TRACE_DIMENSION_PATTERN = /^[A-Za-z0-9._:/+@*-]{0,128}$/;
const TRACE_EXPORT_FILENAME_PATTERN = /^omni-traces-\d{8}T\d{6}Z\.(?:jsonl|csv)$/;

const TraceConsoleState = {
    traces: [], filters: {}, cursor: null, cursorStack: [], nextCursor: null,
    loaded: false, loading: false, requestId: 0, abortController: null,
    exporting: false, selectedTrace: null, detailReturnFocus: null, retention: null,
    detailRequestId: 0, detailAbortController: null
};

function traceElement(id) { return document.getElementById(id); }
function traceExactFields(value, fields) {
    return value && typeof value === 'object' && !Array.isArray(value)
        && Object.keys(value).length === fields.length
        && fields.every((field) => Object.hasOwn(value, field));
}
function traceBoundedInteger(value, minimum, maximum) {
    return Number.isInteger(value) && value >= minimum && value <= maximum;
}
function traceBoundedNumber(value, minimum, maximum) {
    return typeof value === 'number' && Number.isFinite(value) && value >= minimum && value <= maximum;
}

function normalizeTraceDecision(value, expectedSequence) {
    if (!traceExactFields(value, TRACE_DECISION_FIELDS)
        || value.sequence !== expectedSequence
        || !traceBoundedInteger(value.elapsed_ms, 0, 86400000)
        || !TRACE_CATEGORIES.has(value.category)
        || !TRACE_ACTIONS.has(value.action)
        || !TRACE_RESULTS.has(value.result)
        || !TRACE_REASONS.has(value.reason)
        || !TRACE_DIMENSION_PATTERN.test(value.provider)
        || !TRACE_DIMENSION_PATTERN.test(value.model)
        || !traceBoundedInteger(value.attempt, 0, 32)
        || !(value.status_code === 0 || traceBoundedInteger(value.status_code, 100, 599))
        || !traceBoundedInteger(value.latency_ms, 0, 86400000)
        || !traceBoundedInteger(value.candidate_count, 0, 10000)
        || !['original_tokens', 'final_tokens', 'input_tokens', 'output_tokens', 'cached_tokens', 'reasoning_tokens'].every((field) => traceBoundedInteger(value[field], 0, 2000000000))
        || !traceBoundedNumber(value.cost_usd, 0, 1000000)) return null;
    return Object.freeze(Object.fromEntries(TRACE_DECISION_FIELDS.map((field) => [field, value[field]])));
}

function normalizeRequestTrace(value) {
    if (!traceExactFields(value, TRACE_FIELDS)
        || value.schema_version !== 1
        || !TRACE_ID_PATTERN.test(value.trace_id)
        || !TRACE_REQUEST_ID_PATTERN.test(value.request_id)
        || !TRACE_PROTOCOLS.has(value.protocol)
        || !Number.isFinite(Date.parse(value.started_at))
        || !Number.isFinite(Date.parse(value.completed_at))
        || Date.parse(value.completed_at) < Date.parse(value.started_at)
        || !TRACE_OUTCOMES.has(value.outcome)
        || !traceBoundedInteger(value.status_code, 100, 599)
        || !traceBoundedInteger(value.duration_ms, 0, 86400000)
        || !TRACE_DIMENSION_PATTERN.test(value.requested_model)
        || !TRACE_DIMENSION_PATTERN.test(value.selected_provider)
        || !['input_tokens', 'output_tokens', 'total_tokens'].every((field) => traceBoundedInteger(value[field], 0, 2000000000))
        || (value.total_tokens && value.total_tokens < value.input_tokens + value.output_tokens)
        || !traceBoundedNumber(value.cost_usd, 0, 1000000)
        || !Array.isArray(value.decisions)
        || value.decisions.length > 64
        || typeof value.decisions_truncated !== 'boolean') return null;
    const decisions = value.decisions.map((item, index) => normalizeTraceDecision(item, index + 1));
    if (decisions.some((item) => item === null)) return null;
    return Object.freeze({ ...Object.fromEntries(TRACE_FIELDS.filter((field) => field !== 'decisions').map((field) => [field, value[field]])), decisions: Object.freeze(decisions) });
}

function normalizeTracePage(payload) {
    if (!payload || typeof payload !== 'object' || !Array.isArray(payload.traces)
        || !traceBoundedInteger(payload.page_size, 1, 200)
        || payload.traces.length > payload.page_size
        || typeof payload.has_more !== 'boolean'
        || !(payload.next_cursor === null || (typeof payload.next_cursor === 'string' && payload.next_cursor.length >= 1 && payload.next_cursor.length <= 1024))
        || payload.has_more !== (payload.next_cursor !== null)) return null;
    const traces = payload.traces.map(normalizeRequestTrace);
    return traces.some((item) => item === null) ? null : { traces, nextCursor: payload.next_cursor };
}

function normalizeTraceRetention(payload) {
    const policy = payload?.policy;
    const days = payload?.bounds?.retention_days;
    const traces = payload?.bounds?.max_traces;
    if (days?.minimum !== 1 || days?.maximum !== 90
        || traces?.minimum !== 1000 || traces?.maximum !== 1000000
        || !traceBoundedInteger(policy?.retention_days, days.minimum, days.maximum)
        || !traceBoundedInteger(policy?.max_traces, traces.minimum, traces.maximum)) return null;
    return { policy: { retention_days: policy.retention_days, max_traces: policy.max_traces }, bounds: { retention_days: days, max_traces: traces } };
}

function readTraceFilters() {
    const protocol = traceElement('traceProtocol')?.value || '';
    const model = traceElement('traceModel')?.value.trim() || '';
    const filters = {
        protocols: protocol ? [protocol] : [], outcomes: [],
        providers: [], models: model ? [model] : [], request_id: '',
        started_after: '', started_before: '',
        page_size: Number(traceElement('tracePageSize')?.value || 25)
    };
    return typeof mergeActivityTraceFilters === 'function'
        ? mergeActivityTraceFilters(filters)
        : filters;
}

function traceFiltersAreValid(filters) {
    return filters.protocols.every((value) => TRACE_PROTOCOLS.has(value))
        && filters.outcomes.every((value) => TRACE_OUTCOMES.has(value))
        && filters.providers.every((value) => TRACE_DIMENSION_PATTERN.test(value) && value)
        && filters.models.every((value) => TRACE_DIMENSION_PATTERN.test(value) && value)
        && (!filters.request_id || TRACE_REQUEST_ID_PATTERN.test(filters.request_id))
        && [25, 50, 100, 200].includes(filters.page_size)
        && !(filters.started_after && filters.started_before && Date.parse(filters.started_after) > Date.parse(filters.started_before));
}

function buildTraceParams(filters, { includePaging = true } = {}) {
    const params = new URLSearchParams();
    for (const name of ['protocols', 'outcomes', 'providers', 'models']) {
        for (const value of filters[name]) params.append(name, value);
    }
    for (const name of ['request_id', 'started_after', 'started_before']) {
        if (filters[name]) params.set(name, filters[name]);
    }
    if (includePaging) {
        params.set('page_size', String(filters.page_size));
        if (TraceConsoleState.cursor) params.set('cursor', TraceConsoleState.cursor);
    }
    return params;
}

function persistTraceSafeFilters(filters) {
    try {
        localStorage.setItem(TRACE_SAFE_FILTER_STORAGE_KEY, JSON.stringify({ protocols: filters.protocols, page_size: filters.page_size }));
    } catch (_error) { /* Optional preference storage. */ }
}

function restoreTraceSafeFilters() {
    let stored;
    try { stored = JSON.parse(localStorage.getItem(TRACE_SAFE_FILTER_STORAGE_KEY) || 'null'); } catch (_error) { stored = null; }
    if (!stored || typeof stored !== 'object' || Array.isArray(stored)) return;
    const values = { traceProtocol: stored.protocols?.[0], tracePageSize: stored.page_size };
    for (const [id, value] of Object.entries(values)) if (traceElement(id) && value !== undefined) traceElement(id).value = String(value);
    if (!traceFiltersAreValid(readTraceFilters())) clearTraceFilters({ reload: false });
}

function setTraceStatus(key, variables = {}) { if (traceElement('traceStatus')) traceElement('traceStatus').textContent = key ? t(key, variables) : ''; }
function traceText(tag, className, value) { const node = document.createElement(tag); if (className) node.className = className; node.textContent = value; return node; }
function formatTraceDate(value) { try { return new Intl.DateTimeFormat(getActiveLocale(), { dateStyle: 'medium', timeStyle: 'medium' }).format(new Date(value)); } catch (_error) { return t('trace.unknown'); } }
function formatTraceCost(value) { return formatConsoleCurrency(value, {maximumFractionDigits: 6}); }

function renderTraces() {
    const list = traceElement('traceList');
    if (!list) return;
    list.replaceChildren();
    for (const trace of TraceConsoleState.traces) {
        const item = document.createElement('li');
        const card = document.createElement('article');
        card.className = 'trace-card';
        const primary = traceText('div', 'trace-card-primary', '');
        primary.append(traceText('code', 'trace-card-protocol', trace.protocol), traceText('time', '', formatTraceDate(trace.started_at)), traceText('span', `trace-outcome trace-outcome-${trace.outcome}`, trace.outcome));
        const route = [trace.selected_provider || t('trace.unknown'), trace.requested_model || t('trace.unknown')].join(' · ');
        const metadata = traceText('div', 'trace-card-meta', '');
        metadata.append(traceText('span', '', route), traceText('code', '', `${t('trace.request_id')}: ${trace.request_id}`), traceText('span', '', `${formatConsoleNumber(trace.duration_ms)} ms · ${formatConsoleNumber(trace.total_tokens)} ${t('trace.tokens_short')} · ${formatTraceCost(trace.cost_usd)}`));
        const button = traceText('button', 'btn btn-secondary btn-small', t('trace.details'));
        button.type = 'button'; button.dataset.uiAction = 'view-trace-detail'; button.dataset.traceId = trace.trace_id;
        card.append(primary, metadata, button); item.append(card); list.append(item);
    }
    if (!TraceConsoleState.traces.length && TraceConsoleState.loaded) list.append(traceText('li', 'trace-empty', t('trace.empty')));
    const pagination = traceElement('tracePreviousPage')?.closest('.trace-pagination');
    if (pagination) pagination.hidden = !TraceConsoleState.traces.length;
    if (traceElement('tracePreviousPage')) traceElement('tracePreviousPage').disabled = TraceConsoleState.loading || !TraceConsoleState.cursorStack.length;
    if (traceElement('traceNextPage')) traceElement('traceNextPage').disabled = TraceConsoleState.loading || !TraceConsoleState.nextCursor;
    if (traceElement('tracePageNumber')) traceElement('tracePageNumber').textContent = t('trace.page', { page: TraceConsoleState.cursorStack.length + 1 });
}

async function loadTraces() {
    TraceConsoleState.abortController?.abort();
    const requestId = ++TraceConsoleState.requestId;
    const controller = new AbortController();
    TraceConsoleState.abortController = controller; TraceConsoleState.loading = true;
    traceElement('traceList')?.setAttribute('aria-busy', 'true'); setTraceStatus('trace.loading'); renderTraces();
    try {
        const response = await fetch(`./api/traces?${buildTraceParams(TraceConsoleState.filters)}`, { signal: controller.signal });
        if (!response.ok) throw new Error('trace-request');
        const page = normalizeTracePage(await response.json());
        if (!page) throw new TypeError('trace-shape');
        if (requestId !== TraceConsoleState.requestId) return;
        TraceConsoleState.traces = page.traces; TraceConsoleState.nextCursor = page.nextCursor; TraceConsoleState.loaded = true; setTraceStatus('');
    } catch (_error) {
        if (requestId !== TraceConsoleState.requestId || controller.signal.aborted) return;
        TraceConsoleState.traces = []; TraceConsoleState.nextCursor = null; TraceConsoleState.loaded = true; setTraceStatus('trace.load_failed');
    } finally {
        if (requestId !== TraceConsoleState.requestId) return;
        TraceConsoleState.loading = false; TraceConsoleState.abortController = null; traceElement('traceList')?.setAttribute('aria-busy', 'false'); renderTraces();
    }
}

function renderTraceRetention() {
    if (!TraceConsoleState.retention) return;
    const { policy, bounds } = TraceConsoleState.retention;
    for (const [id, field] of [['traceRetentionDays', 'retention_days'], ['traceMaxTraces', 'max_traces']]) {
        const input = traceElement(id); if (!input) continue;
        input.value = String(policy[field]); input.min = String(bounds[field].minimum); input.max = String(bounds[field].maximum);
    }
}

async function loadTraceRetention() {
    try {
        const response = await fetch('./api/traces/retention'); if (!response.ok) throw new Error('trace-retention');
        const retention = normalizeTraceRetention(await response.json()); if (!retention) throw new TypeError('trace-retention-shape');
        TraceConsoleState.retention = retention; renderTraceRetention();
    } catch (_error) { if (traceElement('traceRetentionStatus')) traceElement('traceRetentionStatus').textContent = t('trace.load_failed'); }
}

async function loadTraceConsole(force = false) {
    if (!traceElement('activityTracesPanel')) return;
    if (!TraceConsoleState.loaded || force) { TraceConsoleState.filters = readTraceFilters(); await loadTraces(); }
    else renderTraces();
}

async function applyTraceFilters(event) {
    event?.preventDefault();
    if (!traceElement('traceFilterForm')?.reportValidity()) return;
    const filters = readTraceFilters(); if (!traceFiltersAreValid(filters)) { setTraceStatus('trace.invalid_range'); return; }
    TraceConsoleState.filters = filters; TraceConsoleState.cursor = null; TraceConsoleState.cursorStack = []; TraceConsoleState.nextCursor = null; persistTraceSafeFilters(filters); await loadTraces();
}

function clearTraceFilters({ reload = true } = {}) {
    traceElement('traceFilterForm')?.reset(); if (traceElement('tracePageSize')) traceElement('tracePageSize').value = '25';
    try { localStorage.removeItem(TRACE_SAFE_FILTER_STORAGE_KEY); } catch (_error) { /* Optional preference storage. */ }
    TraceConsoleState.filters = readTraceFilters(); TraceConsoleState.cursor = null; TraceConsoleState.cursorStack = []; TraceConsoleState.nextCursor = null; if (reload) void loadTraces();
}

function refreshTraceConsole() {
    TraceConsoleState.cursor = null; TraceConsoleState.cursorStack = []; TraceConsoleState.nextCursor = null;
    if (!TraceConsoleState.loaded) TraceConsoleState.filters = readTraceFilters();
    void loadTraces();
}

function changeTracePage(direction) {
    if (TraceConsoleState.loading) return;
    if (direction === 'next' && TraceConsoleState.nextCursor) { TraceConsoleState.cursorStack.push(TraceConsoleState.cursor); TraceConsoleState.cursor = TraceConsoleState.nextCursor; }
    else if (direction === 'previous' && TraceConsoleState.cursorStack.length) TraceConsoleState.cursor = TraceConsoleState.cursorStack.pop();
    else return;
    TraceConsoleState.nextCursor = null; void loadTraces();
}

function renderTraceDetail(trace) {
    const values = {
        traceDetailTitle: trace.trace_id, traceDetailStartedAt: formatTraceDate(trace.started_at), traceDetailDuration: `${formatConsoleNumber(trace.duration_ms)} ms`,
        traceDetailRequestId: trace.request_id, traceDetailProtocol: trace.protocol, traceDetailOutcome: trace.outcome, traceDetailStatusCode: String(trace.status_code),
        traceDetailModel: trace.requested_model || t('trace.unknown'), traceDetailProvider: trace.selected_provider || t('trace.unknown'),
        traceDetailTokens: `${formatConsoleNumber(trace.input_tokens)} / ${formatConsoleNumber(trace.output_tokens)} / ${formatConsoleNumber(trace.total_tokens)}`, traceDetailCost: formatTraceCost(trace.cost_usd), traceDecisionCount: formatConsoleNumber(trace.decisions.length)
    };
    for (const [id, value] of Object.entries(values)) if (traceElement(id)) traceElement(id).textContent = value;
    const list = traceElement('traceDecisionList'); list?.replaceChildren();
    for (const decision of trace.decisions) {
        const item = document.createElement('li'); item.className = 'trace-decision';
        item.append(traceText('span', 'trace-decision-sequence', String(decision.sequence)));
        const body = traceText('div', '', ''); const title = traceText('div', 'trace-decision-title', '');
        title.append(traceText('code', '', `${decision.category}.${decision.action}`), traceText('span', 'trace-decision-result', decision.result));
        const dimensions = [decision.reason, decision.provider, decision.model, decision.status_code ? `HTTP ${decision.status_code}` : '', decision.attempt ? `${t('trace.attempt')} ${decision.attempt}` : '', `${decision.elapsed_ms} ms`].filter(Boolean).join(' · ');
        body.append(title, traceText('div', 'trace-decision-meta', dimensions)); item.append(body); list?.append(item);
    }
    traceElement('traceDecisionTruncated')?.classList.toggle('hidden', !trace.decisions_truncated);
}

function clearTraceDetail() {
    for (const id of [
        'traceDetailTitle', 'traceDetailStartedAt', 'traceDetailDuration',
        'traceDetailRequestId', 'traceDetailProtocol', 'traceDetailOutcome',
        'traceDetailStatusCode', 'traceDetailModel', 'traceDetailProvider',
        'traceDetailTokens', 'traceDetailCost', 'traceDecisionCount'
    ]) if (traceElement(id)) traceElement(id).textContent = '';
    traceElement('traceDecisionList')?.replaceChildren();
    traceElement('traceDecisionTruncated')?.classList.add('hidden');
}

async function openTraceDetail(element) {
    const traceId = element.dataset.traceId; const dialog = traceElement('traceDetailDialog');
    if (!TRACE_ID_PATTERN.test(traceId || '') || !dialog) return;
    TraceConsoleState.detailAbortController?.abort();
    const detailRequestId = ++TraceConsoleState.detailRequestId;
    const controller = new AbortController();
    TraceConsoleState.detailAbortController = controller;
    TraceConsoleState.selectedTrace = null;
    clearTraceDetail();
    TraceConsoleState.detailReturnFocus = element; if (traceElement('traceDetailStatus')) traceElement('traceDetailStatus').textContent = t('trace.loading'); dialog.showModal();
    try {
        const response = await fetch(`./api/traces/${encodeURIComponent(traceId)}`, { signal: controller.signal }); if (!response.ok) throw new Error('trace-detail');
        const trace = normalizeRequestTrace(await response.json()); if (!trace) throw new TypeError('trace-detail-shape');
        if (detailRequestId !== TraceConsoleState.detailRequestId) return;
        TraceConsoleState.selectedTrace = trace; renderTraceDetail(trace); if (traceElement('traceDetailStatus')) traceElement('traceDetailStatus').textContent = '';
    } catch (_error) {
        if (detailRequestId === TraceConsoleState.detailRequestId && !controller.signal.aborted && traceElement('traceDetailStatus')) traceElement('traceDetailStatus').textContent = t('trace.detail_failed');
    } finally {
        if (detailRequestId === TraceConsoleState.detailRequestId) TraceConsoleState.detailAbortController = null;
    }
}

function closeTraceDetail() {
    TraceConsoleState.detailAbortController?.abort();
    TraceConsoleState.detailAbortController = null;
    TraceConsoleState.detailRequestId += 1;
    const dialog = traceElement('traceDetailDialog'); if (dialog?.open) dialog.close();
}
function pivotTraceRequest() {
    const trace = TraceConsoleState.selectedTrace;
    if (!trace) return;
    closeTraceDetail();
    investigateActivityRequest(trace.request_id, 'traces');
}
function openRelatedAuditRequest() {
    const trace = TraceConsoleState.selectedTrace;
    if (!trace) return;
    closeTraceDetail();
    investigateActivityRequest(trace.request_id, 'audit');
}
async function copyTraceRequest() {
    const status = traceElement('traceDetailStatus'); if (!TraceConsoleState.selectedTrace || !status) return;
    try { await navigator.clipboard.writeText(TraceConsoleState.selectedTrace.request_id); status.textContent = t('trace.copied'); } catch (_error) { status.textContent = t('trace.copy_failed'); }
}

function traceExportFilename(response, format) {
    const candidate = (response.headers.get('Content-Disposition') || '').match(/filename="?([^";]+)"?/i)?.[1] || '';
    if (TRACE_EXPORT_FILENAME_PATTERN.test(candidate)) return candidate;
    return `omni-traces-${new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z')}.${format}`;
}

async function exportTraces(format) {
    if (TraceConsoleState.exporting || !['jsonl', 'csv'].includes(format)) return;
    TraceConsoleState.exporting = true; document.querySelectorAll('[data-ui-action="export-traces"]').forEach((button) => { button.disabled = true; }); setTraceStatus('trace.exporting');
    try {
        if (!traceFiltersAreValid(TraceConsoleState.filters)) throw new TypeError('trace-export-filters');
        const params = buildTraceParams(TraceConsoleState.filters, { includePaging: false }); params.set('format', format);
        const response = await fetch(`./api/traces/export?${params}`); if (!response.ok) throw new Error('trace-export');
        const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement('a');
        link.href = url; link.download = traceExportFilename(response, format); link.hidden = true; document.body.append(link); link.click(); link.remove(); URL.revokeObjectURL(url); setTraceStatus('trace.exported');
    } catch (_error) { setTraceStatus('trace.export_failed'); }
    finally { TraceConsoleState.exporting = false; document.querySelectorAll('[data-ui-action="export-traces"]').forEach((button) => { button.disabled = false; }); }
}

async function saveTraceRetention(event) {
    event?.preventDefault(); const form = traceElement('traceRetentionForm'); if (!form?.reportValidity() || !TraceConsoleState.retention) return;
    const retentionDays = Number(traceElement('traceRetentionDays')?.value); const maxTraces = Number(traceElement('traceMaxTraces')?.value); const { bounds } = TraceConsoleState.retention;
    if (!traceBoundedInteger(retentionDays, bounds.retention_days.minimum, bounds.retention_days.maximum) || !traceBoundedInteger(maxTraces, bounds.max_traces.minimum, bounds.max_traces.maximum)) return;
    if (!await showConfirmModal(t('trace.retention_confirm', { days: retentionDays, maxTraces }), { title: t('trace.retention'), confirmLabel: t('trace.save_retention') })) return;
    const button = traceElement('traceSaveRetention'); const status = traceElement('traceRetentionStatus'); if (button) button.disabled = true;
    try {
        const response = await fetch('./api/traces/retention', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ retention_days: retentionDays, max_traces: maxTraces }) });
        if (!response.ok) throw new Error('trace-retention-update'); const payload = await response.json(); if (!traceBoundedInteger(payload?.removed_traces, 0, 1000000)) throw new TypeError('trace-retention-update-shape');
        await loadTraceRetention(); if (status) status.textContent = t('trace.retention_updated', { count: formatConsoleNumber(payload.removed_traces) }); TraceConsoleState.cursor = null; TraceConsoleState.cursorStack = []; if (TraceConsoleState.loaded) await loadTraces();
    } catch (_error) { if (status) status.textContent = t('trace.update_failed'); }
    finally { if (button) button.disabled = false; }
}

function initTraceBindings() {
    restoreTraceSafeFilters(); TraceConsoleState.filters = readTraceFilters(); traceElement('traceFilterForm')?.addEventListener('submit', applyTraceFilters); traceElement('traceRetentionForm')?.addEventListener('submit', saveTraceRetention);
    const dialog = traceElement('traceDetailDialog');
    dialog?.addEventListener('close', () => TraceConsoleState.detailReturnFocus?.focus());
    dialog?.addEventListener('cancel', (event) => { event.preventDefault(); closeTraceDetail(); });
    dialog?.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') { event.preventDefault(); closeTraceDetail(); }
    });
}
document.addEventListener('DOMContentLoaded', initTraceBindings);
document.addEventListener('omni:locale-change', () => { if (TraceConsoleState.loaded) { renderTraces(); if (TraceConsoleState.selectedTrace) renderTraceDetail(TraceConsoleState.selectedTrace); } });
