const IDENTITY_PAGE_SIZE = 25;
const IDENTITY_PERMISSION_LIMIT = 64;
const IDENTITY_ROLES = ['viewer', 'operator', 'security_admin', 'owner'];
const IDENTITY_PERMISSIONS = new Set([
    'identity.read',
    'identity.manage',
    'owners.manage',
    'sessions.manage',
    'oidc.manage',
    'recovery.manage'
]);

const IdentityConsoleState = {
    principal: null,
    permissions: new Set(),
    identities: [],
    sessions: [],
    oidcPolicy: null,
    recovery: null,
    identityCursor: null,
    identityNextCursor: null,
    identityCursorStack: [],
    identityPage: 1,
    sessionCursor: null,
    sessionNextCursor: null,
    sessionCursorStack: [],
    sessionPage: 1,
    identityPageLoading: false,
    sessionPageLoading: false,
    loading: false,
    loaded: false,
    generation: 0,
    controller: null,
    confirmResolver: null,
    returnFocus: null,
    createReturnFocus: null,
    createDraft: null,
    roleDrafts: new Map()
};

function identitySafeText(value, maxLength = 2048) {
    return typeof value === 'string' ? value.slice(0, maxLength) : '';
}

function identityCan(permission) {
    return IDENTITY_PERMISSIONS.has(permission) && IdentityConsoleState.permissions.has(permission);
}

function identityValidatePrincipal(payload) {
    const principal = payload?.principal;
    if (!principal || typeof principal !== 'object' || !Array.isArray(principal.permissions)) {
        throw new Error('invalid_identity_principal');
    }
    if (principal.permissions.length > IDENTITY_PERMISSION_LIMIT) {
        throw new Error('invalid_identity_permissions');
    }
    return {
        identityId: identitySafeText(principal.identity_id, 128),
        principalType: identitySafeText(principal.principal_type, 32),
        role: identitySafeText(principal.role, 32),
        roleSource: identitySafeText(principal.role_source, 32),
        permissions: [...new Set(principal.permissions.slice(0, IDENTITY_PERMISSION_LIMIT).filter(
            (permission) => typeof permission === 'string'
                && permission.length <= 64
                && /^[a-z_]+(?:\.[a-z_]+)+$/.test(permission)
        ))].sort(),
        authenticationContext: identitySafeText(payload.authentication_context, 32),
        session: payload.session && typeof payload.session === 'object' ? payload.session : null
    };
}

function identityValidateRecord(record) {
    if (!record || typeof record !== 'object') return null;
    const role = identitySafeText(record.role, 32);
    if (!IDENTITY_ROLES.includes(role)) return null;
    if (!Number.isInteger(record.revision) || !Number.isInteger(record.binding_revision)) return null;
    return {
        identityId: identitySafeText(record.identity_id, 128),
        principalType: identitySafeText(record.principal_type, 32),
        issuer: record.issuer === null ? null : identitySafeText(record.issuer),
        subject: record.subject === null ? null : identitySafeText(record.subject, 255),
        enabled: record.enabled === true,
        revision: record.revision,
        authorizationEpoch: Number(record.authorization_epoch) || 0,
        createdAt: identitySafeText(record.created_at, 64),
        updatedAt: identitySafeText(record.updated_at, 64),
        bindingId: identitySafeText(record.binding_id, 128),
        role,
        roleSource: identitySafeText(record.role_source, 32),
        bindingRevision: record.binding_revision
    };
}

function identityValidateSession(record) {
    if (!record || typeof record !== 'object') return null;
    const reference = identitySafeText(record.reference, 64);
    if (!/^ssr_[0-9a-f]{32}$/.test(reference)) return null;
    return {
        reference,
        identityId: identitySafeText(record.identity_id, 128),
        principalType: identitySafeText(record.principal_type, 32),
        role: identitySafeText(record.role, 32),
        roleSource: identitySafeText(record.role_source, 32),
        authenticationMethod: identitySafeText(record.authentication_method, 32),
        issuedAt: Number(record.issued_at),
        lastSeenAt: Number(record.last_seen_at),
        idleExpiresAt: Number(record.idle_expires_at),
        absoluteExpiresAt: Number(record.absolute_expires_at),
        current: record.current === true
    };
}

function identityValidateOidcPolicy(payload) {
    if (!payload || typeof payload !== 'object') return null;
    if (!['disabled', 'ready', 'invalid'].includes(payload.readiness)) return null;
    if (!Number.isInteger(payload.revision) || payload.revision < 1) return null;
    if (!Number.isInteger(payload.authorization_epoch) || payload.authorization_epoch < 1) return null;
    if (!Number.isInteger(payload.role_mapping_count) || payload.role_mapping_count < 0) return null;
    if (!Array.isArray(payload.scopes) || payload.scopes.length > 64) return null;
    const scopes = payload.scopes.slice(0, 64).map((scope) => (
        typeof scope === 'string' && scope.length <= 64 ? scope : null
    ));
    if (scopes.some((scope) => scope === null)) return null;
    return {
        enabled: payload.enabled === true,
        readiness: payload.readiness,
        secret_configured: payload.secret_configured === true,
        revision: payload.revision,
        authorization_epoch: payload.authorization_epoch,
        issuer: payload.issuer === null ? null : identitySafeText(payload.issuer),
        redirect_uri: payload.redirect_uri === null
            ? null
            : identitySafeText(payload.redirect_uri),
        scopes,
        role_mapping_count: payload.role_mapping_count
    };
}

function identityValidateRecovery(payload) {
    if (!payload || typeof payload !== 'object') return null;
    if (!['direct_loopback_only', 'network_reachable'].includes(payload.ingress_policy)) {
        return null;
    }
    return {
        local_owner_enabled: payload.local_owner_enabled === true,
        password_configured: payload.password_configured === true,
        ingress_policy: payload.ingress_policy,
        ready: payload.ready === true
    };
}

function identityValidateCursor(value, maximum, pattern = null) {
    if (value === null || value === undefined) return null;
    if (typeof value !== 'string' || value.length < 1 || value.length > maximum) return null;
    return pattern && !pattern.test(value) ? null : value;
}

function identityValidatePage(payload, collectionKey, validator, cursorMaximum, cursorPattern = null) {
    const records = payload?.[collectionKey];
    if (!Array.isArray(records) || records.length > IDENTITY_PAGE_SIZE) {
        throw new Error('invalid_identity_page');
    }
    const validated = records.slice(0, IDENTITY_PAGE_SIZE).map(validator);
    if (validated.some((record) => record === null)) throw new Error('invalid_identity_record');
    return {
        records: validated,
        nextCursor: identityValidateCursor(payload.next_cursor, cursorMaximum, cursorPattern)
    };
}

function identityCurrentSessionInvalidatedByOidcAdvance() {
    return IdentityConsoleState.principal?.principalType === 'oidc_user';
}

function identityMutationInvalidatesCurrentSession(identityId) {
    return identityCurrentSessionInvalidatedByOidcAdvance()
        && IdentityConsoleState.principal.identityId === identityId;
}

function identityResetState() {
    IdentityConsoleState.controller?.abort();
    IdentityConsoleState.generation += 1;
    IdentityConsoleState.principal = null;
    IdentityConsoleState.permissions = new Set();
    IdentityConsoleState.identities = [];
    IdentityConsoleState.sessions = [];
    IdentityConsoleState.oidcPolicy = null;
    IdentityConsoleState.recovery = null;
    IdentityConsoleState.identityCursor = null;
    IdentityConsoleState.identityNextCursor = null;
    IdentityConsoleState.identityCursorStack = [];
    IdentityConsoleState.identityPage = 1;
    IdentityConsoleState.sessionCursor = null;
    IdentityConsoleState.sessionNextCursor = null;
    IdentityConsoleState.sessionCursorStack = [];
    IdentityConsoleState.sessionPage = 1;
    IdentityConsoleState.identityPageLoading = false;
    IdentityConsoleState.sessionPageLoading = false;
    IdentityConsoleState.loading = false;
    IdentityConsoleState.loaded = false;
    IdentityConsoleState.controller = null;
    IdentityConsoleState.confirmResolver = null;
    IdentityConsoleState.returnFocus = null;
    IdentityConsoleState.createReturnFocus = null;
    IdentityConsoleState.createDraft = null;
    IdentityConsoleState.roleDrafts.clear();
}
