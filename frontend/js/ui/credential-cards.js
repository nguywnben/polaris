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

    if (provider === 'google_ai_studio' || provider === 'ai_studio' || provider === 'aistudio' || provider === 'gemini') {

        return {
            id: 'google_ai_studio',
            name: t('provider_google_ai_studio'),
            logo: '/frontend/assets/providers/google-ai-studio-logo.png'
        };

    }

    if (provider === 'google_antigravity' || provider === 'antigravity' || provider === 'primary' || provider === 'provider' || (!provider && managerType === 'primary')) {

        return {
            id: 'google_antigravity',
            name: t('provider_antigravity'),
            logo: '/frontend/assets/providers/google-antigravity-logo.png'
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
                logo: '/frontend/assets/providers/grok-build-logo.png'
            };
        }

        if (isXaiConsole) {
            return {
                id: 'xai_console',
                name: 'SpaceXAI Console',
                logo: '/frontend/assets/providers/spacexai-console-logo.png'
            };
        }

        return {
            id: 'grok',
            name: t('provider_grok'),
            logo: '/frontend/assets/providers/grok-build-logo.png'
        };

    }

    if (provider === 'openai' || provider === 'codex' || provider === 'openai_codex' || provider === 'openai_platform' || provider === 'openai_api_key') {

        const credentialType = String(credInfo.credential_type || '').trim().toLowerCase();
        const isCodex = provider === 'codex' || provider === 'openai_codex' || credentialType === 'oauth';

        if (isCodex) {
            return {
                id: 'codex',
                name: 'Codex',
                logo: '/frontend/assets/providers/codex-logo.png'
            };
        }

        return {
            id: 'openai_platform',
            name: 'OpenAI Platform',
            logo: '/frontend/assets/providers/openai-platform-logo.png'
        };

    }

    if (provider === 'anthropic' || provider === 'claude' || provider === 'claude_code' || provider === 'claude_platform') {

        const credentialType = String(credInfo.credential_type || '').trim().toLowerCase();
        const isClaudeCode = provider === 'claude_code' || credentialType === 'oauth';

        return {
            id: isClaudeCode ? 'claude_code' : 'claude_platform',
            name: isClaudeCode ? 'Claude Code' : 'Claude Platform',
            logo: isClaudeCode ? '/frontend/assets/providers/claude-code-logo.png' : '/frontend/assets/providers/claude-platform-logo.png'
        };

    }

    if (provider === 'ollama' || provider === 'ollama_cloud' || provider === 'ollama_local') {

        return {
            id: 'ollama',
            name: 'Ollama',
            logo: '/frontend/assets/providers/ollama-logo.png'
        };

    }

    return {
        id: 'google_antigravity',
        name: 'Google Antigravity',
        logo: '/frontend/assets/providers/google-antigravity-logo.png'
    };

}

function createCredentialProviderGroup(providerMeta, credentials, manager) {

    const section = document.createElement('section');

    section.className = 'credential-provider-group';

    section.setAttribute('aria-labelledby', `credentialProviderGroup-${providerMeta.id}`);

    const logo = providerMeta.logo

        ? `<img src="${escapeAttribute(providerMeta.logo)}" alt="">`

        : `<span>${escapeHtml(providerMeta.name.charAt(0))}</span>`;

    const countLabel = t('credential_count', {count: formatConsoleNumber(credentials.length)});

    section.innerHTML = `

        <div class="credential-provider-group-header">

            <div class="credential-provider-group-logo" aria-hidden="true">${logo}</div>

            <h2 class="credential-provider-group-title" id="credentialProviderGroup-${escapeAttribute(providerMeta.id)}">${escapeHtml(providerMeta.name)}</h2>

            <span class="credential-provider-group-count">${countLabel}</span>

        </div>

        <div class="credential-provider-grid"></div>

    `;

    const grid = section.querySelector('.credential-provider-grid');

    credentials.forEach((credInfo) => {

        grid.appendChild(createCredCard(credInfo, manager));

    });

    return section;

}

function normalizeCredentialSubscriptionPlan(value, kind = 'plan') {

    const rawValue = String(value || '').trim();
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

    const badgeLabel = plan.kind === 'tier'
        ? t('credential_badge_tier', {tier: escapeHtml(plan.label)})
        : t('credential_badge_plan', {plan: escapeHtml(plan.label)});
    const title = plan.kind === 'tier'
        ? `Access tier reported by the provider: ${plan.label}`
        : `Subscription plan reported by the provider: ${plan.label}`;

    return `<span id="subscription-plan-${pathId}" class="status-badge subscription-badge ${plan.badgeClass}" title="${escapeAttribute(title)}">${badgeLabel}</span>`;

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

function renderCredentialAuthenticationBadge(providerMeta, credInfo) {

    const authenticationType = getCredentialAuthenticationType(providerMeta, credInfo);
    if (!authenticationType) return '';

    const title = `${providerMeta.name} ${authenticationType} credential`;
    return `<span class="status-badge muted" title="${escapeAttribute(title)}">${authenticationType}</span>`;

}

function createCredCard(credInfo, manager) {

    const div = document.createElement('div');

    const { status, filename } = credInfo;

    const managerType = manager.type;
    const providerMeta = getCredentialProviderMeta(credInfo, managerType);
    const isAntigravity = providerMeta.id === 'google_antigravity';
    const isCodexOAuth = providerMeta.id === 'codex' && credInfo.credential_type === 'oauth';
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

    const accountLabel = credInfo.credential_label || credInfo.user_email || t('email_not_fetched');
    const accountClass = (credInfo.credential_label || credInfo.user_email) ? 'cred-email' : 'cred-email empty';
    const providerLogo = providerMeta.logo
        ? `<img src="${escapeAttribute(providerMeta.logo)}" alt="${escapeAttribute(providerMeta.name)} logo">`
        : `<span>${escapeHtml(providerMeta.name.charAt(0))}</span>`;

    div.className = status.disabled ? 'cred-card disabled' : 'cred-card';

    let statusBadges = '';

    statusBadges += status.disabled

        ? `<span class="status-badge disabled">${t('status_disabled')}</span>`

        : `<span class="status-badge enabled">${t('status_enabled')}</span>`;

    if (status.error_codes && status.error_codes.length > 0) {

        statusBadges += `<span class="error-codes">${t('error_code_prefix')} ${escapeHtml(status.error_codes.join(', '))}</span>`;

        const autoBan = status.error_codes.filter(c => c === 400 || c === 403);

        if (autoBan.length > 0 && status.disabled) {

            statusBadges += `<span class="status-badge danger">${t('credential_badge_auto_disabled')}</span>`;

        }

    }

    if (managerType !== 'primary' && credInfo.preview) {

        statusBadges += `<span class="status-badge success" title="${t('preview_supported_title')}">${t('credential_badge_preview', {state: t('credential_state_on')})}</span>`;

    }

    statusBadges += renderCredentialAuthenticationBadge(providerMeta, credInfo);

    if (!isManagedCredential) {
        statusBadges += `<span class="status-badge muted" title="${escapeAttribute(t('settings.managed_environment'))}">${t('credential_badge_environment')}</span>`;
    }

    if (isAntigravity) {

        statusBadges += renderCredentialSubscriptionBadge(pathId, credInfo.tier, 'plan');

    } else if (isCodexOAuth) {

        statusBadges += renderCredentialSubscriptionBadge(
            pathId,
            AppState.quotaPreviewCache[filename]?.data?.plan,
            'plan'
        );

    } else if (managerType !== 'primary') {

        const tier = (credInfo.tier || 'pro').toString().toLowerCase();

        const tierLabel = tier.toUpperCase();

        const tierClass = tier === 'ultra' ? 'tier-ultra' : (tier === 'free' ? 'tier-free' : 'tier-pro');

        statusBadges += `<span class="status-badge ${tierClass}" title="${escapeAttribute(`${t('tier_badge_title')}: ${tierLabel}`)}">${tierLabel}</span>`;

    }

    if (managerType === 'primary' && isAntigravity && credInfo.enable_credit) {

        statusBadges += `<span class="status-badge credit-on" title="${t('credit_enabled_title')}">${t('credential_badge_credits', {state: t('credential_state_on')})}</span>`;

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

                statusBadges += `<span class="cooldown-badge" title="${escapeAttribute(`${t('model_title')}: ${item.fullModel}`)}">${t('credential_badge_cooldown', {model: escapeHtml(item.model), time: escapeHtml(item.time)})}</span>`;

            });

            if (activeCooldowns.length > 2) {

                const remaining = activeCooldowns.length - 2;

                const remainingModels = activeCooldowns.slice(2).map(i => `${i.fullModel}: ${i.time}`).join('\n');

                statusBadges += `<span class="cooldown-badge" title="${escapeAttribute(`${t('other_models_title')}: ${remainingModels}`)}">+${remaining}</span>`;

            }

        }

    }

    AppState.credentialCardIndex[pathId] = {
        filename,
        managerType,
        email: credInfo.user_email || '',
        accountLabel: credInfo.user_email || credInfo.credential_label || '',
        providerName: providerMeta.name,
        providerVariant: providerMeta.id,
        credentialSource: credInfo.source || 'managed',
        modelCount: Number.isFinite(Number(credInfo.model_count)) ? Number(credInfo.model_count) : 0,
        subscriptionPlan: isAntigravity ? credInfo.tier : '',
        subscriptionKind: isAntigravity ? 'plan' : '',
    };

    const primaryActionButtons = `

        ${supportsDisable ? (status.disabled

            ? `<button type="button" class="cred-btn enable" data-credential-command="enable">${t('action_enable')}</button>`

            : `<button type="button" class="cred-btn disable" data-credential-command="disable">${t('action_disable')}</button>`

        ) : ''}

        ${supportsTest ? `<button type="button" class="cred-btn" data-credential-command="test" title="${escapeAttribute(t('btn_test_model_title'))}">${t('btn_test_model')}</button>` : ''}

        <button type="button" class="cred-btn view" data-credential-command="view" title="${escapeAttribute(t('btn_view_content_title'))}">${t('btn_view_content')}</button>

        ${supportsDelete ? `<button type="button" class="cred-btn delete" data-credential-command="delete">${t('action_delete')}</button>` : ''}

    `;

    const secondaryActionButtons = `

        ${supportsEdit ? `<button type="button" class="cred-btn" data-credential-command="edit">${t('credential_edit_action')}</button>` : ''}

        ${supportsReauthenticate ? `<button type="button" class="cred-btn" data-credential-command="reauthenticate">${t('credential_reauthenticate_action')}</button>` : ''}

        ${supportsExport ? `<button type="button" class="cred-btn download" data-credential-command="download">${t('btn_download')}</button>` : ''}

        ${supportsModelDiscovery && Number(credInfo.model_count) > 0 ? `<button type="button" class="cred-btn" data-credential-command="models" title="${escapeAttribute(t('btn_view_models_title'))}">${t('btn_view_models')}</button>` : ''}

        ${supportsQuotaPreview ? `<button type="button" class="cred-btn" data-credential-command="quota" title="${escapeAttribute(t('btn_view_quota_title'))}">${t('btn_view_quota')}</button>` : ''}

        ${managerType !== 'primary' ? `<button type="button" class="cred-btn" data-credential-command="preview" title="${escapeAttribute(t('btn_setup_preview_title'))}">${t('btn_setup_preview')}</button>` : ''}

        ${supportsVerify ? `<button type="button" class="cred-btn" data-credential-command="verify" title="${escapeAttribute(t('btn_verify_id_title'))}">${t('btn_verify_id')}</button>` : ''}

        <button type="button" class="cred-btn" data-credential-command="errors" title="${escapeAttribute(t('btn_view_errors_title'))}">${t('btn_view_errors')}</button>

    `;

    const checkboxClass = manager.getElementId('file-checkbox');
    const quotaPreview = supportsQuotaPreview ? renderCredentialQuotaPreview(pathId, filename, managerType) : '';

    div.innerHTML = `

        <div class="cred-header">

            <div class="cred-title-row">

                <input type="checkbox" class="${escapeAttribute(checkboxClass)}" data-filename="${escapeAttribute(filename)}" data-credential-select aria-label="${escapeAttribute(`Select ${providerMeta.name} credential for ${accountLabel}`)}">

                <div class="cred-identity" title="${escapeAttribute(filename)}">
                    <div class="cred-provider-logo" aria-hidden="true">${providerLogo}</div>
                    <div class="cred-identity-copy">
                        <div class="cred-provider-name">${escapeHtml(providerMeta.name)}</div>
                        <div class="${accountClass}">${escapeHtml(accountLabel)}</div>
                    </div>
                </div>

                ${quotaPreview}

            </div>

            <div class="cred-status">${statusBadges}</div>

        </div>

        ${credInfo.validation_status === 'unverified' ? `<p class="upload-result-message" data-i18n="provider.ownership.import_unverified_provenance">${escapeHtml(t('provider.ownership.import_unverified_provenance'))}</p>` : ''}

        <div class="cred-actions">
            <div class="cred-actions-primary">${primaryActionButtons}</div>
            <details class="cred-actions-secondary">
                <summary>${t('pool.actions.more')}</summary>
                <div class="cred-actions-secondary-grid">${secondaryActionButtons}</div>
            </details>
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

    div.querySelectorAll('[data-credential-command]').forEach(button => {

        button.addEventListener('click', async function () {

            const command = this.getAttribute('data-credential-command');

            if (command === 'delete') {

                if (!(await showConfirmModal(t('confirm_delete_cred'), {

                    title: t('confirm_delete_cred_title'),

                    confirmLabel: t('action_delete')

                }))) return;

            }

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
            if (command === 'test') {
                await showCredentialModelTest(pathId);
            }
            if (command === 'errors') await toggleErrorDetailsCommon(pathId, manager);


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
