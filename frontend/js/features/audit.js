const AUDIT_SAFE_FILTER_STORAGE_KEY = 'polaris_audit_safe_filters_v1';
const AUDIT_PERSISTED_FILTERS = [
    'actions',
    'target_types',
    'page_size'
];
const AUDIT_EVENT_FIELDS = [
    'schema_version',
    'event_id',
    'occurred_at',
    'request_id',
    'actor_type',
    'actor_fingerprint',
    'action',
    'target_type',
    'target_fingerprint',
    'outcome',
    'change_codes'
];
const AUDIT_EXPORT_FILENAME_PATTERN = /^polaris-audit-\d{8}T\d{6}Z\.(?:jsonl|csv)$/;
const AUDIT_REQUEST_ID_PATTERN = /^[A-Za-z0-9._:-]{1,128}$/;
const AUDIT_FINGERPRINT_PATTERN = /^[0-9a-f]{20}$/;
const AUDIT_EVENT_ID_PATTERN = /^[0-9a-f]{32}$/;
const AUDIT_CURSOR_MAX_LENGTH = 4096;
const AUDIT_ACTIONS = new Set([
    'auth.login', 'auth.logout', 'auth.recovery', 'auth.setup', 'config.update', 'config.reset',
    'root_key.rotate', 'provider.create', 'provider.update', 'provider.delete',
    'credential.create', 'credential.update', 'credential.delete', 'credential.verify',
    'credential.test', 'credential.quota', 'credential.toggle', 'credential.export',
    'credential.credit_mode', 'credential.batch', 'credential.import',
    'credential.email_refresh', 'virtual_key.create', 'virtual_key.update',
    'virtual_key.rotate', 'virtual_key.revoke', 'quality_policy.update',
    'backup.create', 'backup.restore', 'backup.export', 'audit.retention_update',
    'audit.export', 'trace.retention_update', 'trace.export', 'model_blacklist.clear',
    'model_pool.update', 'logs.clear', 'identity.create', 'identity.update',
    'role_binding.update', 'session.revoke', 'oidc_policy.advance',
    'management.access_denied'
]);
const AUDIT_ACTOR_TYPES = new Set([
    'local_owner', 'oidc_user', 'panel_session', 'root_key', 'virtual_key', 'system'
]);
const AUDIT_TARGET_TYPES = new Set([
    'session', 'configuration', 'provider', 'credential', 'virtual_key',
    'quality_policy', 'backup', 'audit_policy', 'root_key', 'model_blacklist',
    'model_pool', 'log_store', 'trace_policy', 'identity', 'role_binding',
    'oidc_policy', 'management_route'
]);
const AUDIT_OUTCOMES = new Set([
    'succeeded', 'denied', 'failed', 'not_found', 'conflict', 'invalid',
    'timed_out', 'cancelled'
]);
const AUDIT_CHANGE_CODES = new Set([
    'created', 'updated', 'deleted', 'enabled', 'disabled', 'rotated', 'revoked',
    'verified', 'settings_changed', 'scopes_changed', 'limits_changed',
    'budget_changed', 'expiry_changed', 'models_changed', 'credentials_changed',
    'policy_changed', 'restored', 'exported', 'retention_changed', 'no_change'
]);

const AuditConsoleState = {
    events: [],
    filters: {},
    cursor: null,
    cursorStack: [],
    nextCursor: null,
    loaded: false,
    loading: false,
    loadError: false,
    eventRequestId: 0,
    eventAbortController: null,
    exporting: false,
    selectedEventId: null,
    detailReturnFocus: null,
    retention: null
};

function auditElement(id) {
    return document.getElementById(id);
}

function isAuditString(value, maximum = 128) {
    return typeof value === 'string' && value.length > 0 && value.length <= maximum;
}

function normalizeAuditEvent(record) {
    if (!record || typeof record !== 'object' || Array.isArray(record)) return null;
    const keys = Object.keys(record).sort();
    if (keys.length !== AUDIT_EVENT_FIELDS.length
        || !AUDIT_EVENT_FIELDS.every((field) => keys.includes(field))) return null;
    if (record.schema_version !== 1
        || !AUDIT_EVENT_ID_PATTERN.test(record.event_id)
        || !isAuditString(record.occurred_at, 64)
        || !Number.isFinite(Date.parse(record.occurred_at))
        || !AUDIT_REQUEST_ID_PATTERN.test(record.request_id)
        || !AUDIT_ACTOR_TYPES.has(record.actor_type)
        || !AUDIT_FINGERPRINT_PATTERN.test(record.actor_fingerprint)
        || !AUDIT_ACTIONS.has(record.action)
        || !AUDIT_TARGET_TYPES.has(record.target_type)
        || !AUDIT_FINGERPRINT_PATTERN.test(record.target_fingerprint)
        || !AUDIT_OUTCOMES.has(record.outcome)
        || !Array.isArray(record.change_codes)
        || record.change_codes.length < 1
        || record.change_codes.length > 16
        || !record.change_codes.every((code) => AUDIT_CHANGE_CODES.has(code))) return null;
    return Object.freeze(Object.fromEntries(AUDIT_EVENT_FIELDS.map((field) => [field, record[field]])));
}

function normalizeAuditPage(payload) {
    if (!payload || typeof payload !== 'object' || !Array.isArray(payload.events)) return null;
    if (!Number.isInteger(payload.page_size) || payload.page_size < 1 || payload.page_size > 200) return null;
    if (payload.events.length > payload.page_size) return null;
    if (typeof payload.has_more !== 'boolean') return null;
    if (payload.next_cursor !== null
        && (!isAuditString(payload.next_cursor, AUDIT_CURSOR_MAX_LENGTH))) return null;
    if (payload.has_more !== (payload.next_cursor !== null)) return null;
    const events = payload.events.map(normalizeAuditEvent);
    if (events.some((event) => event === null)) return null;
    return { events, nextCursor: payload.next_cursor };
}

function normalizeAuditRetention(payload) {
    const policy = payload?.policy;
    const bounds = payload?.bounds;
    const dayBounds = bounds?.retention_days;
    const eventBounds = bounds?.max_events;
    const validBound = (bound) => Number.isInteger(bound?.minimum)
        && Number.isInteger(bound?.maximum)
        && bound.minimum <= bound.maximum;
    if (!Number.isInteger(policy?.retention_days)
        || !Number.isInteger(policy?.max_events)
        || !validBound(dayBounds)
        || !validBound(eventBounds)
        || policy.retention_days < dayBounds.minimum
        || policy.retention_days > dayBounds.maximum
        || policy.max_events < eventBounds.minimum
        || policy.max_events > eventBounds.maximum) return null;
    return {
        policy: { retention_days: policy.retention_days, max_events: policy.max_events },
        bounds: {
            retention_days: { minimum: dayBounds.minimum, maximum: dayBounds.maximum },
            max_events: { minimum: eventBounds.minimum, maximum: eventBounds.maximum }
        }
    };
}

function readAuditFilters() {
    const action = auditElement('auditAction')?.value.trim() || '';
    const targetType = auditElement('auditTargetType')?.value || '';
    const actorFingerprint = auditElement('auditActorFingerprint')?.value.trim() || '';
    const targetFingerprint = auditElement('auditTargetFingerprint')?.value.trim() || '';
    const pageSize = Number(auditElement('auditPageSize')?.value || 25);
    const filters = {
        actions: action ? [action] : [],
        outcomes: [],
        actor_types: [],
        target_types: targetType ? [targetType] : [],
        request_id: '',
        actor_fingerprints: actorFingerprint ? [actorFingerprint] : [],
        target_fingerprints: targetFingerprint ? [targetFingerprint] : [],
        occurred_after: '',
        occurred_before: '',
        page_size: pageSize
    };
    return typeof mergeActivityAuditFilters === 'function'
        ? mergeActivityAuditFilters(filters)
        : filters;
}

function auditFiltersAreValid(filters) {
    if (filters.actions.some((value) => !AUDIT_ACTIONS.has(value))) return false;
    if (filters.outcomes.some((value) => !AUDIT_OUTCOMES.has(value))) return false;
    if (filters.actor_types.some((value) => !AUDIT_ACTOR_TYPES.has(value))) return false;
    if (filters.target_types.some((value) => !AUDIT_TARGET_TYPES.has(value))) return false;
    if (filters.request_id && !AUDIT_REQUEST_ID_PATTERN.test(filters.request_id)) return false;
    if (filters.actor_fingerprints.some((value) => !AUDIT_FINGERPRINT_PATTERN.test(value))) return false;
    if (filters.target_fingerprints.some((value) => !AUDIT_FINGERPRINT_PATTERN.test(value))) return false;
    if (![25, 50, 100, 200].includes(filters.page_size)) return false;
    if (filters.occurred_after && filters.occurred_before
        && Date.parse(filters.occurred_after) > Date.parse(filters.occurred_before)) return false;
    return true;
}

function buildAuditParams(filters, { includePaging = true } = {}) {
    const params = new URLSearchParams();
    for (const name of [
        'actor_types', 'actor_fingerprints', 'actions', 'target_types',
        'target_fingerprints', 'outcomes'
    ]) {
        for (const value of filters[name] || []) params.append(name, value);
    }
    for (const name of ['request_id', 'occurred_after', 'occurred_before']) {
        if (filters[name]) params.set(name, filters[name]);
    }
    if (includePaging) {
        params.set('page_size', String(filters.page_size));
        if (AuditConsoleState.cursor) params.set('cursor', AuditConsoleState.cursor);
    }
    return params;
}

function persistAuditSafeFilters(filters) {
    const safe = Object.fromEntries(AUDIT_PERSISTED_FILTERS.map((name) => [name, filters[name]]));
    try {
        localStorage.setItem(AUDIT_SAFE_FILTER_STORAGE_KEY, JSON.stringify(safe));
    } catch (_error) {
        // Storage is optional; filters remain functional for the current page.
    }
}

function restoreAuditSafeFilters() {
    let stored = null;
    try {
        stored = JSON.parse(localStorage.getItem(AUDIT_SAFE_FILTER_STORAGE_KEY) || 'null');
    } catch (_error) {
        stored = null;
    }
    if (!stored || typeof stored !== 'object' || Array.isArray(stored)) return;
    const values = {
        auditAction: Array.isArray(stored.actions) ? stored.actions[0] : '',
        auditTargetType: Array.isArray(stored.target_types) ? stored.target_types[0] : '',
        auditPageSize: stored.page_size
    };
    for (const [id, value] of Object.entries(values)) {
        const element = auditElement(id);
        if (element && (typeof value === 'string' || Number.isInteger(value))) {
            element.value = String(value);
        }
    }
    const filters = readAuditFilters();
    if (!auditFiltersAreValid(filters)) clearAuditFilters({ reload: false });
}

function setAuditStatus(key, variables = {}) {
    const status = auditElement('auditEventStatus');
    if (status) status.textContent = key ? t(key, variables) : '';
}

function formatAuditDate(value) {
    try {
        return new Intl.DateTimeFormat(getActiveLocale(), {
            dateStyle: 'medium',
            timeStyle: 'medium'
        }).format(new Date(value));
    } catch (_error) {
        return t('audit.unknown');
    }
}

function createAuditText(tagName, className, value) {
    const element = document.createElement(tagName);
    if (className) element.className = className;
    element.textContent = value;
    return element;
}

function renderAuditEvents() {
    const list = auditElement('auditEventList');
    if (!list) return;
    list.replaceChildren();
    for (const event of AuditConsoleState.events) {
        const item = document.createElement('li');
        const card = document.createElement('article');
        card.className = 'audit-event-card';

        const primary = document.createElement('div');
        primary.className = 'audit-event-primary';
        primary.append(
            createAuditText('code', 'audit-event-action', event.action),
            createAuditText('time', 'audit-event-time', formatAuditDate(event.occurred_at)),
            createAuditText('span', `audit-outcome audit-outcome-${event.outcome}`, event.outcome)
        );

        const metadata = document.createElement('div');
        metadata.className = 'audit-event-meta';
        metadata.append(
            createAuditText('span', 'audit-event-target', `${t('audit.target_type')}: ${event.target_type}`),
            createAuditText('code', 'audit-event-request', `${t('audit.request_id')}: ${event.request_id}`)
        );

        const button = createAuditText('button', 'btn btn-secondary btn-small', t('audit.details'));
        button.type = 'button';
        button.dataset.uiAction = 'view-audit-detail';
        button.dataset.eventId = event.event_id;
        card.append(primary, metadata, button);
        item.append(card);
        list.append(item);
    }
    if (!AuditConsoleState.events.length && AuditConsoleState.loaded && !AuditConsoleState.loading && !AuditConsoleState.loadError) {
        const item = createAuditText('li', 'audit-empty-state', t('audit.empty'));
        list.append(item);
    }
    const pagination = auditElement('auditPreviousPage')?.closest('.audit-pagination');
    if (pagination) pagination.hidden = !AuditConsoleState.events.length && !AuditConsoleState.cursorStack.length;
    const previous = auditElement('auditPreviousPage');
    const next = auditElement('auditNextPage');
    if (previous) previous.disabled = AuditConsoleState.loading || !AuditConsoleState.cursorStack.length;
    if (next) next.disabled = AuditConsoleState.loading || !AuditConsoleState.nextCursor;
    const page = auditElement('auditPageNumber');
    if (page) page.textContent = t('audit.page', { page: AuditConsoleState.cursorStack.length + 1 });
}

async function loadAuditEvents() {
    AuditConsoleState.eventAbortController?.abort();
    const requestId = ++AuditConsoleState.eventRequestId;
    const controller = new AbortController();
    AuditConsoleState.eventAbortController = controller;
    AuditConsoleState.loading = true;
    AuditConsoleState.loadError = false;
    const list = auditElement('auditEventList');
    setAuditStatus('audit.loading');
    renderAuditEvents();
    setRegionBusy(list, true);
    try {
        const params = buildAuditParams(AuditConsoleState.filters);
        const response = await fetch(`./api/audit/events?${params.toString()}`, {
            signal: controller.signal
        });
        if (!response.ok) throw new Error('audit-events-request');
        const page = normalizeAuditPage(await response.json());
        if (!page) throw new TypeError('audit-events-shape');
        if (requestId !== AuditConsoleState.eventRequestId) return;
        AuditConsoleState.events = page.events;
        AuditConsoleState.nextCursor = page.nextCursor;
        AuditConsoleState.loaded = true;
        setAuditStatus('');
    } catch (_error) {
        if (requestId !== AuditConsoleState.eventRequestId) return;
        AuditConsoleState.loadError = true;
        AuditConsoleState.events = [];
        AuditConsoleState.nextCursor = null;
        AuditConsoleState.loaded = true;
        setAuditStatus('audit.load_failed');
    } finally {
        if (requestId !== AuditConsoleState.eventRequestId) return;
        AuditConsoleState.loading = false;
        AuditConsoleState.eventAbortController = null;
        setRegionBusy(list, false);
        renderAuditEvents();
    }
}

function renderAuditRetention() {
    if (!AuditConsoleState.retention) return;
    const { policy, bounds } = AuditConsoleState.retention;
    const days = auditElement('auditRetentionDays');
    const events = auditElement('auditMaxEvents');
    if (days) {
        days.value = String(policy.retention_days);
        days.min = String(bounds.retention_days.minimum);
        days.max = String(bounds.retention_days.maximum);
    }
    if (events) {
        events.value = String(policy.max_events);
        events.min = String(bounds.max_events.minimum);
        events.max = String(bounds.max_events.maximum);
    }
}

async function loadAuditRetention() {
    try {
        const response = await fetch('./api/audit/retention');
        if (!response.ok) throw new Error('audit-retention-request');
        const retention = normalizeAuditRetention(await response.json());
        if (!retention) throw new TypeError('audit-retention-shape');
        AuditConsoleState.retention = retention;
        renderAuditRetention();
    } catch (_error) {
        const status = auditElement('auditRetentionStatus');
        if (status) status.textContent = t('audit.load_failed');
    }
}

async function loadAuditConsole(force = false) {
    if (!auditElement('activityAuditPanel')) return;
    if (!AuditConsoleState.loaded || force) {
        AuditConsoleState.filters = readAuditFilters();
        await loadAuditEvents();
    } else {
        renderAuditEvents();
    }
}

async function applyAuditFilters(event) {
    event?.preventDefault();
    const form = auditElement('auditFilterForm');
    if (!form?.reportValidity()) return;
    const filters = readAuditFilters();
    if (!auditFiltersAreValid(filters)) {
        setAuditStatus('audit.invalid_range');
        return;
    }
    AuditConsoleState.filters = filters;
    AuditConsoleState.cursor = null;
    AuditConsoleState.cursorStack = [];
    AuditConsoleState.nextCursor = null;
    persistAuditSafeFilters(filters);
    await loadAuditEvents();
}

function clearAuditFilters({ reload = true } = {}) {
    auditElement('auditFilterForm')?.reset();
    const pageSize = auditElement('auditPageSize');
    if (pageSize) pageSize.value = '25';
    try {
        localStorage.removeItem(AUDIT_SAFE_FILTER_STORAGE_KEY);
    } catch (_error) {
        // Storage is optional.
    }
    AuditConsoleState.filters = readAuditFilters();
    AuditConsoleState.cursor = null;
    AuditConsoleState.cursorStack = [];
    AuditConsoleState.nextCursor = null;
    if (reload) void loadAuditEvents();
}

function refreshAuditConsole() {
    AuditConsoleState.cursor = null;
    AuditConsoleState.cursorStack = [];
    AuditConsoleState.nextCursor = null;
    if (!AuditConsoleState.loaded) AuditConsoleState.filters = readAuditFilters();
    void Promise.all([loadAuditEvents(), loadAuditRetention()]);
}

function changeAuditPage(direction) {
    if (AuditConsoleState.loading) return;
    if (direction === 'next' && AuditConsoleState.nextCursor) {
        AuditConsoleState.cursorStack.push(AuditConsoleState.cursor);
        AuditConsoleState.cursor = AuditConsoleState.nextCursor;
    } else if (direction === 'previous' && AuditConsoleState.cursorStack.length) {
        AuditConsoleState.cursor = AuditConsoleState.cursorStack.pop();
    } else {
        return;
    }
    AuditConsoleState.nextCursor = null;
    void loadAuditEvents();
}

function openAuditDetail(element) {
    const event = AuditConsoleState.events.find((item) => item.event_id === element.dataset.eventId);
    const dialog = auditElement('auditDetailDialog');
    if (!event || !dialog) return;
    AuditConsoleState.selectedEventId = event.event_id;
    AuditConsoleState.detailReturnFocus = element;
    const values = {
        auditDetailOccurredAt: formatAuditDate(event.occurred_at),
        auditDetailEventId: event.event_id,
        auditDetailRequestId: event.request_id,
        auditDetailAction: event.action,
        auditDetailOutcome: event.outcome,
        auditDetailActorType: event.actor_type,
        auditDetailActorFingerprint: event.actor_fingerprint,
        auditDetailTargetType: event.target_type,
        auditDetailTargetFingerprint: event.target_fingerprint,
        auditDetailChangeCodes: event.change_codes.join(', ')
    };
    for (const [id, value] of Object.entries(values)) {
        const field = auditElement(id);
        if (field) field.textContent = value;
    }
    const status = auditElement('auditDetailStatus');
    if (status) status.textContent = '';
    dialog.showModal();
}

function closeAuditDetail() {
    const dialog = auditElement('auditDetailDialog');
    if (dialog?.open) dialog.close();
    AuditConsoleState.detailReturnFocus?.focus();
}

function selectedAuditEvent() {
    return AuditConsoleState.events.find((item) => item.event_id === AuditConsoleState.selectedEventId);
}

function pivotAuditRequest() {
    const event = selectedAuditEvent();
    if (!event) return;
    closeAuditDetail();
    investigateActivityRequest(event.request_id, 'audit');
}

function openRelatedTraceRequest() {
    const event = selectedAuditEvent();
    if (!event) return;
    closeAuditDetail();
    investigateActivityRequest(event.request_id, 'traces');
}

async function copyAuditRequest() {
    const event = selectedAuditEvent();
    const status = auditElement('auditDetailStatus');
    if (!event || !status) return;
    try {
        await navigator.clipboard.writeText(event.request_id);
        status.textContent = t('audit.copied');
    } catch (_error) {
        status.textContent = t('audit.copy_failed');
    }
}

function auditExportFilename(response, format) {
    const disposition = response.headers.get('Content-Disposition') || '';
    const candidate = disposition.match(/filename="?([^";]+)"?/i)?.[1] || '';
    if (AUDIT_EXPORT_FILENAME_PATTERN.test(candidate)) return candidate;
    const timestamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
    return `polaris-audit-${timestamp}.${format}`;
}

async function exportAuditEvents(format) {
    if (AuditConsoleState.exporting || !['jsonl', 'csv'].includes(format)) return;
    AuditConsoleState.exporting = true;
    document.querySelectorAll('[data-ui-action="export-audit"]').forEach((button) => {
        button.disabled = true;
    });
    setAuditStatus('audit.exporting');
    try {
        const filters = AuditConsoleState.filters;
        if (!auditFiltersAreValid(filters)) throw new TypeError('audit-export-filters');
        const params = buildAuditParams(filters, { includePaging: false });
        params.set('format', format);
        const response = await fetch(`./api/audit/export?${params.toString()}`);
        if (!response.ok) throw new Error('audit-export-request');
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = auditExportFilename(response, format);
        link.hidden = true;
        document.body.append(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        setAuditStatus('audit.exported');
    } catch (_error) {
        setAuditStatus('audit.export_failed');
    } finally {
        AuditConsoleState.exporting = false;
        document.querySelectorAll('[data-ui-action="export-audit"]').forEach((button) => {
            button.disabled = false;
        });
    }
}

async function saveAuditRetention(event) {
    event?.preventDefault();
    const form = auditElement('auditRetentionForm');
    if (!form?.reportValidity() || !AuditConsoleState.retention) return;
    const retentionDays = Number(auditElement('auditRetentionDays')?.value);
    const maxEvents = Number(auditElement('auditMaxEvents')?.value);
    const { bounds } = AuditConsoleState.retention;
    if (!Number.isInteger(retentionDays)
        || retentionDays < bounds.retention_days.minimum
        || retentionDays > bounds.retention_days.maximum
        || !Number.isInteger(maxEvents)
        || maxEvents < bounds.max_events.minimum
        || maxEvents > bounds.max_events.maximum) return;
    const confirmed = await showConfirmModal(
        t('audit.retention_confirm', { days: retentionDays, maxEvents }),
        {
            title: t('audit.retention'),
            confirmLabel: t('audit.save_retention')
        }
    );
    if (!confirmed) return;
    const button = auditElement('auditSaveRetention');
    const status = auditElement('auditRetentionStatus');
    if (button) button.disabled = true;
    try {
        const response = await fetch('./api/audit/retention', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ retention_days: retentionDays, max_events: maxEvents })
        });
        if (!response.ok) throw new Error('audit-retention-update');
        const payload = await response.json();
        if (!Number.isInteger(payload?.removed_events) || payload.removed_events < 0) {
            throw new TypeError('audit-retention-update-shape');
        }
        await loadAuditRetention();
        if (status) status.textContent = t('audit.retention_updated', { count: formatConsoleNumber(payload.removed_events) });
        AuditConsoleState.cursor = null;
        AuditConsoleState.cursorStack = [];
        if (AuditConsoleState.loaded) await loadAuditEvents();
    } catch (_error) {
        if (status) status.textContent = t('audit.update_failed');
    } finally {
        if (button) button.disabled = false;
    }
}

function initAuditBindings() {
    restoreAuditSafeFilters();
    AuditConsoleState.filters = readAuditFilters();
    auditElement('auditFilterForm')?.addEventListener('submit', applyAuditFilters);
    auditElement('auditRetentionForm')?.addEventListener('submit', saveAuditRetention);
    auditElement('auditDetailDialog')?.addEventListener('close', () => {
        AuditConsoleState.detailReturnFocus?.focus();
    });
}

document.addEventListener('DOMContentLoaded', initAuditBindings);
document.addEventListener('polaris:locale-change', () => {
    if (AuditConsoleState.loaded) renderAuditEvents();
});
