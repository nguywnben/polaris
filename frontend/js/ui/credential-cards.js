function getAuthHeaders(includeContentType = true) {

    const headers = {'Accept-Language': getActiveLocale()};
    if (includeContentType) headers['Content-Type'] = 'application/json';
    return headers;

}

function formatFileSize(bytes) {

    if (bytes < 1024) return bytes + ' B';

    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' KB';

    return Math.round(bytes / (1024 * 1024)) + ' MB';

}

function formatCooldownTime(remainingSeconds) {

    const hours = Math.floor(remainingSeconds / 3600);

    const minutes = Math.floor((remainingSeconds % 3600) / 60);

    const seconds = remainingSeconds % 60;

    if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;

    if (minutes > 0) return `${minutes}m ${seconds}s`;

    return `${seconds}s`;

}

// =====================================================================

// =====================================================================

function getCredentialProviderMeta(credInfo, managerType) {

    const provider = String(credInfo.provider_variant || credInfo.provider || credInfo.provider_name || '')
        .trim()
        .toLowerCase()
        .replace(/[\s-]+/g, '_');

    const extended = typeof EXTENDED_PROVIDER_UI !== 'undefined' && Object.hasOwn(EXTENDED_PROVIDER_UI, provider)
        ? EXTENDED_PROVIDER_UI[provider] : null;
    if (extended) {
        return {id: provider, name: extended.name, logo: `/frontend/assets/providers/${extended.logo}`};
    }

    if (provider === 'google_ai_studio' || provider === 'ai_studio' || provider === 'aistudio' || provider === 'gemini') {

        return {
            id: 'google_ai_studio',
            name: t('provider_google_ai_studio'),
            logo: '/frontend/assets/providers/google-ai-studio.png'
        };

    }

    if (provider === 'google_antigravity' || provider === 'antigravity' || provider === 'primary' || provider === 'provider' || (!provider && managerType === 'primary')) {

        return {
            id: 'google_antigravity',
            name: t('provider_antigravity'),
            logo: '/frontend/assets/providers/google-antigravity.png'
        };

    }

    if (provider === 'xai' || provider === 'grok' || provider === 'xai_grok' || provider === 'xai_console' || provider === 'xai_oauth' || provider === 'xai_api_key') {

        const credentialType = String(credInfo.credential_type || '').trim().toLowerCase();
        const isGrok = provider === 'grok' || provider === 'xai_oauth' || credentialType === 'oauth';
        const isXaiConsole = provider === 'xai_console' || provider === 'xai_api_key' || credentialType === 'api_key';

        if (isGrok) {
            return {
                id: 'grok',
                name: t('provider_grok'),
                logo: '/frontend/assets/providers/grok-build.png'
            };
        }

        if (isXaiConsole) {
            return {
                id: 'xai_console',
                name: 'SpaceXAI Console',
                logo: '/frontend/assets/providers/spacexai-console.png'
            };
        }

        return {
            id: 'grok',
            name: t('provider_grok'),
            logo: '/frontend/assets/providers/grok-build.png'
        };

    }

    if (provider === 'openai' || provider === 'codex' || provider === 'openai_codex' || provider === 'openai_platform' || provider === 'openai_api_key') {

        const credentialType = String(credInfo.credential_type || '').trim().toLowerCase();
        const isCodex = provider === 'codex' || provider === 'openai_codex' || credentialType === 'oauth';

        if (isCodex) {
            return {
                id: 'codex',
                name: 'Codex',
                logo: '/frontend/assets/providers/codex.png'
            };
        }

        return {
            id: 'openai_platform',
            name: 'OpenAI Platform',
            logo: '/frontend/assets/providers/openai-platform.png'
        };

    }

    if (provider === 'anthropic' || provider === 'claude' || provider === 'claude_code' || provider === 'claude_platform') {

        const credentialType = String(credInfo.credential_type || '').trim().toLowerCase();
        const isClaudeCode = provider === 'claude_code' || credentialType === 'oauth';

        return {
            id: isClaudeCode ? 'claude_code' : 'claude_platform',
            name: isClaudeCode ? 'Claude Code' : 'Claude Platform',
            logo: isClaudeCode ? '/frontend/assets/providers/claude-code.png' : '/frontend/assets/providers/claude-platform.png'
        };

    }

    if (provider === 'ollama' || provider === 'ollama_cloud' || provider === 'ollama_local') {

        return {
            id: 'ollama',
            name: 'Ollama',
            logo: '/frontend/assets/providers/ollama.png'
        };

    }

    return {
        id: 'google_antigravity',
        name: 'Google Antigravity',
        logo: '/frontend/assets/providers/google-antigravity.png'
    };

}

function createCredentialProviderGroup(providerMeta, credentials, manager) {

    const section = document.createElement('section');

    section.className = 'credential-provider-group';

    section.setAttribute('aria-labelledby', `credentialProviderGroup-${providerMeta.id}`);

    const logo = providerMeta.logo

        ? `<img src="${escapeAttribute(providerMeta.logo)}" alt="">`

        : `<span>${escapeHtml(providerMeta.name.charAt(0))}</span>`;

    const countLabel = t('credentials.workspace.visible', {count: formatConsoleNumber(credentials.length)});
    const scope = t('credentials.workspace.scope', {provider: providerMeta.name, count: formatConsoleNumber(credentials.length)});
    const operations = [
        ['enable', 'disable', 'action_enable'],
        ['disable', 'disable', 'action_disable'],
        ['delete', 'delete', 'action_delete'],
    ].filter(([, capability]) => credentials.some(item => manager.credentialSupportsOperation(item, capability)));
    const buttons = operations.map(([action, , label]) =>
        `<button type="button" class="cred-btn ${action === 'delete' ? 'delete' : ''}" data-provider-batch="${action}">${escapeHtml(t(label))}</button>`
    ).join('');

    section.innerHTML = `

        <div class="credential-provider-group-header">

            <div class="credential-provider-group-logo" aria-hidden="true">${logo}</div>

            <h2 class="credential-provider-group-title" id="credentialProviderGroup-${escapeAttribute(providerMeta.id)}">${escapeHtml(providerMeta.name)}</h2>

            <span class="credential-provider-group-count">${countLabel}</span>

            ${buttons ? `<div class="credential-provider-actions" role="group" aria-label="${escapeAttribute(`${providerMeta.name}: ${t('credentials.workspace.group_actions')}`)}" title="${escapeAttribute(scope)}">${buttons}</div>` : ''}

        </div>

        <div class="credential-provider-grid"></div>

    `;

    const grid = section.querySelector('.credential-provider-grid');

    credentials.forEach((credInfo) => {

        grid.appendChild(createCredCard(credInfo, manager));

    });

    const actions = section.querySelector('.credential-provider-actions');
    let pending = false;
    section.querySelectorAll('[data-provider-batch]').forEach(button => {
        button.addEventListener('click', async () => {
            if (pending) return;
            pending = true;
            actions.setAttribute('aria-busy', 'true');
            // Retain focus on the trigger for the confirmation dialog's return path.
            actions.querySelectorAll('button').forEach(item => item.setAttribute('aria-disabled', 'true'));
            try {
                await manager.batchAction(button.dataset.providerBatch, {
                    filenames: credentials.map(item => item.filename), description: scope,
                });
            } finally {
                pending = false;
                actions.removeAttribute('aria-busy');
                actions.querySelectorAll('button').forEach(item => item.removeAttribute('aria-disabled'));
            }
        });
    });

    return section;

}

function normalizeCredentialSubscriptionPlan(value, kind = 'plan') {

    const rawValue = String(value || '').trim();
    if (kind === 'provider_tier' || kind === 'provider_plan') {
        if (!rawValue || rawValue.length > 128 || /[\u0000-\u001f\u007f-\u009f]/.test(rawValue)
            || ['unknown', 'not_applicable', 'n/a', 'none'].includes(rawValue.toLowerCase())) return null;
        return {label: rawValue, kind: kind === 'provider_plan' ? 'plan' : 'tier', badgeClass: 'muted'};
    }
    if (!rawValue || rawValue.toLowerCase() === 'unknown' || rawValue.length > 48) return null;

    const normalizedKind = kind === 'tier' || /^tier[\s:_-]/i.test(rawValue) ? 'tier' : 'plan';
    const displayValue = rawValue
        .replace(/^tier[\s:_-]*/i, '')
        .replace(/[_-]+/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
    if (!displayValue) return null;

    const label = displayValue.replace(/\b\w/g, (character) => character.toUpperCase());
    const normalizedLabel = label.toLowerCase();
    const badgeClass = normalizedLabel === 'free'
        ? 'tier-free'
        : (normalizedLabel === 'ultra' || normalizedLabel === 'enterprise' ? 'tier-ultra' : 'tier-pro');

    return { label, kind: normalizedKind, badgeClass };

}

function renderCredentialSubscriptionBadge(pathId, value, kind = 'plan') {

    const plan = normalizeCredentialSubscriptionPlan(value, kind);
    if (!plan) {
        return `<span id="subscription-plan-${pathId}" class="status-badge subscription-badge muted" hidden></span>`;
    }

    const title = plan.kind === 'tier'
        ? t('credential_badge_tier', {tier: plan.label})
        : t('credential_badge_plan', {plan: plan.label});

    return `<span id="subscription-plan-${pathId}" class="status-badge subscription-badge credential-badge-hint ${plan.badgeClass}" tabindex="0" aria-label="${escapeAttribute(title)}"><span class="credential-badge-label">${escapeHtml(plan.label)}</span><span class="credential-badge-tooltip" aria-hidden="true">${escapeHtml(title)}</span></span>`;

}

function getCredentialAuthenticationType(providerMeta, credInfo) {

    const providerId = String(providerMeta?.id || '').trim().toLowerCase();
    if (['google_antigravity', 'grok', 'codex', 'claude_code'].includes(providerId)) return 'OAuth';
    if (['google_ai_studio', 'xai_console', 'openai_platform', 'claude_platform'].includes(providerId)) return 'API key';
    if (providerId === 'ollama') return 'Connection';

    const declaredType = String(credInfo?.credential_type || '').trim().toLowerCase();
    if (declaredType === 'oauth') return 'OAuth';
    if (declaredType === 'api_key') return 'API key';
    return '';

}

function renderCredentialAuthenticationBadge(providerMeta, credInfo, {compact = false} = {}) {

    const authenticationType = getCredentialAuthenticationType(providerMeta, credInfo);
    if (!authenticationType || (compact && authenticationType === 'OAuth')) return '';

    const label = authenticationType === 'Connection' ? t('pool.kind.connection')
        : authenticationType === 'API key' ? t('credentials.workspace.api_key') : authenticationType;
    return `<span class="status-badge muted">${escapeHtml(label)}</span>`;

}

function getCredentialAccountLabel(credInfo) {
    const label = String(credInfo.credential_label || '').trim();
    if (label) return label;
    const kind = String(credInfo.credential_type || 'oauth').toLowerCase();
    const email = kind === 'oauth' ? String(credInfo.user_email || '').trim() : '';
    if (email) return email;
    // Filenames are existing public inventory identifiers, not token/key fragments.
    return String(credInfo.filename || '').replace(/\.json$/i, '') || t('credential_details_title');
}

function createCredCard(credInfo, manager) {

    const div = document.createElement('div');

    const { status, filename } = credInfo;

    const managerType = manager.type;
    const providerMeta = getCredentialProviderMeta(credInfo, managerType);
    const isAntigravity = providerMeta.id === 'google_antigravity';
    const isMuseOAuth = providerMeta.id === 'muse_code' && credInfo.credential_type === 'oauth';
    const isManagedCredential = credInfo.source !== 'environment';
    const pathId = (managerType === 'primary' ? 'primary_' : '') + btoa(encodeURIComponent(filename)).replace(/[+/=]/g, '_');
    const supportsQuotaPreview = managerType === 'primary'
        && manager.credentialSupportsOperation(credInfo, 'quota');
    const supportsDisable = manager.credentialSupportsOperation(credInfo, 'disable');
    const supportsExport = manager.credentialSupportsOperation(credInfo, 'export');
    const supportsModelDiscovery = manager.credentialSupportsOperation(credInfo, 'model_discovery');
    const supportsVerify = manager.credentialSupportsOperation(credInfo, 'verify');
    const supportsTest = manager.credentialSupportsOperation(credInfo, 'test');
    const supportsDelete = manager.credentialSupportsOperation(credInfo, 'delete');
    const supportsEdit = managerType === 'primary' && isManagedCredential
        && manager.credentialSupportsOperation(credInfo, 'edit');
    const supportsReauthenticate = managerType === 'primary' && isManagedCredential
        && manager.credentialSupportsOperation(credInfo, 'reauthenticate');
    const shouldAutoLoadQuota = supportsQuotaPreview && !AppState.quotaPreviewCache[filename];

    if (shouldAutoLoadQuota) {

        AppState.quotaPreviewCache[filename] = { loading: true };

    }

    const accountLabel = getCredentialAccountLabel(credInfo);
    const modelCount = Number.isFinite(Number(credInfo.model_count)) ? Number(credInfo.model_count) : 0;

    div.className = status.disabled ? 'cred-card disabled' : 'cred-card';

    let statusBadges = '';
    let contextBadges = '';
    let cooldownBadges = '';

    statusBadges += status.disabled

        ? `<span class="status-badge disabled">${t('status_disabled')}</span>`

        : `<span class="status-badge enabled">${t('status_enabled')}</span>`;

    if (status.error_codes && status.error_codes.length > 0) {

        const errorLabel = `${t('error_code_prefix')} ${status.error_codes.join(', ')}`;
        statusBadges += `<span class="error-codes" title="${escapeAttribute(errorLabel)}">${escapeHtml(errorLabel)}</span>`;

        const autoBan = status.error_codes.filter(c => c === 400 || c === 403);

        if (autoBan.length > 0 && status.disabled) {

            statusBadges += `<span class="status-badge danger">${t('credential_badge_auto_disabled')}</span>`;

        }

    }

    if (managerType !== 'primary' && credInfo.preview) {

        statusBadges += `<span class="status-badge success" title="${t('preview_supported_title')}">${t('credential_badge_preview', {state: t('credential_state_on')})}</span>`;

    }

    statusBadges += renderCredentialAuthenticationBadge(providerMeta, credInfo, {compact: true});

    if (!isManagedCredential) {
        statusBadges += `<span class="status-badge muted" title="${escapeAttribute(t('settings.managed_environment'))}">${t('credential_badge_environment')}</span>`;
    }

    if (isAntigravity) {

        contextBadges += renderCredentialSubscriptionBadge(pathId, credInfo.tier, 'plan');

    } else if (isMuseOAuth) {

        contextBadges += renderCredentialSubscriptionBadge(
            pathId,
            AppState.quotaPreviewCache[filename]?.data?.plan || AppState.quotaPreviewCache[filename]?.data?.subscription_tier,
            AppState.quotaPreviewCache[filename]?.data?.plan ? 'provider_plan' : 'provider_tier'
        );

    } else if (supportsQuotaPreview) {

        contextBadges += renderCredentialSubscriptionBadge(
            pathId,
            AppState.quotaPreviewCache[filename]?.data?.plan,
            'plan'
        );

    } else if (managerType !== 'primary' && credInfo.tier) {

        const tier = credInfo.tier.toString().toLowerCase();

        const tierLabel = tier.toUpperCase();

        const tierClass = tier === 'ultra' ? 'tier-ultra' : (tier === 'free' ? 'tier-free' : 'tier-pro');

        contextBadges += `<span class="status-badge ${tierClass}" title="${escapeAttribute(`${t('tier_badge_title')}: ${tierLabel}`)}">${tierLabel}</span>`;

    }

    if (managerType === 'primary' && isAntigravity && credInfo.enable_credit) {

        const creditLabel = t('credit_enabled_title');
        contextBadges += `<span class="status-badge credit-on credential-badge-hint" tabindex="0" aria-label="${escapeAttribute(creditLabel)}"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"></rect><path d="M3 10h18M7 15h3"></path></svg><span class="credential-badge-tooltip" aria-hidden="true">${escapeHtml(creditLabel)}</span></span>`;

    }

    if (credInfo.model_cooldowns && Object.keys(credInfo.model_cooldowns).length > 0) {

        const currentTime = Date.now() / 1000;

        const activeCooldowns = Object.entries(credInfo.model_cooldowns)

            .filter(([, until]) => until > currentTime)

            .map(([model, until]) => {

                const remaining = Math.max(0, Math.floor(until - currentTime));

                const shortModel = model.replace('gemini-', '').replace('-exp', '')

                    .replace('2.0-', '2-').replace('1.5-', '1.5-');

                return {

                    model: shortModel,

                    time: formatCooldownTime(remaining).replace(/s$/, '').replace(/ /g, ''),

                    fullModel: model

                };

            });

        if (activeCooldowns.length > 0) {

            activeCooldowns.slice(0, 2).forEach(item => {

                cooldownBadges += `<span class="cooldown-badge" title="${escapeAttribute(`${t('model_title')}: ${item.fullModel}`)}">${t('credential_badge_cooldown', {model: escapeHtml(item.model), time: escapeHtml(item.time)})}</span>`;

            });

            if (activeCooldowns.length > 2) {

                const remaining = activeCooldowns.length - 2;

                const remainingModels = activeCooldowns.slice(2).map(i => `${i.fullModel}: ${i.time}`).join('\n');

                cooldownBadges += `<span class="cooldown-badge" title="${escapeAttribute(`${t('other_models_title')}: ${remainingModels}`)}">+${remaining}</span>`;

            }

        }

    }

    AppState.credentialCardIndex[pathId] = {
        filename,
        managerType,
        email: credInfo.user_email || '',
        accountLabel,
        providerName: providerMeta.name,
        providerVariant: providerMeta.id,
        credentialSource: credInfo.source || 'managed',
        modelCount: Number.isFinite(Number(credInfo.model_count)) ? Number(credInfo.model_count) : 0,
        subscriptionPlan: isAntigravity ? credInfo.tier : '',
        subscriptionKind: isAntigravity ? 'plan' : '',
    };

    const primaryActionButtons = `

        ${supportsDisable ? (status.disabled

            ? `<button type="button" class="cred-btn icon-btn enable" data-credential-command="enable" aria-label="${escapeAttribute(t('action_enable'))}" title="${escapeAttribute(t('action_enable'))}"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v9"></path><path d="M18.4 6.6a8 8 0 1 1-12.8 0"></path></svg><span class="visually-hidden">${escapeHtml(t('action_enable'))}</span></button>`

            : `<button type="button" class="cred-btn icon-btn disable" data-credential-command="disable" aria-label="${escapeAttribute(t('action_disable'))}" title="${escapeAttribute(t('action_disable'))}"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v9"></path><path d="M18.4 6.6a8 8 0 1 1-12.8 0"></path></svg><span class="visually-hidden">${escapeHtml(t('action_disable'))}</span></button>`

        ) : ''}

        ${supportsTest ? `<button type="button" class="cred-btn icon-btn" data-credential-command="test" aria-label="${escapeAttribute(t('btn_test_model'))}" title="${escapeAttribute(t('btn_test_model_title'))}"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6"></path><path d="M10 3v6l-5 8.5A2 2 0 0 0 6.7 21h10.6A2 2 0 0 0 19 17.5L14 9V3"></path><path d="M8 14h8"></path></svg><span class="visually-hidden">${escapeHtml(t('btn_test_model'))}</span></button>` : ''}

        <button type="button" class="cred-btn icon-btn view" data-credential-command="manage" aria-label="${escapeAttribute(t('credentials.workspace.manage'))}" title="${escapeAttribute(t('credentials.workspace.manage'))}"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h10"></path><path d="M18 7h2"></path><circle cx="16" cy="7" r="2"></circle><path d="M4 17h2"></path><path d="M10 17h10"></path><circle cx="8" cy="17" r="2"></circle></svg><span class="visually-hidden">${escapeHtml(t('credentials.workspace.manage'))}</span></button>

    `;

    const checkboxClass = manager.getElementId('file-checkbox');
    const quotaPreview = supportsQuotaPreview ? renderCredentialQuotaPreview(pathId, filename, managerType) : '';

    div.innerHTML = `

        <div class="cred-header">

            <div class="cred-title-row">

                <input type="checkbox" class="${escapeAttribute(checkboxClass)}" data-filename="${escapeAttribute(filename)}" data-credential-select aria-label="${escapeAttribute(t('credentials.workspace.select', {name: accountLabel}))}">

                <div class="cred-identity" title="${escapeAttribute(filename)}">
                    <div class="cred-identity-copy">
                        <h3 class="cred-account-name" title="${escapeAttribute(accountLabel)}">${escapeHtml(accountLabel)}</h3>
                        ${credInfo.credential_label && getCredentialAuthenticationType(providerMeta, credInfo) === 'OAuth' && credInfo.user_email && credInfo.user_email !== accountLabel ? `<div class="cred-email" title="${escapeAttribute(credInfo.user_email)}">${escapeHtml(credInfo.user_email)}</div>` : ''}
                    </div>
                </div>

            </div>

            <div class="cred-status cred-summary">${statusBadges}${contextBadges}</div>
            ${cooldownBadges ? `<div class="cred-status cred-context">${cooldownBadges}</div>` : ''}

        </div>

        <div class="cred-metrics">
            <span>${escapeHtml(t('credentials.workspace.models', {count: formatConsoleNumber(modelCount)}))}</span>
            ${quotaPreview}
        </div>

        ${credInfo.validation_status === 'unverified' ? `<p class="upload-result-message" data-i18n="provider.ownership.import_unverified_provenance">${escapeHtml(t('provider.ownership.import_unverified_provenance'))}</p>` : ''}

        <div class="cred-actions">
            <div class="cred-actions-primary">${primaryActionButtons}</div>
        </div>

    `;

    const selectionCheckbox = div.querySelector('[data-credential-select]');
    if (selectionCheckbox) {
        selectionCheckbox.addEventListener('change', () => {
            if (managerType === 'primary') togglePrimaryFileSelection(filename);
            else toggleFileSelection(filename);
        });
    }

    const quotaPreviewButton = div.querySelector('[data-quota-preview]');
    if (quotaPreviewButton) {
        quotaPreviewButton.addEventListener('click', () => loadPrimaryQuotaPreview(pathId));
    }

    const executeCommand = async (command) => {
        if (command === 'manage') {
            await showCredentialManagement(pathId, manager, credInfo, {
                disable: supportsDisable, verify: supportsVerify, test: supportsTest,
                edit: supportsEdit, reauthenticate: supportsReauthenticate, export: supportsExport,
                models: supportsModelDiscovery, quota: supportsQuotaPreview, delete: supportsDelete,
                reveal: manager.permissions.has('credentials.export'),
                preview: managerType !== 'primary' && manager.canOperateCredential('verify'),
                credit: managerType === 'primary' && isManagedCredential && manager.credentialSupportsOperation(credInfo, 'credit_mode'),
            });
            return;
        }

        if (command === 'delete' && !(await showConfirmModal(t('confirm_delete_cred'), {
            title: t('confirm_delete_cred_title'), confirmLabel: t('action_delete'),
        }))) return;

        if (['enable', 'disable', 'delete', 'enable_credit', 'disable_credit'].includes(command)) {
            await manager.action(filename, command);
            return;
        }

        if (command === 'view') await toggleCredDetailsCommon(pathId, manager);
        if (command === 'download') {
            if (managerType === 'primary') downloadPrimaryCred(filename);
            else downloadCred(filename);
        }
        if (command === 'quota') await togglePrimaryQuotaDetails(pathId);
        if (command === 'edit') await showCredentialEditModal(pathId);
        if (command === 'reauthenticate') reauthenticateCredential(pathId);
        if (command === 'models') await showCredentialModels(pathId);
        if (command === 'preview') await configurePreviewChannel(filename);
        if (command === 'verify') {
            if (managerType === 'primary') await verifyProviderCredential(filename);
            else await verifyCredential(filename);
        }
        if (command === 'test') await showCredentialModelTest(pathId);
        if (command === 'errors') await toggleErrorDetailsCommon(pathId, manager);
    };
    div.querySelectorAll('[data-credential-command]').forEach(button => {
        button.addEventListener('click', async () => {
            const command = button.dataset.credentialCommand;
            // Keep dialog triggers focusable so closing restores keyboard focus.
            const changesState = command === 'enable' || command === 'disable';
            if (changesState) button.disabled = true;
            try { await executeCommand(command); }
            finally { if (changesState) button.disabled = false; }
        });
    });

    if (shouldAutoLoadQuota) {

        setTimeout(() => loadPrimaryQuotaPreview(pathId), 0);

    }

    return div;

}

// =====================================================================

// =====================================================================

async function toggleCredDetails(pathId) {

    await toggleCredDetailsCommon(pathId, AppState.creds);

}

async function togglePrimaryCredDetails(pathId) {

    await toggleCredDetailsCommon(pathId, AppState.primaryCreds);

}

async function toggleCredDetailsCommon(pathId, manager) {

    const { filename, manager: resolvedManager } = getCredentialModalContext(pathId, manager);

    if (!filename) return;

    showStatus(t('status_loading_file_content'), 'info');

    try {

        const modeParam = resolvedManager.type === 'primary' ? 'mode=provider' : 'mode=code_assist';

        const endpoint = `./api/credentials/detail/${encodeURIComponent(filename)}?${modeParam}`;

        const response = await fetch(endpoint, { headers: getAuthHeaders() });

        const data = await response.json();

        if (response.ok && data.content) {

            showMessageModal(t('credential_details_title'), buildCredentialContentHtml(filename, data.content), 'info', {html: true});

        } else {

            const errorMsg = data.error || data.detail || t('unknown_error');

            showStatus(`${t('unable_to_load_file_content')} ${errorMsg}`, 'error');

            showMessageModal(t('credential_details_title'), `${t('unable_to_load_file_content')} ${errorMsg}`, 'error');

        }

    } catch (error) {

        const errorMsg = `${t('unable_to_load_file_content')} ${error.message}`;

        showStatus(errorMsg, 'error');

        showMessageModal(t('credential_details_title'), errorMsg, 'error');

    }

}

// =====================================================================

// =====================================================================
