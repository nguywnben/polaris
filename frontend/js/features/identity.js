function identityElement(tagName, className = '', text = '') {
    const element = document.createElement(tagName);
    if (className) element.className = className;
    if (text !== '') element.textContent = String(text);
    return element;
}

function identitySetStatus(elementId, message = '', type = '') {
    const element = document.getElementById(elementId);
    if (!element) return;
    element.textContent = message;
    element.classList.toggle('identity-status-error', type === 'error');
    element.classList.toggle('identity-status-warning', type === 'warning');
    element.classList.toggle('identity-status-success', type === 'success');
}

function identitySetBusy(elementId, busy) {
    const region = document.getElementById(elementId);
    const labels = {
        identityPrincipalSummary: ['identity.identity_id', 'identity.principal_type', 'identity.role',
            'identity.role_source', 'identity.authentication', 'identity.permissions'],
        identityOidcSummary: ['identity.status', 'identity.issuer', 'identity.redirect_uri', 'identity.scopes',
            'identity.role_mappings', 'identity.authorization_epoch', 'identity.configuration_revision', 'identity.client_credential'],
        identityRecoverySummary: ['identity.local_owner', 'identity.password', 'identity.ingress_policy']
    }[elementId];
    if (busy && region && !region.childElementCount && labels) {
        for (const label of labels) {
            const fact = identityFact(label, '');
            fact.className = 'region-skeleton identity-fact-skeleton';
            const line = identityElement('span', 'skeleton-line');
            line.setAttribute('aria-hidden', 'true');
            fact.lastElementChild.append(line);
            if (label === 'identity.permissions') {
                fact.classList.add('identity-permission-fact');
                fact.firstElementChild.className = 'visually-hidden';
            }
            region.append(fact);
        }
    }
    setRegionBusy(elementId, Boolean(busy));
}

function identitySetRefreshBusy(busy) {
    const button = document.getElementById('identityRefreshButton');
    if (!button) return;
    button.disabled = busy;
    button.setAttribute('aria-busy', String(busy));
}

function identityFocus(selector, fallbackId) {
    const target = document.querySelector(selector) || document.getElementById(fallbackId);
    if (!(target instanceof HTMLElement)) return;
    if (!target.matches('button, input, select, textarea, a[href], [tabindex]')) {
        target.setAttribute('tabindex', '-1');
    }
    target.focus();
}

function resetIdentityConsoleState() {
    const confirmResolver = IdentityConsoleState.confirmResolver;
    const confirmDialog = document.getElementById('identityConfirmDialog');
    const createDialog = document.getElementById('identityCreateDialog');
    if (confirmDialog?.open) confirmDialog.close();
    if (createDialog?.open) createDialog.close();
    if (confirmResolver) confirmResolver(false);
    identityResetState();
    identitySetRefreshBusy(false);
    if (AppState.tabLoadTimes) delete AppState.tabLoadTimes.identity;
    for (const elementId of (
        ['identityPrincipalSummary', 'identityOidcSummary', 'identityRecoverySummary',
            'identityList', 'identitySessionList']
    )) {
        document.getElementById(elementId)?.replaceChildren();
    }
    for (const statusId of (
        ['identityPageStatus', 'identityListStatus', 'identitySessionStatus', 'identityCreateStatus']
    )) {
        identitySetStatus(statusId);
    }
    document.getElementById('identityCreateButton')?.classList.add('hidden');
    document.getElementById('identityOidcAdvance')?.classList.add('hidden');
}

function identitySignOut(messageKey = 'identity.current_session_revoked') {
    resetIdentityConsoleState();
    AppState.authenticated = false;
    navigate('/login', false);
    showStatus(t(messageKey), 'info');
}

function identityErrorMessage(error, fallbackKey) {
    if (error?.status === 403) return t('identity.permission_denied');
    if (error?.status === 409) return t('identity.stale_revision');
    if (error?.status === 404) return t('identity.not_found');
    return t(fallbackKey);
}

function identityLoadIsCurrent(generation, signal = null) {
    return generation === IdentityConsoleState.generation && signal?.aborted !== true;
}

async function identityApi(path, options = {}) {
    const hasBody = options.body !== undefined;
    const response = await fetch(`./api/identity${path}`, {
        ...options,
        headers: {
            ...getAuthHeaders(hasBody),
            ...(options.headers || {})
        }
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
        if (response.status === 401) {
            identitySignOut('authentication_failed_please_log_in');
        }
        const error = new Error('identity_request_failed');
        error.status = response.status;
        throw error;
    }
    return payload;
}

function identityFact(labelKey, value, { technical = false } = {}) {
    const row = identityElement('div');
    row.appendChild(identityElement('dt', '', t(labelKey)));
    const output = identityElement('dd', technical ? 'identity-technical-value' : '', value);
    row.appendChild(output);
    return row;
}

function identityBooleanLabel(value) {
    return t(value ? 'identity.yes' : 'identity.no');
}

function identityRoleLabel(role) {
    return IDENTITY_ROLES.includes(role) ? role : t('identity.unknown');
}

function identityProtocolLabel(value) {
    return identitySafeText(value, 64) || t('identity.unknown');
}

function identityStatusBadge(elementId, key, variant) {
    const badge = document.getElementById(elementId);
    if (!badge) return;
    badge.className = `status-badge ${variant}`;
    badge.textContent = t(key);
}

function identityFormatDate(value) {
    const numeric = typeof value === 'number' ? value * 1000 : Date.parse(value);
    if (!Number.isFinite(numeric)) return t('identity.unknown');
    return new Intl.DateTimeFormat(getActiveLocale(), {
        dateStyle: 'medium',
        timeStyle: 'short'
    }).format(new Date(numeric));
}

function renderIdentityPrincipal() {
    const container = document.getElementById('identityPrincipalSummary');
    if (!container || !IdentityConsoleState.principal) return;
    const principal = IdentityConsoleState.principal;
    const previousPermissions = container.querySelector('.identity-permissions');
    const restorePermissionFocus = previousPermissions?.contains(document.activeElement);
    const permissionFact = identityFact('identity.permissions', '');
    permissionFact.className = 'identity-permission-fact';
    permissionFact.children[0].className = 'visually-hidden';
    const permissions = identityElement('details', 'identity-permissions');
    permissions.open = previousPermissions?.open === true;
    permissions.appendChild(identityElement('summary', '', t('identity.permissions')));
    permissionFact.children[1].appendChild(permissions);
    if (principal.permissions.length) {
        const list = identityElement('ul', 'identity-permission-list');
        for (const permission of principal.permissions) {
            list.appendChild(identityElement('li', 'identity-technical-value', permission));
        }
        permissions.appendChild(list);
    } else {
        permissions.appendChild(identityElement('p', '', t('identity.none')));
    }
    container.replaceChildren(
        identityFact('identity.identity_id', principal.identityId, { technical: true }),
        identityFact('identity.principal_type', identityProtocolLabel(principal.principalType), { technical: true }),
        identityFact('identity.role', identityRoleLabel(principal.role)),
        identityFact('identity.role_source', identityProtocolLabel(principal.roleSource), { technical: true }),
        identityFact('identity.authentication', identityProtocolLabel(principal.authenticationContext), { technical: true }),
        permissionFact
    );
    if (restorePermissionFocus) permissions.querySelector('summary').focus({ preventScroll: true });
    container.setAttribute('aria-busy', 'false');
    identityStatusBadge('identityPrincipalBadge', 'identity.authorized', 'success');
}

function renderIdentityModeNotice() {
    const notice = document.getElementById('identityModeNotice');
    if (!notice) return;
    const readiness = IdentityConsoleState.oidcPolicy?.readiness;
    const key = readiness === 'ready'
        ? 'identity.mode_ready'
        : readiness === 'disabled'
            ? 'identity.mode_disabled'
            : readiness === 'invalid'
                ? 'identity.mode_invalid'
                : 'identity.mode_unavailable';
    notice.textContent = t(key);
    notice.dataset.readiness = readiness || 'unavailable';
}

function renderIdentityOidc() {
    const container = document.getElementById('identityOidcSummary');
    const policy = IdentityConsoleState.oidcPolicy;
    const advanceButton = document.getElementById('identityOidcAdvance');
    advanceButton?.classList.toggle(
        'hidden', !policy || policy.readiness !== 'ready' || !identityCan('oidc.manage')
    );
    renderIdentityModeNotice();
    if (!container) return;
    if (!policy) {
        container.replaceChildren();
        container.setAttribute('aria-busy', 'false');
        identityStatusBadge('identityOidcBadge', identityCan('identity.read')
            ? 'identity.unavailable'
            : 'identity.not_authorized', 'muted');
        return;
    }
    const readiness = policy.readiness;
    container.replaceChildren(
        identityFact('identity.status', readiness, { technical: true }),
        identityFact('identity.issuer', identitySafeText(policy.issuer) || t('identity.not_configured'), { technical: true }),
        identityFact('identity.redirect_uri', identitySafeText(policy.redirect_uri) || t('identity.not_configured'), { technical: true }),
        identityFact('identity.scopes', Array.isArray(policy.scopes) && policy.scopes.length
            ? policy.scopes.map((scope) => identitySafeText(scope, 64)).join(', ')
            : t('identity.none'), { technical: true }),
        identityFact('identity.role_mappings', String(Number(policy.role_mapping_count) || 0)),
        identityFact('identity.authorization_epoch', String(Number(policy.authorization_epoch) || 0)),
        identityFact('identity.configuration_revision', String(Number(policy.revision) || 0)),
        identityFact('identity.client_credential', identityBooleanLabel(policy.secret_configured === true))
    );
    container.setAttribute('aria-busy', 'false');
    identityStatusBadge(
        'identityOidcBadge',
        readiness === 'ready' ? 'identity.ready' : readiness === 'disabled' ? 'identity.disabled' : 'identity.invalid',
        readiness === 'ready' ? 'success' : readiness === 'invalid' ? 'danger' : 'muted'
    );
}

function renderIdentityRecovery() {
    const container = document.getElementById('identityRecoverySummary');
    const recovery = IdentityConsoleState.recovery;
    if (!container) return;
    if (!recovery) {
        container.replaceChildren();
        container.setAttribute('aria-busy', 'false');
        identityStatusBadge('identityRecoveryBadge', identityCan('recovery.manage')
            ? 'identity.unavailable'
            : 'identity.not_authorized', 'muted');
        return;
    }
    const ingress = recovery.ingress_policy === 'direct_loopback_only'
        ? 'direct_loopback_only'
        : 'network_reachable';
    container.replaceChildren(
        identityFact('identity.local_owner', identityBooleanLabel(recovery.local_owner_enabled === true)),
        identityFact('identity.password', identityBooleanLabel(recovery.password_configured === true)),
        identityFact('identity.ingress_policy', ingress, { technical: true })
    );
    container.setAttribute('aria-busy', 'false');
    identityStatusBadge(
        'identityRecoveryBadge',
        recovery.ready === true ? 'identity.ready' : 'identity.not_ready',
        recovery.ready === true ? 'success' : 'danger'
    );
}

function identityRoleSelect(record, editable) {
    const select = identityElement('select', 'identity-role-select');
    select.setAttribute('aria-label', `${t('identity.role')}: ${record.identityId}`);
    select.dataset.identityRole = record.identityId;
    const draftRole = IdentityConsoleState.roleDrafts.get(record.identityId);
    const selectedRole = IDENTITY_ROLES.includes(draftRole) ? draftRole : record.role;
    for (const role of IDENTITY_ROLES) {
        if (role === 'owner' && !identityCan('owners.manage') && record.role !== 'owner') continue;
        const option = identityElement('option', '', identityRoleLabel(role));
        option.value = role;
        option.selected = role === selectedRole;
        select.appendChild(option);
    }
    select.disabled = !editable;
    return select;
}

function renderIdentityRecord(record) {
    const article = identityElement('article', 'identity-record');
    article.setAttribute('role', 'listitem');
    article.dataset.identityId = record.identityId;

    const heading = identityElement('div', 'identity-record-heading');
    const title = identityElement('div', 'identity-record-title');
    title.appendChild(identityElement(
        'strong', '', record.subject || t('identity.local_owner_identity')
    ));
    title.appendChild(identityElement('code', '', record.identityId));
    heading.appendChild(title);
    const enabled = identityElement(
        'span', `status-badge ${record.enabled ? 'success' : 'muted'}`,
        t(record.enabled ? 'identity.enabled' : 'identity.disabled')
    );
    heading.appendChild(enabled);
    article.appendChild(heading);

    const facts = identityElement('dl', 'identity-record-facts');
    facts.append(
        identityFact('identity.issuer', record.issuer || t('identity.local'), { technical: true }),
        identityFact('identity.subject', record.subject || t('identity.local'), { technical: true }),
        identityFact('identity.role_source', identityProtocolLabel(record.roleSource), { technical: true }),
        identityFact('identity.updated_at', identityFormatDate(record.updatedAt)),
        identityFact('identity.identity_revision', String(record.revision)),
        identityFact('identity.binding_revision', String(record.bindingRevision))
    );
    article.appendChild(facts);

    const mutable = record.identityId !== 'local-owner';
    const ownerAllowed = record.role !== 'owner' || identityCan('owners.manage');
    const editable = mutable && ownerAllowed && identityCan('identity.manage');
    if (!editable) {
        facts.appendChild(identityFact('identity.role', identityRoleLabel(record.role)));
        return article;
    }
    const actions = identityElement('div', 'identity-record-actions');
    const roleSelect = identityRoleSelect(record, editable);
    actions.appendChild(roleSelect);
    const saveRole = identityElement('button', 'btn btn-secondary btn-small', t('identity.save_role'));
    saveRole.type = 'button';
    saveRole.dataset.uiAction = 'identity-role';
    saveRole.dataset.identityId = record.identityId;
    saveRole.disabled = !editable;
    actions.appendChild(saveRole);
    const toggle = identityElement(
        'button', `btn btn-small ${record.enabled ? 'btn-danger' : 'btn-secondary'}`,
        t(record.enabled ? 'identity.disable' : 'identity.enable')
    );
    toggle.type = 'button';
    toggle.dataset.uiAction = 'identity-toggle';
    toggle.dataset.identityId = record.identityId;
    toggle.disabled = !editable;
    actions.appendChild(toggle);
    article.appendChild(actions);
    return article;
}

function renderIdentityList() {
    const list = document.getElementById('identityList');
    if (!list) return;
    list.replaceChildren(...IdentityConsoleState.identities.map(renderIdentityRecord));
    if (!IdentityConsoleState.identities.length) {
        list.appendChild(identityElement('p', 'identity-empty-state', t('identity.no_identities')));
    }
    list.setAttribute('aria-busy', 'false');
    const createButton = document.getElementById('identityCreateButton');
    createButton?.classList.toggle('hidden', !identityCan('identity.manage'));
    renderIdentityPagination();
}

function renderIdentityPagination() {
    const busy = IdentityConsoleState.identityPageLoading;
    const pagination = document.getElementById('identityPreviousPage')?.closest('.identity-pagination');
    if (pagination) pagination.hidden = !IdentityConsoleState.identityCursorStack.length
        && !IdentityConsoleState.identityNextCursor;
    document.getElementById('identityPreviousPage').disabled =
        busy || IdentityConsoleState.identityCursorStack.length === 0;
    document.getElementById('identityNextPage').disabled =
        busy || !IdentityConsoleState.identityNextCursor;
    document.getElementById('identityPageNumber').textContent = t(
        'identity.page', { page: IdentityConsoleState.identityPage }
    );
}

function renderIdentitySession(record) {
    const article = identityElement('article', 'identity-record');
    article.setAttribute('role', 'listitem');
    article.dataset.sessionReference = record.reference;
    const heading = identityElement('div', 'identity-record-heading');
    const title = identityElement('div', 'identity-record-title');
    title.appendChild(identityElement('strong', '', record.identityId));
    title.appendChild(identityElement('code', '', record.reference));
    heading.appendChild(title);
    if (record.current) {
        heading.appendChild(identityElement('span', 'status-badge info', t('identity.current')));
    }
    article.appendChild(heading);
    const facts = identityElement('dl', 'identity-record-facts');
    facts.append(
        identityFact('identity.role', identityRoleLabel(record.role)),
        identityFact('identity.authentication', identityProtocolLabel(record.authenticationMethod), { technical: true }),
        identityFact('identity.issued_at', identityFormatDate(record.issuedAt)),
        identityFact('identity.last_seen_at', identityFormatDate(record.lastSeenAt)),
        identityFact('identity.idle_expires_at', identityFormatDate(record.idleExpiresAt)),
        identityFact('identity.absolute_expires_at', identityFormatDate(record.absoluteExpiresAt))
    );
    article.appendChild(facts);
    const actions = identityElement('div', 'identity-record-actions');
    const revoke = identityElement('button', 'btn btn-danger btn-small', t('identity.revoke'));
    revoke.type = 'button';
    revoke.dataset.uiAction = 'identity-session-revoke';
    revoke.dataset.sessionReference = record.reference;
    revoke.disabled = !identityCan('sessions.manage');
    actions.appendChild(revoke);
    article.appendChild(actions);
    return article;
}

function renderIdentitySessions() {
    const list = document.getElementById('identitySessionList');
    if (!list) return;
    list.replaceChildren(...IdentityConsoleState.sessions.map(renderIdentitySession));
    if (!IdentityConsoleState.sessions.length) {
        list.appendChild(identityElement('p', 'identity-empty-state', identityCan('sessions.manage')
            ? t('identity.no_sessions')
            : t('identity.not_authorized')));
    }
    list.setAttribute('aria-busy', 'false');
    renderIdentitySessionPagination();
}

function renderIdentitySessionPagination() {
    const busy = IdentityConsoleState.sessionPageLoading;
    const pagination = document.getElementById('identitySessionPreviousPage')?.closest('.identity-pagination');
    if (pagination) pagination.hidden = !IdentityConsoleState.sessionCursorStack.length
        && !IdentityConsoleState.sessionNextCursor;
    document.getElementById('identitySessionPreviousPage').disabled =
        busy || IdentityConsoleState.sessionCursorStack.length === 0;
    document.getElementById('identitySessionNextPage').disabled =
        busy || !IdentityConsoleState.sessionNextCursor;
    document.getElementById('identitySessionPageNumber').textContent = t(
        'identity.page', { page: IdentityConsoleState.sessionPage }
    );
}

async function loadIdentityPage({
    signal = null,
    generation = IdentityConsoleState.generation,
    preserveOnError = false
} = {}) {
    if (!identityLoadIsCurrent(generation, signal)) return;
    if (!identityCan('identity.read')) {
        IdentityConsoleState.identities = [];
        IdentityConsoleState.identityNextCursor = null;
        renderIdentityList();
        identitySetStatus('identityListStatus', t('identity.not_authorized'), 'warning');
        return;
    }
    identitySetBusy('identityList', true);
    const params = new URLSearchParams({ page_size: String(IDENTITY_PAGE_SIZE) });
    if (IdentityConsoleState.identityCursor) params.set('cursor', IdentityConsoleState.identityCursor);
    try {
        const payload = await identityApi(`/identities?${params.toString()}`, { signal });
        if (!identityLoadIsCurrent(generation, signal)) return;
        const page = identityValidatePage(payload, 'identities', identityValidateRecord, 512);
        IdentityConsoleState.identities = page.records;
        IdentityConsoleState.identityNextCursor = page.nextCursor;
        renderIdentityList();
        identitySetStatus('identityListStatus');
    } catch (error) {
        if (error?.name === 'AbortError' || !identityLoadIsCurrent(generation, signal)) return;
        if (!preserveOnError || error.status === 403) {
            IdentityConsoleState.identities = [];
            IdentityConsoleState.identityNextCursor = null;
            renderIdentityList();
        }
        identitySetBusy('identityList', false);
        identitySetStatus(
            'identityListStatus', identityErrorMessage(error, 'identity.request_failed'), 'error'
        );
        return false;
    }
}

async function loadIdentitySessions({
    signal = null,
    generation = IdentityConsoleState.generation,
    preserveOnError = false
} = {}) {
    if (!identityLoadIsCurrent(generation, signal)) return;
    if (!identityCan('sessions.manage')) {
        IdentityConsoleState.sessions = [];
        IdentityConsoleState.sessionNextCursor = null;
        renderIdentitySessions();
        identitySetStatus('identitySessionStatus', t('identity.not_authorized'), 'warning');
        return;
    }
    identitySetBusy('identitySessionList', true);
    const params = new URLSearchParams({ page_size: String(IDENTITY_PAGE_SIZE) });
    if (IdentityConsoleState.sessionCursor) params.set('cursor', IdentityConsoleState.sessionCursor);
    try {
        const payload = await identityApi(`/sessions?${params.toString()}`, { signal });
        if (!identityLoadIsCurrent(generation, signal)) return;
        const page = identityValidatePage(
            payload, 'sessions', identityValidateSession, 64, /^ssr_[0-9a-f]{32}$/
        );
        IdentityConsoleState.sessions = page.records;
        IdentityConsoleState.sessionNextCursor = page.nextCursor;
        renderIdentitySessions();
        identitySetStatus('identitySessionStatus');
    } catch (error) {
        if (error?.name === 'AbortError' || !identityLoadIsCurrent(generation, signal)) return;
        if (!preserveOnError || error.status === 403) {
            IdentityConsoleState.sessions = [];
            IdentityConsoleState.sessionNextCursor = null;
            renderIdentitySessions();
        }
        identitySetBusy('identitySessionList', false);
        identitySetStatus(
            'identitySessionStatus', identityErrorMessage(error, 'identity.request_failed'), 'error'
        );
        return false;
    }
}

async function loadIdentityOidc({
    signal = null,
    generation = IdentityConsoleState.generation
} = {}) {
    if (!identityLoadIsCurrent(generation, signal)) return;
    if (!identityCan('identity.read')) {
        IdentityConsoleState.oidcPolicy = null;
        renderIdentityOidc();
        return;
    }
    try {
        const payload = await identityApi('/oidc-policy', { signal });
        if (!identityLoadIsCurrent(generation, signal)) return;
        IdentityConsoleState.oidcPolicy = identityValidateOidcPolicy(payload);
        AppState.teamAccessEnabled = IdentityConsoleState.oidcPolicy?.enabled === true;
        updateTeamAccessNavigation();
    } catch (error) {
        if (error?.name === 'AbortError' || !identityLoadIsCurrent(generation, signal)) return;
        if (error.status === 403) IdentityConsoleState.oidcPolicy = null;
        renderIdentityOidc();
        return false;
    }
    renderIdentityOidc();
}

async function loadIdentityRecovery({
    signal = null,
    generation = IdentityConsoleState.generation
} = {}) {
    if (!identityLoadIsCurrent(generation, signal)) return;
    if (!identityCan('recovery.manage')) {
        IdentityConsoleState.recovery = null;
        renderIdentityRecovery();
        return;
    }
    try {
        const payload = await identityApi('/recovery', { signal });
        if (!identityLoadIsCurrent(generation, signal)) return;
        IdentityConsoleState.recovery = identityValidateRecovery(payload);
    } catch (error) {
        if (error?.name === 'AbortError' || !identityLoadIsCurrent(generation, signal)) return;
        if (error.status === 403) IdentityConsoleState.recovery = null;
        renderIdentityRecovery();
        return false;
    }
    renderIdentityRecovery();
}

async function loadIdentityConsole({ announce = false } = {}) {
    if (IdentityConsoleState.loading) return;
    IdentityConsoleState.loading = true;
    IdentityConsoleState.controller?.abort();
    IdentityConsoleState.controller = new AbortController();
    const controller = IdentityConsoleState.controller;
    const generation = ++IdentityConsoleState.generation;
    identitySetRefreshBusy(true);
    for (const id of ['identityPrincipalSummary', 'identityOidcSummary', 'identityRecoverySummary', 'identityList', 'identitySessionList']) {
        identitySetBusy(id, true);
    }
    // The shaped regions already announce loading without adding/removing a page row.
    identitySetStatus('identityPageStatus');
    try {
        const current = await identityApi('/session', {
            signal: controller.signal
        });
        if (!identityLoadIsCurrent(generation, controller.signal)) return;
        IdentityConsoleState.principal = identityValidatePrincipal(current);
        IdentityConsoleState.permissions = new Set(IdentityConsoleState.principal.permissions);
        renderIdentityPrincipal();
        const results = await Promise.all([
            loadIdentityPage({ signal: controller.signal, generation, preserveOnError: true }),
            loadIdentitySessions({ signal: controller.signal, generation, preserveOnError: true }),
            loadIdentityOidc({ signal: controller.signal, generation }),
            loadIdentityRecovery({ signal: controller.signal, generation })
        ]);
        if (!identityLoadIsCurrent(generation, controller.signal)) return;
        IdentityConsoleState.loaded = true;
        identitySetStatus('identityPageStatus');
        if (announce) {
            const failed = results.includes(false);
            showStatus(t(failed ? 'identity.request_failed' : 'identity.refreshed'),
                failed ? 'error' : 'success');
        }
    } catch (error) {
        if (error?.name === 'AbortError' || !identityLoadIsCurrent(generation, controller.signal)) {
            return;
        }
        IdentityConsoleState.principal = null;
        IdentityConsoleState.permissions = new Set();
        IdentityConsoleState.identities = [];
        IdentityConsoleState.sessions = [];
        IdentityConsoleState.oidcPolicy = null;
        IdentityConsoleState.recovery = null;
        document.getElementById('identityPrincipalSummary')?.replaceChildren();
        identityStatusBadge('identityPrincipalBadge', 'identity.unavailable', 'danger');
        identitySetBusy('identityPrincipalSummary', false);
        renderIdentityOidc();
        renderIdentityRecovery();
        renderIdentityList();
        renderIdentitySessions();
        const message = identityErrorMessage(error, 'identity.load_failed');
        if (announce) {
            identitySetStatus('identityPageStatus');
            showStatus(message, 'error');
        } else {
            identitySetStatus('identityPageStatus', message, 'error');
        }
    } finally {
        if (generation === IdentityConsoleState.generation) {
            IdentityConsoleState.loading = false;
            identitySetRefreshBusy(false);
        }
    }
}

function findIdentityRecord(identityId) {
    return IdentityConsoleState.identities.find((record) => record.identityId === identityId) || null;
}

function identityCaptureCreateDraft(form) {
    const data = new FormData(form);
    const draft = {
        issuer: identitySafeText(data.get('issuer')),
        subject: identitySafeText(data.get('subject'), 255),
        role: identitySafeText(data.get('role'), 32)
    };
    IdentityConsoleState.createDraft = draft;
    return draft;
}

function openIdentityCreateDialog(draft = IdentityConsoleState.createDraft) {
    if (!identityCan('identity.manage')) return;
    const dialog = document.getElementById('identityCreateDialog');
    const form = document.getElementById('identityCreateForm');
    if (!dialog || !form) return;
    IdentityConsoleState.createReturnFocus = document.activeElement;
    const ownerOption = document.getElementById('identityCreateOwnerOption');
    if (ownerOption) {
        ownerOption.disabled = !identityCan('owners.manage');
        ownerOption.hidden = !identityCan('owners.manage');
    }
    if (draft) {
        form.elements.issuer.value = draft.issuer || '';
        form.elements.subject.value = draft.subject || '';
        form.elements.role.value = IDENTITY_ROLES.includes(draft.role) ? draft.role : 'viewer';
    } else {
        form.reset();
    }
    identitySetStatus('identityCreateStatus');
    dialog.showModal();
}

function closeIdentityCreateDialog({ clear = false } = {}) {
    const dialog = document.getElementById('identityCreateDialog');
    if (dialog?.open) dialog.close();
    if (clear) {
        IdentityConsoleState.createDraft = null;
        document.getElementById('identityCreateForm')?.reset();
    }
    const returnFocus = IdentityConsoleState.createReturnFocus;
    IdentityConsoleState.createReturnFocus = null;
    if (returnFocus instanceof HTMLElement && returnFocus.isConnected) returnFocus.focus();
}

function showIdentityConfirmation({ title, message, confirmLabel, returnFocus }) {
    const dialog = document.getElementById('identityConfirmDialog');
    if (!dialog) return Promise.resolve(false);
    if (IdentityConsoleState.confirmResolver) return Promise.resolve(false);
    document.getElementById('identityConfirmTitle').textContent = title;
    document.getElementById('identityConfirmMessage').textContent = message;
    document.getElementById('identityConfirmSubmit').textContent = confirmLabel;
    IdentityConsoleState.returnFocus = returnFocus || document.activeElement;
    dialog.showModal();
    document.getElementById('identityConfirmSubmit')?.focus();
    return new Promise((resolve) => {
        IdentityConsoleState.confirmResolver = resolve;
    });
}

function closeIdentityConfirmation(confirmed) {
    const dialog = document.getElementById('identityConfirmDialog');
    const resolve = IdentityConsoleState.confirmResolver;
    IdentityConsoleState.confirmResolver = null;
    if (dialog?.open) dialog.close();
    const returnFocus = IdentityConsoleState.returnFocus;
    IdentityConsoleState.returnFocus = null;
    if (returnFocus instanceof HTMLElement && returnFocus.isConnected) returnFocus.focus();
    if (resolve) resolve(Boolean(confirmed));
}

async function submitIdentityCreate(event) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity() || !identityCan('identity.manage')) return;
    const draft = identityCaptureCreateDraft(form);
    if (!IDENTITY_ROLES.includes(draft.role)) return;
    if (draft.role === 'owner' && !identityCan('owners.manage')) return;
    if (draft.role === 'owner') {
        closeIdentityCreateDialog();
        const confirmed = await showIdentityConfirmation({
            title: t('identity.confirm_change_title'),
            message: t('identity.confirm_owner_create'),
            confirmLabel: t('identity.create_owner'),
            returnFocus: document.getElementById('identityCreateButton')
        });
        if (!confirmed) {
            openIdentityCreateDialog(draft);
            return;
        }
    }
    const submit = document.getElementById('identityCreateSubmit');
    if (submit) submit.disabled = true;
    try {
        await identityApi('/identities', {
            method: 'POST',
            body: JSON.stringify(draft)
        });
        closeIdentityCreateDialog({ clear: true });
        await loadIdentityPage();
        identitySetStatus('identityListStatus', t('identity.saved'), 'success');
        identityFocus('#identityCreateButton', 'identityListStatus');
    } catch (error) {
        if (error.status === 409) {
            if (!document.getElementById('identityCreateDialog')?.open) openIdentityCreateDialog(draft);
            identitySetStatus('identityCreateStatus', t('identity.already_exists'), 'error');
        } else {
            if (!document.getElementById('identityCreateDialog')?.open) openIdentityCreateDialog(draft);
            identitySetStatus(
                'identityCreateStatus', identityErrorMessage(error, 'identity.request_failed'), 'error'
            );
        }
    } finally {
        if (submit) submit.disabled = false;
    }
}

async function toggleManagedIdentity(element) {
    const record = findIdentityRecord(element.dataset.identityId);
    if (!record || !identityCan('identity.manage')) return;
    if (record.role === 'owner' && !identityCan('owners.manage')) return;
    const enabled = !record.enabled;
    const confirmed = await showIdentityConfirmation({
        title: t('identity.confirm_change_title'),
        message: t(enabled ? 'identity.confirm_enable' : 'identity.confirm_disable', {
            id: record.identityId
        }),
        confirmLabel: t(enabled ? 'identity.enable' : 'identity.disable'),
        returnFocus: element
    });
    if (!confirmed) return;
    element.disabled = true;
    try {
        await identityApi(`/identities/${encodeURIComponent(record.identityId)}`, {
            method: 'PATCH',
            body: JSON.stringify({ enabled, expected_revision: record.revision })
        });
        if (identityMutationInvalidatesCurrentSession(record.identityId)) {
            identitySignOut();
            return;
        }
        await loadIdentityPage();
        await loadIdentitySessions();
        identitySetStatus('identityListStatus', t('identity.saved'), 'success');
        identityFocus(
            `[data-ui-action="identity-toggle"][data-identity-id="${CSS.escape(record.identityId)}"]`,
            'identityListStatus'
        );
    } catch (error) {
        if (error.status === 409) {
            await loadIdentityPage();
            identityFocus(
                `[data-ui-action="identity-toggle"][data-identity-id="${CSS.escape(record.identityId)}"]`,
                'identityListStatus'
            );
        }
        identitySetStatus(
            'identityListStatus', identityErrorMessage(error, 'identity.request_failed'), 'error'
        );
    } finally {
        if (element.isConnected) element.disabled = false;
    }
}

async function updateIdentityRole(element) {
    const record = findIdentityRecord(element.dataset.identityId);
    const select = document.querySelector(
        `[data-identity-role="${CSS.escape(element.dataset.identityId || '')}"]`
    );
    const role = identitySafeText(select?.value, 32);
    if (!record || !IDENTITY_ROLES.includes(role) || !identityCan('identity.manage')) return;
    if ((record.role === 'owner' || role === 'owner') && !identityCan('owners.manage')) return;
    if (role === record.role) {
        IdentityConsoleState.roleDrafts.delete(record.identityId);
        identitySetStatus('identityListStatus', t('identity.no_change'));
        return;
    }
    const confirmed = await showIdentityConfirmation({
        title: t('identity.confirm_change_title'),
        message: t('identity.confirm_role', { id: record.identityId, role: identityRoleLabel(role) }),
        confirmLabel: t('identity.save_role'),
        returnFocus: element
    });
    if (!confirmed) return;
    element.disabled = true;
    if (select) select.disabled = true;
    try {
        await identityApi(`/identities/${encodeURIComponent(record.identityId)}/role-binding`, {
            method: 'PUT',
            body: JSON.stringify({ role, expected_revision: record.bindingRevision })
        });
        if (identityMutationInvalidatesCurrentSession(record.identityId)) {
            identitySignOut();
            return;
        }
        IdentityConsoleState.roleDrafts.delete(record.identityId);
        await loadIdentityPage();
        await loadIdentitySessions();
        identitySetStatus('identityListStatus', t('identity.saved'), 'success');
        identityFocus(
            `[data-ui-action="identity-role"][data-identity-id="${CSS.escape(record.identityId)}"]`,
            'identityListStatus'
        );
    } catch (error) {
        if (error.status === 409) {
            IdentityConsoleState.roleDrafts.set(record.identityId, role);
            await loadIdentityPage();
            identityFocus(
                `[data-ui-action="identity-role"][data-identity-id="${CSS.escape(record.identityId)}"]`,
                'identityListStatus'
            );
        }
        identitySetStatus(
            'identityListStatus', identityErrorMessage(error, 'identity.request_failed'), 'error'
        );
    } finally {
        if (element.isConnected) element.disabled = false;
        if (select?.isConnected) select.disabled = false;
    }
}

async function revokeIdentitySession(element) {
    if (!identityCan('sessions.manage')) return;
    const reference = identitySafeText(element.dataset.sessionReference, 64);
    const record = IdentityConsoleState.sessions.find((item) => item.reference === reference);
    if (!record) return;
    const confirmed = await showIdentityConfirmation({
        title: t('identity.confirm_change_title'),
        message: t(record.current ? 'identity.confirm_revoke_current' : 'identity.confirm_revoke', {
            id: record.identityId
        }),
        confirmLabel: t('identity.revoke'),
        returnFocus: element
    });
    if (!confirmed) return;
    element.disabled = true;
    try {
        await identityApi(`/sessions/${encodeURIComponent(reference)}/revoke`, { method: 'POST' });
        if (record.current) {
            identitySignOut();
            return;
        }
        await loadIdentitySessions();
        identitySetStatus('identitySessionStatus', t('identity.revoked'), 'success');
        identityFocus('#identitySessionStatus', 'identitySessionsHeading');
    } catch (error) {
        identitySetStatus(
            'identitySessionStatus', identityErrorMessage(error, 'identity.request_failed'), 'error'
        );
    } finally {
        if (element.isConnected) element.disabled = false;
    }
}

async function advanceIdentityOidcPolicy(element) {
    const policy = IdentityConsoleState.oidcPolicy;
    if (!policy || !identityCan('oidc.manage')) return;
    const confirmed = await showIdentityConfirmation({
        title: t('identity.confirm_change_title'),
        message: t('identity.confirm_advance'),
        confirmLabel: t('identity.advance_oidc'),
        returnFocus: element
    });
    if (!confirmed) return;
    element.disabled = true;
    try {
        const result = await identityApi('/oidc-policy/advance', {
            method: 'POST',
            body: JSON.stringify({ expected_revision: Number(policy.revision) })
        });
        if (identityCurrentSessionInvalidatedByOidcAdvance()) {
            identitySignOut();
            return;
        }
        await Promise.all([loadIdentityOidc(), loadIdentitySessions()]);
        identitySetStatus(
            'identityPageStatus',
            result.revocation_complete === false
                ? t('identity.policy_advanced_incomplete')
                : t('identity.policy_advanced', { count: formatConsoleNumber(result.revoked_sessions) }),
            result.revocation_complete === false ? 'warning' : 'success'
        );
        identityFocus('#identityOidcAdvance', 'identityPageStatus');
    } catch (error) {
        if (error.status === 409) {
            await loadIdentityOidc();
            identityFocus('#identityOidcAdvance', 'identityPageStatus');
        }
        identitySetStatus(
            'identityPageStatus', identityErrorMessage(error, 'identity.request_failed'), 'error'
        );
    } finally {
        if (element.isConnected) element.disabled = false;
    }
}

async function changeIdentityPage(direction) {
    if (IdentityConsoleState.identityPageLoading) return;
    if (direction === 'next' && IdentityConsoleState.identityNextCursor) {
        IdentityConsoleState.identityCursorStack.push(IdentityConsoleState.identityCursor);
        IdentityConsoleState.identityCursor = IdentityConsoleState.identityNextCursor;
        IdentityConsoleState.identityNextCursor = null;
        IdentityConsoleState.identityPage += 1;
    } else if (direction === 'previous' && IdentityConsoleState.identityCursorStack.length) {
        IdentityConsoleState.identityCursor = IdentityConsoleState.identityCursorStack.pop() || null;
        IdentityConsoleState.identityNextCursor = null;
        IdentityConsoleState.identityPage = Math.max(1, IdentityConsoleState.identityPage - 1);
    } else {
        return;
    }
    IdentityConsoleState.identityPageLoading = true;
    renderIdentityPagination();
    try {
        await loadIdentityPage();
    } finally {
        IdentityConsoleState.identityPageLoading = false;
        renderIdentityPagination();
    }
}

async function changeIdentitySessionPage(direction) {
    if (IdentityConsoleState.sessionPageLoading) return;
    if (direction === 'next' && IdentityConsoleState.sessionNextCursor) {
        IdentityConsoleState.sessionCursorStack.push(IdentityConsoleState.sessionCursor);
        IdentityConsoleState.sessionCursor = IdentityConsoleState.sessionNextCursor;
        IdentityConsoleState.sessionNextCursor = null;
        IdentityConsoleState.sessionPage += 1;
    } else if (direction === 'previous' && IdentityConsoleState.sessionCursorStack.length) {
        IdentityConsoleState.sessionCursor = IdentityConsoleState.sessionCursorStack.pop() || null;
        IdentityConsoleState.sessionNextCursor = null;
        IdentityConsoleState.sessionPage = Math.max(1, IdentityConsoleState.sessionPage - 1);
    } else {
        return;
    }
    IdentityConsoleState.sessionPageLoading = true;
    renderIdentitySessionPagination();
    try {
        await loadIdentitySessions();
    } finally {
        IdentityConsoleState.sessionPageLoading = false;
        renderIdentitySessionPagination();
    }
}

function renderIdentityConsoleForLocale() {
    if (!IdentityConsoleState.loaded) return;
    renderIdentityPrincipal();
    renderIdentityOidc();
    renderIdentityRecovery();
    renderIdentityList();
    renderIdentitySessions();
}

function initIdentityBindings() {
    document.getElementById('identityCreateForm')?.addEventListener('submit', submitIdentityCreate);
    const createDialog = document.getElementById('identityCreateDialog');
    configureModalDismissal(createDialog, 'explicit');
    const confirmDialog = document.getElementById('identityConfirmDialog');
    configureModalDismissal(confirmDialog, 'explicit');
}

document.addEventListener('DOMContentLoaded', initIdentityBindings);
document.addEventListener('polaris:locale-change', renderIdentityConsoleForLocale);
