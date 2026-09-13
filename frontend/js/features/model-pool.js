function modelProviderMeta(providerId) {
    if (MODEL_PROVIDER_META[providerId]) return MODEL_PROVIDER_META[providerId];
    const name = String(providerId || t('provider'))
        .split(/[_-]+/)
        .filter(Boolean)
        .map(word => ['ai', 'api'].includes(word.toLowerCase())
            ? word.toUpperCase()
            : word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
        .join(' ');
    return { name, logo: '' };
}

function modelCatalogEntry(modelId) {
    return AppState.modelCatalog.find(entry => entry.model_id === modelId) || {
        model_id: modelId,
        providers: [],
        routable_providers: [],
        blacklisted_providers: [],
        available: false
    };
}

function deriveModelRouteState(selectedModels, catalog) {
    const selected = Array.isArray(selectedModels) ? [...new Set(selectedModels)] : [];
    const entries = new Map((Array.isArray(catalog) ? catalog : []).map(entry => [entry.model_id, entry]));
    const issues = [];
    let available = 0;
    let providerRoutes = 0;
    selected.forEach(modelId => {
        const entry = entries.get(modelId);
        if (!entry) {
            issues.push({code: 'model_not_discovered', severity: 'error', model_id: modelId});
            return;
        }
        const providers = Array.isArray(entry.routable_providers) ? entry.routable_providers : [];
        if (entry.available && providers.length > 0) {
            available += 1;
            providerRoutes += providers.length;
        } else {
            issues.push({code: 'model_temporarily_unavailable', severity: 'warning', model_id: modelId});
        }
    });
    if (selected.length === 0) {
        issues.push({code: 'route_has_no_models', severity: 'error', model_id: ''});
    } else if (available === 0) {
        issues.push({code: 'route_has_no_available_model', severity: 'error', model_id: ''});
    }
    const hasError = issues.some(issue => issue.severity === 'error');
    const unavailable = selected.length - available;
    const status = selected.length === 0
        ? 'draft'
        : (available === 0 || hasError ? 'unavailable' : (unavailable > 0 ? 'degraded' : 'ready'));
    return {
        valid: selected.length > 0 && available > 0 && !hasError,
        status,
        issues,
        summary: {
            selected_models: selected.length,
            available_models: available,
            unavailable_models: unavailable,
            provider_routes: providerRoutes
        }
    };
}

function appendModelProviderBadges(container, providers) {
    const values = Array.isArray(providers) ? providers : [];
    if (values.length === 0) {
        const unavailable = document.createElement('span');
        unavailable.className = 'model-provider-badge unavailable';
        unavailable.textContent = t('models.unavailable');
        container.appendChild(unavailable);
        return;
    }
    values.forEach(providerId => {
        const meta = modelProviderMeta(providerId);
        const badge = document.createElement('span');
        badge.className = 'model-provider-badge';
        if (meta.logo) {
            const logo = document.createElement('img');
            logo.src = meta.logo;
            logo.alt = '';
            badge.appendChild(logo);
        }
        badge.appendChild(document.createTextNode(meta.name));
        container.appendChild(badge);
    });
}

function updateModelPoolSummary() {
    const available = AppState.modelCatalog.filter(entry => entry.available).length;
    const unavailable = AppState.selectedModels.filter(
        modelId => !modelCatalogEntry(modelId).available
    ).length;
    const availableEl = document.getElementById('modelStatAvailable');
    const selectedEl = document.getElementById('modelStatSelected');
    const unavailableEl = document.getElementById('modelStatUnavailable');
    if (availableEl) availableEl.textContent = String(available);
    if (selectedEl) selectedEl.textContent = String(AppState.selectedModels.length);
    if (unavailableEl) unavailableEl.textContent = String(unavailable);

    const status = document.getElementById('modelPoolStatus');
    if (status) {
        const routeState = AppState.modelRouteValidation || deriveModelRouteState(AppState.selectedModels, AppState.modelCatalog);
        const statusName = AppState.modelPoolConfigured && AppState.modelPoolEnabled ? routeState.status : 'draft';
        const statusKey = {
            ready: 'models.ready',
            degraded: 'models.degraded',
            unavailable: 'models.unavailable',
            draft: 'models.not_configured'
        }[statusName];
        status.textContent = t(statusKey);
        status.className = `status-badge ${statusName === 'ready' ? 'success' : (statusName === 'degraded' ? 'warning' : (statusName === 'draft' ? 'muted' : 'danger'))}`;
    }

    const saveButton = document.getElementById('saveModelPoolBtn');
    if (saveButton) saveButton.textContent = t(AppState.modelPoolConfigured ? 'models.save_route' : 'models.create_route');
    document.getElementById('deleteModelRouteBtn')?.classList.toggle('hidden', !AppState.modelPoolConfigured);
    const testButton = document.getElementById('testModelRouteBtn');
    const dirty = modelRouteHasUnsavedChanges();
    document.getElementById('modelRouteUnsavedNotice')?.classList.toggle('hidden', !dirty);
    if (testButton) testButton.disabled = !(
        AppState.modelRouteValidation?.valid
        && AppState.modelPoolConfigured
        && AppState.modelPoolEnabled
        && !dirty
    );
}

function modelRouteHasUnsavedChanges() {
    return JSON.stringify(AppState.selectedModels) !== JSON.stringify(AppState.savedModelSelection)
        || Object.keys(modelRoutingPolicyChanges()).length > 0;
}

function formatModelBlacklistTime(timestamp) {
    const date = new Date(Number(timestamp || 0) * 1000);
    if (Number.isNaN(date.getTime())) return t('models.unavailable');
    return new Intl.DateTimeFormat(getActiveLocale(), {
        dateStyle: 'medium',
        timeStyle: 'short'
    }).format(date);
}

function renderModelBlacklist() {
    const list = document.getElementById('modelBlacklistList');
    const count = document.getElementById('modelBlacklistCount');
    const clearButton = document.getElementById('clearModelBlacklistBtn');
    if (!list) return;

    const entries = Array.isArray(AppState.modelBlacklist) ? AppState.modelBlacklist : [];
    if (count) count.textContent = t('models.route_count', {count: formatConsoleNumber(entries.length)});
    if (clearButton) clearButton.classList.toggle('hidden', entries.length === 0);
    list.replaceChildren();

    if (entries.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'model-empty-state';
        empty.textContent = t('models.no_unavailable_routes');
        list.appendChild(empty);
        return;
    }

    entries.forEach(entry => {
        const item = document.createElement('div');
        item.className = 'model-blacklist-item';

        const details = document.createElement('div');
        details.className = 'model-blacklist-details';
        const identity = document.createElement('div');
        identity.className = 'model-blacklist-identity';
        const model = document.createElement('strong');
        model.textContent = entry.model_id;
        const providerBadges = document.createElement('div');
        providerBadges.className = 'model-provider-badges';
        const providerMeta = modelProviderMeta(entry.provider_id);
        const providerBadge = document.createElement('span');
        providerBadge.className = 'model-provider-badge unavailable';
        if (providerMeta.logo) {
            const logo = document.createElement('img');
            logo.src = providerMeta.logo;
            logo.alt = '';
            providerBadge.appendChild(logo);
        }
        providerBadge.appendChild(document.createTextNode(providerMeta.name));
        providerBadges.appendChild(providerBadge);
        identity.append(model, providerBadges);

        const metadata = document.createElement('div');
        metadata.className = 'model-blacklist-meta';
        const status = document.createElement('span');
        status.textContent = 'HTTP 404';
        const occurrences = document.createElement('span');
        const failureCount = Math.max(1, Number(entry.failure_count || 1));
        occurrences.textContent = t('models.occurrence_count', {count: formatConsoleNumber(failureCount)});
        const lastSeen = document.createElement('span');
        lastSeen.textContent = t('models.last_seen', {time: formatModelBlacklistTime(entry.last_seen_at)});
        metadata.append(status, occurrences, lastSeen);
        if (entry.credential_name) {
            const credential = document.createElement('span');
            credential.textContent = t('models.credential_name', {name: entry.credential_name});
            metadata.appendChild(credential);
        }
        details.append(identity, metadata);

        const removeButton = document.createElement('button');
        removeButton.type = 'button';
        removeButton.className = 'btn btn-secondary btn-small';
        removeButton.textContent = t('remove');
        removeButton.title = entry.credential_name
            ? t('models.restore_credential_route')
            : t('models.restore_provider_route');
        removeButton.addEventListener('click', () => removeModelBlacklistEntry(
            entry.provider_id,
            entry.model_id,
            entry.credential_name || '',
            removeButton
        ));
        item.append(details, removeButton);
        list.appendChild(item);
    });
}

async function removeModelBlacklistEntry(providerId, modelId, credentialName, button) {
    if (button) button.disabled = true;
    try {
        const query = credentialName
            ? `?credential_name=${encodeURIComponent(credentialName)}`
            : '';
        const response = await fetch(
            `./api/model-blacklist/${encodeURIComponent(providerId)}/models/${encodeURIComponent(modelId)}${query}`,
            { method: 'DELETE', headers: getAuthHeaders() }
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || data.error || t('unknown_error'));
        await loadModelCatalog(false, { preserveContent: true });
        showStatus(data.message || t('models.route_restored'), 'success');
    } catch (error) {
        showStatus(t('models.route_restore_failed', {error: error.message}), 'error');
        if (button) button.disabled = false;
    }
}

async function clearModelBlacklist() {
    const confirmed = await showConfirmModal(
        t('models.clear_confirm'),
        {
            title: t('models.clear_title'),
            confirmLabel: t('clear_all')
        }
    );
    if (!confirmed) return;

    const button = document.getElementById('clearModelBlacklistBtn');
    if (button) button.disabled = true;
    try {
        const response = await fetch('./api/model-blacklist', {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || data.error || t('unknown_error'));
        await loadModelCatalog(false, { preserveContent: true });
        showStatus(data.message || t('models.blacklist_cleared'), 'success');
    } catch (error) {
        showStatus(t('models.blacklist_clear_failed', {error: error.message}), 'error');
    } finally {
        if (button) button.disabled = false;
    }
}

function createModelOrderButton(label, symbol, disabled, handler) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'model-order-button';
    button.setAttribute('aria-label', label);
    button.title = label;
    button.textContent = symbol;
    button.disabled = disabled;
    button.addEventListener('click', handler);
    return button;
}

function renderSelectedModels() {
    const list = document.getElementById('selectedModelList');
    if (!list) return;
    list.replaceChildren();

    if (AppState.selectedModels.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'model-empty-state';
        empty.textContent = t('models.select_one');
        list.appendChild(empty);
        updateModelPoolSummary();
        return;
    }

    AppState.selectedModels.forEach((modelId, index) => {
        const entry = modelCatalogEntry(modelId);
        const item = document.createElement('div');
        item.className = 'selected-model-item';

        const order = document.createElement('span');
        order.className = 'selected-model-order';
        order.textContent = String(index + 1);

        const details = document.createElement('div');
        details.className = 'selected-model-details';
        const name = document.createElement('strong');
        name.textContent = modelId;
        const providers = document.createElement('div');
        providers.className = 'model-provider-badges';
        appendModelProviderBadges(providers, entry.routable_providers || entry.providers);
        details.append(name, providers);
        if (!entry.available) {
            const availability = document.createElement('span');
            availability.className = 'field-hint';
            availability.textContent = t('models.issue_temporarily_unavailable', {model: modelId});
            details.appendChild(availability);
        }

        const actions = document.createElement('div');
        actions.className = 'model-order-actions';
        actions.append(
            createModelOrderButton(t('models.move_up'), '↑', index === 0, () => moveSelectedModel(index, -1)),
            createModelOrderButton(t('models.move_down'), '↓', index === AppState.selectedModels.length - 1, () => moveSelectedModel(index, 1)),
            createModelOrderButton(t('models.remove_selected'), '×', false, () => removeSelectedModel(modelId))
        );

        item.append(order, details, actions);
        list.appendChild(item);
    });
    updateModelPoolSummary();
}

function renderModelCatalog() {
    const list = document.getElementById('modelCatalogList');
    if (!list) return;
    const query = document.getElementById('modelCatalogSearch')?.value.trim().toLowerCase() || '';
    const entries = AppState.modelCatalog.filter(entry => {
        if (!query) return true;
        return entry.model_id.toLowerCase().includes(query)
            || entry.providers.some(provider => modelProviderMeta(provider).name.toLowerCase().includes(query));
    });
    list.replaceChildren();

    if (entries.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'model-empty-state';
        empty.textContent = t(AppState.modelCatalog.length ? 'models.no_matches' : 'models.none_available');
        list.appendChild(empty);
        return;
    }

    entries.forEach(entry => {
        const label = document.createElement('label');
        label.className = `model-catalog-item${entry.available ? '' : ' unavailable'}`;

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.dataset.modelId = entry.model_id;
        checkbox.checked = AppState.selectedModels.includes(entry.model_id);
        checkbox.disabled = !entry.available && !checkbox.checked;
        checkbox.addEventListener('change', () => toggleModelSelection(entry.model_id, checkbox.checked));

        const details = document.createElement('div');
        details.className = 'model-catalog-details';
        const name = document.createElement('strong');
        name.textContent = entry.model_id;
        const providers = document.createElement('div');
        providers.className = 'model-provider-badges';
        appendModelProviderBadges(providers, entry.routable_providers || entry.providers);
        details.append(name, providers);
        if (!entry.available) {
            const reason = document.createElement('span');
            reason.className = 'field-hint';
            reason.textContent = t('models.catalog_unavailable_reason');
            details.appendChild(reason);
        }
        label.append(checkbox, details);
        list.appendChild(label);
    });
}

function updateRouteDraftValidation() {
    AppState.modelRouteValidation = deriveModelRouteState(AppState.selectedModels, AppState.modelCatalog);
    updateModelPoolSummary();
}

function toggleModelSelection(modelId, selected) {
    if (selected && !AppState.selectedModels.includes(modelId)) {
        AppState.selectedModels.push(modelId);
    } else if (!selected) {
        AppState.selectedModels = AppState.selectedModels.filter(value => value !== modelId);
    }
    updateRouteDraftValidation();
    renderSelectedModels();
    renderModelCatalog();
    const checkbox = [...document.querySelectorAll('#modelCatalogList input')]
        .find(input => input.dataset.modelId === modelId);
    checkbox?.focus();
}

function moveSelectedModel(index, offset) {
    const nextIndex = index + offset;
    if (index < 0 || nextIndex < 0 || nextIndex >= AppState.selectedModels.length) return;
    const values = [...AppState.selectedModels];
    [values[index], values[nextIndex]] = [values[nextIndex], values[index]];
    AppState.selectedModels = values;
    updateRouteDraftValidation();
    renderSelectedModels();
    renderModelCatalog();
    document.getElementById('selectedModelList')?.children[nextIndex]
        ?.querySelector('button:not(:disabled)')?.focus();
}

function removeSelectedModel(modelId) {
    AppState.selectedModels = AppState.selectedModels.filter(value => value !== modelId);
    updateRouteDraftValidation();
    renderSelectedModels();
    renderModelCatalog();
}

function populateModelRoutingPolicy() {
    const policy = AppState.modelRoutingPolicy || {};
    const strategy = document.getElementById('modelRoutingStrategy');
    const preferred = document.getElementById('modelPreferredProvider');
    if (strategy) strategy.value = policy.strategy || 'balanced';
    if (preferred) {
        const current = policy.preferred_provider || '';
        const providers = new Map();
        (AppState.modelProviderCatalogs || []).forEach(group => {
            const routingId = String(group.routing_provider_id || group.provider_id || '');
            if (routingId && !providers.has(routingId)) providers.set(routingId, group.provider_name || routingId);
        });
        preferred.replaceChildren();
        const automatic = document.createElement('option');
        automatic.value = '';
        automatic.textContent = t('settings.automatic');
        preferred.appendChild(automatic);
        [...providers.entries()].sort((left, right) => left[1].localeCompare(right[1])).forEach(([id, name]) => {
            const option = document.createElement('option');
            option.value = id;
            option.textContent = name;
            preferred.appendChild(option);
        });
        if (current && !providers.has(current)) {
            const unavailable = document.createElement('option');
            unavailable.value = current;
            unavailable.textContent = t('models.preferred_provider_unavailable', {provider: current});
            preferred.appendChild(unavailable);
        }
        preferred.value = current;
    }
    syncModelRoutingPolicyControls();
}

function syncModelRoutingPolicyControls() {
    const strategy = document.getElementById('modelRoutingStrategy');
    const preferred = document.getElementById('modelPreferredProvider');
    const policy = AppState.modelRoutingPolicy || {};
    if (!strategy || !preferred) return;
    strategy.disabled = Boolean(policy.strategy_locked);
    preferred.disabled = strategy.value !== 'priority' || Boolean(policy.preferred_provider_locked);
    document.getElementById('modelRoutingLockNotice')?.classList.toggle(
        'hidden',
        !policy.strategy_locked && !policy.preferred_provider_locked
    );
    updateModelPoolSummary();
}

function modelRoutingPolicyChanges() {
    const policy = AppState.modelRoutingPolicy || {};
    const control = document.getElementById('modelRoutingStrategy');
    if (!control) return {};
    const strategy = control.value;
    const preferred = strategy === 'priority'
        ? (document.getElementById('modelPreferredProvider')?.value || '')
        : '';
    const config = {};
    if (!policy.strategy_locked && strategy !== (policy.strategy || 'balanced')) config.routing_strategy = strategy;
    if (!policy.preferred_provider_locked && preferred !== (policy.preferred_provider || '')) {
        config.preferred_provider = preferred;
    }
    return config;
}

async function saveModelRoutingPolicy() {
    const config = modelRoutingPolicyChanges();
    if (Object.keys(config).length === 0) return;
    const response = await fetch('./api/config/save', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({config})
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || data.error || t('unknown_error'));
    AppState.modelRoutingPolicy = {
        ...AppState.modelRoutingPolicy,
        ...(config.routing_strategy !== undefined ? {strategy: config.routing_strategy} : {}),
        ...(config.preferred_provider !== undefined ? {preferred_provider: config.preferred_provider} : {})
    };
}

function modelRouteError(data, fallback) {
    const detail = data?.detail;
    if (detail && typeof detail === 'object') return {...detail, message: detail.message || fallback};
    return {code: '', message: detail || data?.error || fallback};
}

async function loadModelCatalog(forceRefresh = false, options = {}) {
    const loading = document.getElementById('modelCatalogLoading');
    const workspace = document.getElementById('modelPoolWorkspace');
    const refreshButton = document.getElementById('refreshModelCatalogBtn');
    const preserveContent = options.preserveContent ?? AppState.modelCatalogLoaded;
    clearPageState('modelCatalogState');
    if (loading && !preserveContent) loading.classList.remove('hidden');
    if (workspace && !preserveContent) workspace.classList.add('hidden');
    if (refreshButton) refreshButton.disabled = true;
    try {
        const response = await fetch(`./api/model-catalog${forceRefresh ? '?refresh=true' : ''}`, {
            headers: getAuthHeaders()
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || data.error || t('unknown_error'));
        AppState.modelCatalog = Array.isArray(data.catalog) ? data.catalog : [];
        AppState.modelCatalogLoaded = true;
        AppState.modelBlacklist = Array.isArray(data.blacklist) ? data.blacklist : [];
        AppState.modelProviderCatalogs = Array.isArray(data.provider_catalogs) ? data.provider_catalogs : [];
        AppState.selectedModels = Array.isArray(data.pool?.selected_models)
            ? [...data.pool.selected_models]
            : [];
        AppState.savedModelSelection = [...AppState.selectedModels];
        AppState.modelPoolEnabled = data.pool?.enabled !== false;
        AppState.modelPoolConfigured = Boolean(data.pool?.configured);
        AppState.modelPoolRevision = data.pool?.revision || '';
        AppState.modelRouteValidation = data.validation || deriveModelRouteState(AppState.selectedModels, AppState.modelCatalog);
        AppState.modelRoutingPolicy = data.routing_policy || {strategy: 'balanced', preferred_provider: ''};
        clearPageState('modelCatalogState');
        populateModelRoutingPolicy();
        renderSelectedModels();
        renderModelCatalog();
        renderModelBlacklist();
        if (workspace) workspace.classList.remove('hidden');
        if (forceRefresh) showStatus(t('models.catalog_refreshed'), 'success');
    } catch (error) {
        const message = t('models.catalog_load_failed', {error: error.message});
        showPageState('modelCatalogState', {
            kind: preserveContent ? 'stale' : 'error',
            title: t(preserveContent ? 'warning' : 'error'),
            message,
            actionLabel: t('refresh'),
            onAction: () => loadModelCatalog(forceRefresh, {preserveContent: AppState.modelCatalogLoaded})
        });
        showStatus(message, 'error');
    } finally {
        if (loading && !preserveContent) loading.classList.add('hidden');
        if (refreshButton) refreshButton.disabled = false;
    }
}

async function validateModelRoute(options = {}) {
    const button = document.getElementById('validateModelRouteBtn');
    const selectedModels = [...AppState.selectedModels];
    if (button) button.disabled = true;
    try {
        const response = await fetch('./api/model-routes/omway/validate', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({selected_models: selectedModels, enabled: true})
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const failure = modelRouteError(data, t('unknown_error'));
            throw new Error(failure.message);
        }
        if (JSON.stringify(selectedModels) !== JSON.stringify(AppState.selectedModels)) return null;
        AppState.modelRouteValidation = data.validation || deriveModelRouteState(selectedModels, AppState.modelCatalog);
        updateModelPoolSummary();
        if (options.announce) {
            showStatus(
                t(AppState.modelRouteValidation.valid ? 'models.validation_passed' : 'models.validation_failed'),
                AppState.modelRouteValidation.valid ? 'success' : 'error'
            );
        }
        return AppState.modelRouteValidation;
    } catch (error) {
        showStatus(t('models.validation_request_failed', {error: error.message}), 'error');
        return null;
    } finally {
        if (button) button.disabled = false;
    }
}

async function saveModelPool() {
    const button = document.getElementById('saveModelPoolBtn');
    const workspace = document.getElementById('modelPoolWorkspace');
    if (workspace?.inert) return;
    if (workspace) workspace.inert = true;
    let routeSaved = false;
    if (button) button.disabled = true;
    try {
        const validation = await validateModelRoute();
        if (!validation?.valid) {
            showStatus(t('models.validation_failed'), 'error');
            return;
        }
        const creating = !AppState.modelPoolConfigured;
        const headers = getAuthHeaders();
        if (!creating && AppState.modelPoolRevision) headers['If-Match'] = AppState.modelPoolRevision;
        const response = await fetch('./api/model-routes/omway', {
            method: creating ? 'POST' : 'PATCH',
            headers,
            body: JSON.stringify({selected_models: AppState.selectedModels, enabled: true})
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const failure = modelRouteError(data, t('unknown_error'));
            if (failure.code === 'model_route_conflict' || failure.code === 'model_route_already_exists') {
                await loadModelCatalog(false, {preserveContent: true});
                throw new Error(t('models.route_conflict'));
            }
            if (failure.validation) {
                AppState.modelRouteValidation = failure.validation;
            }
            throw new Error(failure.message);
        }
        AppState.selectedModels = [...(data.pool?.selected_models || AppState.selectedModels)];
        AppState.savedModelSelection = [...AppState.selectedModels];
        AppState.modelPoolEnabled = data.pool?.enabled !== false;
        AppState.modelPoolConfigured = Boolean(data.pool?.configured);
        AppState.modelPoolRevision = data.pool?.revision || '';
        routeSaved = true;
        renderSelectedModels();
        renderModelCatalog();
        await saveModelRoutingPolicy();
        updateModelPoolSummary();
        showStatus(t(creating ? 'models.route_created' : 'models.route_saved'), 'success');
    } catch (error) {
        showStatus(t(routeSaved ? 'models.policy_save_failed' : 'models.virtual_save_failed', {error: error.message}), 'error');
    } finally {
        if (button) button.disabled = false;
        if (workspace) workspace.inert = false;
    }
}

async function deleteModelRoute() {
    const confirmed = await showConfirmModal(t('models.delete_confirm'), {
        title: t('models.delete_route'),
        confirmLabel: t('models.delete_route'),
        danger: true
    });
    if (!confirmed) return;
    const button = document.getElementById('deleteModelRouteBtn');
    if (button) button.disabled = true;
    try {
        const headers = getAuthHeaders();
        if (AppState.modelPoolRevision) headers['If-Match'] = AppState.modelPoolRevision;
        const response = await fetch('./api/model-routes/omway', {method: 'DELETE', headers});
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const failure = modelRouteError(data, t('unknown_error'));
            if (failure.code === 'model_route_conflict') {
                await loadModelCatalog(false, {preserveContent: true});
                throw new Error(t('models.route_conflict'));
            }
            throw new Error(failure.message);
        }
        AppState.selectedModels = [];
        AppState.savedModelSelection = [];
        AppState.modelPoolEnabled = false;
        AppState.modelPoolConfigured = false;
        AppState.modelPoolRevision = data.pool?.revision || '';
        updateRouteDraftValidation();
        renderSelectedModels();
        renderModelCatalog();
        showStatus(t('models.route_deleted'), 'success');
    } catch (error) {
        showStatus(t('models.route_delete_failed', {error: error.message}), 'error');
    } finally {
        if (button) button.disabled = false;
    }
}

function buildModelPlaygroundHandoff(alias = 'omway') {
    return {
        schema_version: 'playground-handoff.v1',
        source: 'models',
        model: alias
    };
}

async function testModelRouteInPlayground() {
    if (modelRouteHasUnsavedChanges() || !AppState.modelPoolConfigured || !AppState.modelPoolEnabled) {
        showStatus(t('models.unsaved_changes'), 'warning');
        return;
    }
    const validation = await validateModelRoute();
    if (!validation?.valid || !AppState.modelPoolConfigured) {
        showStatus(t('models.validation_failed'), 'error');
        return;
    }
    const handoff = buildModelPlaygroundHandoff('omway');
    try {
        sessionStorage.setItem('omni_gateway_playground_handoff_v1', JSON.stringify(handoff));
    } catch (_error) {
        // Storage can be disabled; the event still carries the bounded handoff in this session.
    }
    document.dispatchEvent(new CustomEvent('omni:playground-handoff', {detail: handoff}));
    if (typeof TAB_MAP === 'object' && TAB_MAP.playground) {
        window.location.assign(`${TAB_MAP.playground}?model=${encodeURIComponent(handoff.model)}&source=models`);
        return;
    }
    showStatus(t('models.playground_handoff_ready'), 'success');
}

// =====================================================================

// =====================================================================
