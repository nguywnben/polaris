function updateTabSlider(targetTab, animate = true) {

    const slider = document.querySelector('.tab-slider');

    const tabs = document.querySelector('.tabs');

    if (!slider || !tabs || !targetTab) return;

    const tabLeft = targetTab.offsetLeft;

    const tabWidth = targetTab.offsetWidth;

    const tabsWidth = tabs.scrollWidth;

    const rightValue = tabsWidth - tabLeft - tabWidth;

    if (animate) {

        slider.style.left = `${tabLeft}px`;

        slider.style.right = `${rightValue}px`;

    } else {

        slider.style.transition = 'none';

        slider.style.left = `${tabLeft}px`;

        slider.style.right = `${rightValue}px`;

        slider.offsetHeight;

        slider.style.transition = '';

    }

}

function initTabSlider() {

    const activeTab = document.querySelector('.tab.active');

    if (activeTab) {

        updateTabSlider(activeTab, false);

    }

}

document.addEventListener('DOMContentLoaded', initTabSlider);

function initControlPointerHover() {
    let hoveredControl = null;
    const controlAt = (target) => target instanceof Element ? target.closest('input, select, textarea') : null;
    const setHoveredControl = (control) => {
        if (control === hoveredControl) return;
        hoveredControl?.removeAttribute('data-pointer-hover');
        hoveredControl = control;
        hoveredControl?.setAttribute('data-pointer-hover', '');
    };
    // Native :hover also matches a control when its associated label is hovered.
    // Pointer targets distinguish the actual control, including dynamically added forms.
    document.addEventListener('pointerover', (event) => {
        setHoveredControl(event.pointerType === 'touch' ? null : controlAt(event.target));
    });
    document.addEventListener('pointerout', (event) => {
        setHoveredControl(event.pointerType === 'touch' ? null : controlAt(event.relatedTarget));
    });
    document.addEventListener('pointercancel', () => setHoveredControl(null));
    window.addEventListener('blur', () => setHoveredControl(null));
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) setHoveredControl(null);
    });
}

function controlValidationMessage(field) {
    const validity = field.validity;
    const reason = validity.customError ? field.validationMessage
        : validity.valueMissing ? t('validation.required')
        : validity.tooShort ? t('validation.min_length', {limit: field.minLength})
        : validity.tooLong ? t('validation.max_length', {limit: field.maxLength})
        : validity.rangeUnderflow ? t('validation.min', {limit: field.min})
        : validity.rangeOverflow ? t('validation.max', {limit: field.max})
        : validity.stepMismatch ? t('validation.step', {step: field.step || '1'})
        : validity.typeMismatch || validity.patternMismatch ? t('validation.format')
        : t('validation.invalid');
    const label = field.labels?.[0]?.cloneNode(true);
    label?.querySelectorAll('input, select, textarea, button, small').forEach(node => node.remove());
    const name = (label?.textContent || field.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
    return name ? `${name}: ${reason}` : reason;
}

function initControlValidationFeedback() {
    let firstInvalid = null;
    // Cancel only the browser's presentation, not HTML constraint validation.
    // Capture also covers reportValidity() and forms inserted by dialogs later.
    document.addEventListener('invalid', (event) => {
        event.preventDefault();
        const field = event.target;
        field.setAttribute('aria-invalid', 'true');
        field.setAttribute('data-validation-error', '');
        if (firstInvalid) return;
        firstInvalid = field;
        setTimeout(() => {
            const target = firstInvalid;
            firstInvalid = null;
            if (!target.isConnected || target.validity.valid) return;
            showStatus(controlValidationMessage(target), 'error');
        }, 0);
    }, true);
    const clearEditedError = (event) => {
        const field = event.target;
        if (field.hasAttribute('data-validation-error')) {
            field.removeAttribute('aria-invalid');
            field.removeAttribute('data-validation-error');
        }
    };
    document.addEventListener('input', clearEditedError);
    document.addEventListener('change', clearEditedError);
}

function initStaticUiBindings() {
    initControlPointerHover();
    initControlValidationFeedback();
    initBackupBindings();
    const clickHandlers = {
        'toggle-mobile-menu': () => toggleMobileMenu(),
        'switch-tab': (element) => switchTab(element.dataset.tab),
        'switch-activity-view': (element) => switchActivityView(element.dataset.activityView),
        'clear-activity-filters': () => clearActivityFilters(),
        'investigate-activity-request': (element) => investigateActivityRequest(element.dataset.requestId, 'traces', {navigateToActivity: true}),
        logout: () => logout(),
        'copy-api-key': (element, event) => {
            // A label forwards a click to its input; only a direct pointer hit copies.
            if (event.detail > 0 && document.elementFromPoint(event.clientX, event.clientY) === element) {
                copyInputValue(element.id);
            }
        },
        'toggle-api-key': () => toggleApiKeyVisibility(),
        'toggle-setup-secret': (element) => toggleSetupSecret(element),
        'toggle-login-secret': (element) => toggleSetupSecret(element),
        'regenerate-api-key': () => regenerateApiKey(),
        'virtual-key-create': () => openVirtualKeyForm(),
        'virtual-key-refresh': () => loadVirtualKeys({ announce: true }),
        'virtual-key-edit': (element) => editVirtualKey(element.dataset.keyId),
        'virtual-key-usage': (element) => showVirtualKeyUsage(element.dataset.keyId),
        'virtual-key-rotate': (element) => rotateVirtualKey(element.dataset.keyId),
        'virtual-key-revoke': (element) => revokeVirtualKey(element.dataset.keyId),
        'copy-access-client-example': () => copyAccessClientExample(),
        'identity-refresh': () => loadIdentityConsole({ announce: true }),
        'identity-create': () => openIdentityCreateDialog(),
        'identity-create-close': () => closeIdentityCreateDialog(),
        'identity-toggle': (element) => toggleManagedIdentity(element),
        'identity-role': (element) => updateIdentityRole(element),
        'identity-session-revoke': (element) => revokeIdentitySession(element),
        'identity-oidc-advance': (element) => advanceIdentityOidcPolicy(element),
        'identity-previous-page': () => changeIdentityPage('previous'),
        'identity-next-page': () => changeIdentityPage('next'),
        'identity-session-previous-page': () => changeIdentitySessionPage('previous'),
        'identity-session-next-page': () => changeIdentitySessionPage('next'),
        'identity-confirm-cancel': () => closeIdentityConfirmation(false),
        'identity-confirm-submit': () => closeIdentityConfirmation(true),
        'copy-url': (element) => cpUrl(element),
        'refresh-pool': () => refreshPrimaryCredsList(),
        'select-pool-archive': () => selectPoolImportArchive(),
        'download-pool': () => downloadAllPrimaryCreds(),
        'batch-primary': (element) => batchPrimaryAction(element.dataset.batchAction),
        'batch-verify-primary': () => batchVerifyProviderCredentials(),
        'select-all-matching-primary': () => selectAllMatchingPrimary(),
        'clear-primary-selection': () => clearPrimarySelection(),
        'reset-primary-filters': () => AppState.primaryCreds.resetFilters(),
        'change-primary-page': (element) => changePrimaryPage(Number(element.dataset.pageDelta)),
        'change-usage-page': (element) => changeUsagePage(Number(element.dataset.pageDelta)),
        'change-historical-usage-page': (element) => changeHistoricalUsagePage(Number(element.dataset.pageDelta)),
        'refresh-model-catalog': () => loadModelCatalog(true),
        'save-model-pool': () => saveModelPool(),
        'validate-model-route': () => validateModelRoute({ announce: true }),
        'test-model-route': () => testModelRouteInPlayground(),
        'playground-add-message': () => addPlaygroundMessage(),
        'playground-remove-message': (element) => removePlaygroundMessage(element.dataset.messageIndex),
        'playground-cancel': () => cancelPlayground(),
        'playground-copy-example': () => copyPlaygroundExample(),
        'delete-model-route': () => deleteModelRoute(),
        'clear-model-blacklist': () => clearModelBlacklist(),
        'select-provider': (element) => selectProviderWorkspace(element.dataset.provider),
        'change-provider-catalog-page': (element) => changeProviderCatalogPage(Number(element.dataset.pageDelta)),
        'retry-provider-capabilities': () => retryProviderCapabilities(),
        'select-ai-studio-files': () => document.getElementById('googleAiStudioFileInput')?.click(),
        'upload-ai-studio-files': () => uploadGoogleAiStudioFiles(),
        'clear-ai-studio-files': () => clearGoogleAiStudioFiles(),
        'save-ai-studio-settings': () => saveGoogleAIStudioSettings(),
        'reset-ai-studio-settings': () => resetGoogleAIStudioSettings(),
        'start-xai-oauth': () => startXaiOauth(),
        'save-xai-oauth': () => saveXaiOauth(),
        'select-grok-files': () => document.getElementById('grokFileInput')?.click(),
        'upload-grok-files': () => uploadGrokFiles(),
        'clear-grok-files': () => clearGrokFiles(),
        'select-xai-console-files': () => document.getElementById('xaiConsoleFileInput')?.click(),
        'upload-xai-console-files': () => uploadXaiConsoleFiles(),
        'clear-xai-console-files': () => clearXaiConsoleFiles(),
        'save-grok-settings': () => saveXaiSettings('oauth'),
        'reset-grok-settings': () => resetXaiSettings('oauth'),
        'save-xai-console-settings': () => saveXaiSettings('api'),
        'reset-xai-console-settings': () => resetXaiSettings('api'),
        'start-codex-oauth': () => startCodexOauth(),
        'complete-codex-oauth': () => completeCodexOauth(),
        'select-codex-files': () => document.getElementById('codexFileInput')?.click(),
        'upload-codex-files': () => uploadCodexFiles(),
        'clear-codex-files': () => clearCodexFiles(),
        'select-openai-platform-files': () => document.getElementById('openaiPlatformFileInput')?.click(),
        'upload-openai-platform-files': () => uploadOpenAIPlatformFiles(),
        'clear-openai-platform-files': () => clearOpenAIPlatformFiles(),
        'save-openai-settings': (element) => saveOpenAISettings(element.dataset.openaiScope),
        'reset-openai-settings': (element) => resetOpenAISettings(element.dataset.openaiScope),
        'start-claude-oauth': () => startClaudeOauth(),
        'save-claude-oauth': () => saveClaudeOauth(),
        'select-claude-code-files': () => document.getElementById('claudeCodeFileInput')?.click(),
        'upload-claude-code-files': () => uploadClaudeCodeFiles(),
        'clear-claude-code-files': () => clearClaudeCodeFiles(),
        'select-claude-platform-files': () => document.getElementById('claudePlatformFileInput')?.click(),
        'upload-claude-platform-files': () => uploadClaudePlatformFiles(),
        'clear-claude-platform-files': () => clearClaudePlatformFiles(),
        'save-anthropic-settings': (element) => saveAnthropicSettings(element.dataset.anthropicScope),
        'reset-anthropic-settings': (element) => resetAnthropicSettings(element.dataset.anthropicScope),
        'copy-claude-auth-url': () => cpUrl(document.getElementById('claudeAuthorizationUrl')),
        'select-ollama-files': () => document.getElementById('ollamaFileInput')?.click(),
        'upload-ollama-files': () => uploadOllamaFiles(),
        'clear-ollama-files': () => clearOllamaFiles(),
        'copy-codex-device-code': (element) => {
            cpUrl(element);
            element.blur();
        },
        'copy-codex-verification-url': () => cpUrl(document.getElementById('codexVerificationUrl')),
        'copy-xai-auth-url': () => cpUrl(document.getElementById('xaiAuthorizationUrl')),
        'copy-primary-auth-url': () => cpUrl(document.getElementById('primaryAuthUrl')),
        'get-primary-credentials': () => getPrimaryCredentials(),
        'download-primary-credentials': () => downloadPrimaryCredentials(),
        'select-primary-files': () => document.getElementById('primaryFileInput')?.click(),
        'upload-primary-files': () => uploadPrimaryFiles(),
        'clear-primary-files': () => clearPrimaryFiles(),
        'save-antigravity-settings': () => saveAntigravitySettings(),
        'reset-antigravity-settings': () => resetAntigravitySettings(),
        'save-quality-policy': () => saveQualityPolicy(),
        'reset-quality-policy': () => resetQualityPolicy(),
        'preview-quality-policy': () => previewQualityPolicy(),
        'refresh-audit': () => refreshAuditConsole(),
        'clear-audit-filters': () => clearAuditFilters(),
        'audit-previous-page': () => changeAuditPage('previous'),
        'audit-next-page': () => changeAuditPage('next'),
        'view-audit-detail': (element) => openAuditDetail(element),
        'close-audit-detail': () => closeAuditDetail(),
        'copy-audit-request': () => copyAuditRequest(),
        'pivot-audit-request': () => pivotAuditRequest(),
        'related-trace-request': () => openRelatedTraceRequest(),
        'export-audit': (element) => exportAuditEvents(element.dataset.exportFormat),
        'refresh-traces': () => refreshTraceConsole(),
        'clear-trace-filters': () => clearTraceFilters(),
        'trace-previous-page': () => changeTracePage('previous'),
        'trace-next-page': () => changeTracePage('next'),
        'view-trace-detail': (element) => openTraceDetail(element),
        'close-trace-detail': () => closeTraceDetail(),
        'copy-trace-request': () => copyTraceRequest(),
        'pivot-trace-request': () => pivotTraceRequest(),
        'related-audit-request': () => openRelatedAuditRequest(),
        'export-traces': (element) => exportTraces(element.dataset.exportFormat),
        'save-config': () => saveConfig(),
        'reset-config': () => resetConfig(),
        'set-current-keepalive-url': () => autoSetKeepaliveUrl(),
        'download-logs': () => downloadLogs(),
        'clear-logs': () => clearLogs(),
        'check-updates': () => checkForUpdates()
    };
    const changeHandlers = {
        'model-routing-strategy': () => syncModelRoutingPolicyControls(),
        'playground-protocol': () => syncPlaygroundProtocol(),
        'playground-draft': () => updatePlaygroundExample(),
        'playground-example-format': () => updatePlaygroundExample(),
        'usage-period': (element) => setUsagePeriod(element.value),
        'pool-archive': (_element, event) => handlePoolImportArchive(event),
        'select-all-primary': () => toggleSelectAllPrimary(),
        'primary-filter': () => applyPrimaryStatusFilter(),
        'primary-page-size': () => changePrimaryPageSize(),
        'ai-studio-files': (_element, event) => handleGoogleAiStudioFileSelect(event),
        'grok-files': (_element, event) => handleGrokFileSelect(event),
        'xai-console-files': (_element, event) => handleXaiConsoleFileSelect(event),
        'codex-files': (_element, event) => handleCodexFileSelect(event),
        'openai-platform-files': (_element, event) => handleOpenAIPlatformFileSelect(event),
        'claude-code-files': (_element, event) => handleClaudeCodeFileSelect(event),
        'claude-platform-files': (_element, event) => handleClaudePlatformFileSelect(event),
        'ollama-files': (_element, event) => handleOllamaFileSelect(event),
        'primary-files': (_element, event) => handlePrimaryFileSelect(event),
        'quality-profile': (element) => selectQualityProfile(element.value),
        'virtual-key-status': (element) => updateVirtualKeyStatus(element.value),
        'virtual-key-pricing': (element) => syncVirtualKeyPricingControl(element.form),
        'virtual-key-scope': (element) => syncVirtualKeyScopeControl(element),
        'access-client-protocol': () => renderAccessClientExample(),
        'access-client-format': () => renderAccessClientExample(),
        'log-level': () => filterLogs()
    };

    document.addEventListener('click', (event) => {
        const label = event.target.closest('label');
        const labeledField = label?.control;
        if (labeledField?.matches('input:not([type="checkbox"]):not([type="radio"]), select, textarea')
            && !event.target.closest('input, select, textarea, button, a, [contenteditable="true"], [role="button"]')) {
            // Keep the accessible label association, but only direct field interaction
            // should focus/open it. Checkbox and radio labels retain native activation.
            event.preventDefault();
        }
        const element = event.target.closest('[data-ui-action]');
        if (!element) return;
        const handler = clickHandlers[element.dataset.uiAction];
        if (handler) handler(element, event);
    });

    document.addEventListener('change', (event) => {
        const element = event.target.closest('[data-ui-change]');
        if (!element) return;
        const handler = changeHandlers[element.dataset.uiChange];
        if (handler) handler(element, event);
    });

    document.addEventListener('input', (event) => {
        if (event.target.matches('[data-quality-control]')) {
            syncQualityPolicyControls();
        }
        if (event.target.matches('[data-quality-control], .quality-preview-inputs input')) {
            document.getElementById('qualityPreviewResult')?.classList.add('hidden');
        }
        if (event.target.matches('[data-playground-input], #playgroundForm input')) {
            syncPlaygroundMessagesFromDom();
            updatePlaygroundExample();
        }
        if (event.target.matches('[data-ui-input="model-catalog-search"]')) {
            renderModelCatalog();
        }
        if (event.target.matches('[data-ui-input="provider-catalog-search"]')) {
            filterProviderCatalog(event.target.value);
        }
        if (event.target.matches('[data-ui-input="virtual-key-search"]')) {
            updateVirtualKeySearch(event.target.value);
        }
    });

    document.getElementById('loginForm')?.addEventListener('submit', (event) => {
        event.preventDefault();
        login();
    });
    document.getElementById('setupForm')?.addEventListener('submit', (event) => {
        event.preventDefault();
        completeInitialSetup();
    });
    document.getElementById('setupPreflightButton')?.addEventListener('click', () => {
        runSetupPreflight();
    });
    for (const eventName of ['input', 'change']) {
        document.getElementById('configForm')?.addEventListener(eventName, (event) => {
            if (event.target.matches('.setup-secret-field input') && !event.target.value) {
                setSetupSecretVisibility(event.target, false);
            }
        });
        document.getElementById('loginForm')?.addEventListener(eventName, (event) => {
            if (event.target.id === 'loginPassword' && !event.target.value) {
                setSetupSecretVisibility(event.target, false);
            }
        });
        document.getElementById('setupForm')?.addEventListener(eventName, (event) => {
            if (event.target.id === 'setupToken') invalidateSetupVerification();
            if (event.target.matches('#setupPassword, #setupPasswordConfirm')) {
                renderSetupPasswordChecks();
            }
            if (event.target.matches('.setup-secret-field input') && !event.target.value) {
                setSetupSecretVisibility(event.target, false);
            }
        });
    }
    document.getElementById('googleAiStudioCredentialForm')?.addEventListener('submit', addGoogleAIStudioCredential);
    document.getElementById('xaiCredentialForm')?.addEventListener('submit', addXaiApiKeyCredential);
    document.getElementById('openaiPlatformCredentialForm')?.addEventListener('submit', addOpenAIPlatformCredential);
    document.getElementById('claudePlatformCredentialForm')?.addEventListener('submit', addClaudePlatformCredential);
    document.getElementById('ollamaCredentialForm')?.addEventListener('submit', addOllamaCredential);
    document.getElementById('accessPasswordForm')?.addEventListener('submit', (event) => {
        event.preventDefault();
        saveAccessCredentials();
    });
    document.getElementById('playgroundForm')?.addEventListener('submit', (event) => {
        event.preventDefault();
        runPlayground();
    });

    document.getElementById('apiKey')?.addEventListener('mousedown', (event) => event.preventDefault());
    document.getElementById('apiKey')?.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            copyInputValue('apiKey', {preserveFocus: true});
        }
    });

    for (const [areaId, dropHandler] of [
        ['googleAiStudioUploadArea', handleGoogleAiStudioFileDrop],
        ['grokUploadArea', handleGrokFileDrop],
        ['xaiConsoleUploadArea', handleXaiConsoleFileDrop],
        ['codexUploadArea', handleCodexFileDrop],
        ['openaiPlatformUploadArea', handleOpenAIPlatformFileDrop],
        ['claudeCodeUploadArea', handleClaudeCodeFileDrop],
        ['claudePlatformUploadArea', handleClaudePlatformFileDrop],
        ['ollamaUploadArea', handleOllamaFileDrop],
        ['primaryUploadArea', handlePrimaryFileDrop]
    ]) {
        const area = document.getElementById(areaId);
        area?.addEventListener('dragover', (event) => {
            event.preventDefault();
            area.classList.add('dragover');
        });
        area?.addEventListener('dragleave', () => area.classList.remove('dragover'));
        area?.addEventListener('drop', dropHandler);
    }

    updateProviderCatalogPagination();
}

document.addEventListener('DOMContentLoaded', initStaticUiBindings);

window.addEventListener('resize', () => {

    const activeTab = document.querySelector('.tab.active');

    if (activeTab) updateTabSlider(activeTab, false);

    syncMobileNavigationState();

});

function switchTab(tabName) {

    const route = TAB_MAP[tabName] || '/dashboard';

    navigate(route, true);

}

const PROVIDER_WORKSPACES = {
    google_antigravity: {
        selectorId: 'providerSelectorGoogleAntigravity',
        panelId: 'providerWorkspaceGoogleAntigravity',
        settingsFamily: 'antigravity'
    },
    google_ai_studio: {
        selectorId: 'providerSelectorGoogleAiStudio',
        panelId: 'providerWorkspaceGoogleAiStudio',
        settingsFamily: 'google-ai-studio'
    },
    grok: {
        selectorId: 'providerSelectorGrok',
        panelId: 'providerWorkspaceGrok',
        settingsFamily: 'xai'
    },
    xai_console: {
        selectorId: 'providerSelectorXaiConsole',
        panelId: 'providerWorkspaceXaiConsole',
        settingsFamily: 'xai'
    },
    codex: {
        selectorId: 'providerSelectorCodex',
        panelId: 'providerWorkspaceCodex',
        settingsFamily: 'openai'
    },
    openai_platform: {
        selectorId: 'providerSelectorOpenAiPlatform',
        panelId: 'providerWorkspaceOpenAiPlatform',
        settingsFamily: 'openai'
    },
    claude_code: {
        selectorId: 'providerSelectorClaudeCode',
        panelId: 'providerWorkspaceClaudeCode',
        settingsFamily: 'anthropic'
    },
    claude_platform: {
        selectorId: 'providerSelectorClaudePlatform',
        panelId: 'providerWorkspaceClaudePlatform',
        settingsFamily: 'anthropic'
    },
    ollama: {
        selectorId: 'providerSelectorOllama',
        panelId: 'providerWorkspaceOllama',
        settingsFamily: null
    }
};

const PROVIDER_CATALOG_PAGE_SIZE = 8;
let providerCatalogCurrentPage = 1;
let providerCatalogSearchQuery = '';

function getFilteredProviderCards() {
    const cards = Array.from(document.querySelectorAll('#providerCatalog [data-provider]'));
    const query = providerCatalogSearchQuery.trim().toLowerCase();
    if (!query) return cards;
    return cards.filter((card) => {
        const searchableText = [
            card.dataset.provider,
            card.dataset.providerName,
            card.textContent
        ].join(' ').toLowerCase();
        return searchableText.includes(query);
    });
}

function updateProviderCatalogPagination() {
    const allCards = Array.from(document.querySelectorAll('#providerCatalog [data-provider]'));
    const filteredCards = getFilteredProviderCards();
    const totalItems = filteredCards.length;
    const totalPages = Math.max(1, Math.ceil(totalItems / PROVIDER_CATALOG_PAGE_SIZE));

    if (providerCatalogCurrentPage > totalPages) {
        providerCatalogCurrentPage = totalPages;
    }
    if (providerCatalogCurrentPage < 1) {
        providerCatalogCurrentPage = 1;
    }

    const startIndex = (providerCatalogCurrentPage - 1) * PROVIDER_CATALOG_PAGE_SIZE;
    const endIndex = startIndex + PROVIDER_CATALOG_PAGE_SIZE;
    const visibleCards = new Set(filteredCards.slice(startIndex, endIndex));
    const tabStop = [...visibleCards].find(card => card.getAttribute('aria-selected') === 'true')
        || visibleCards.values().next().value;

    allCards.forEach((card) => {
        const isVisible = visibleCards.has(card);
        card.classList.toggle('hidden', !isVisible);
        card.setAttribute('aria-hidden', String(!isVisible));
        card.tabIndex = card === tabStop ? 0 : -1;
    });

    const emptyElement = document.getElementById('providerCatalogEmpty');
    if (emptyElement) {
        emptyElement.classList.toggle('hidden', totalItems > 0);
    }

    const paginationContainer = document.getElementById('providerCatalogPagination');
    const prevButton = document.getElementById('providerCatalogPrevBtn');
    const nextButton = document.getElementById('providerCatalogNextBtn');
    const infoElement = document.getElementById('providerCatalogPaginationInfo');

    if (paginationContainer) {
        paginationContainer.style.display = totalPages > 1 ? 'flex' : 'none';
    }
    if (prevButton) {
        prevButton.disabled = providerCatalogCurrentPage <= 1;
    }
    if (nextButton) {
        nextButton.disabled = providerCatalogCurrentPage >= totalPages;
    }
    if (infoElement) {
        infoElement.textContent = t('pagination.page_of', {
            page: providerCatalogCurrentPage,
            total: totalPages
        });
    }
}

function changeProviderCatalogPage(delta) {
    const filteredCards = getFilteredProviderCards();
    const totalPages = Math.max(1, Math.ceil(filteredCards.length / PROVIDER_CATALOG_PAGE_SIZE));
    const targetPage = providerCatalogCurrentPage + delta;
    if (targetPage >= 1 && targetPage <= totalPages) {
        providerCatalogCurrentPage = targetPage;
        updateProviderCatalogPagination();
    }
}

function filterProviderCatalog(value = '') {
    providerCatalogSearchQuery = String(value || '');
    providerCatalogCurrentPage = 1;
    updateProviderCatalogPagination();
}

function selectProviderWorkspace(providerId, focusSelector = false) {
    const selected = PROVIDER_WORKSPACES[providerId];
    if (!selected) return;

    AppState.activeProviderWorkspace = providerId;

    const filteredCards = getFilteredProviderCards();
    const targetCard = document.getElementById(selected.selectorId);
    if (targetCard && filteredCards.includes(targetCard)) {
        const cardIndex = filteredCards.indexOf(targetCard);
        const cardPage = Math.floor(cardIndex / PROVIDER_CATALOG_PAGE_SIZE) + 1;
        if (cardPage !== providerCatalogCurrentPage) {
            providerCatalogCurrentPage = cardPage;
            updateProviderCatalogPagination();
        }
    }

    Object.entries(PROVIDER_WORKSPACES).forEach(([id, workspace]) => {
        const selector = document.getElementById(workspace.selectorId);
        const panel = document.getElementById(workspace.panelId);
        const isActive = id === providerId;

        selector?.classList.toggle('active', isActive);
        selector?.setAttribute('aria-selected', String(isActive));
        if (selector) selector.tabIndex = isActive ? 0 : -1;
        panel?.classList.toggle('hidden', !isActive);
    });

    if (focusSelector) {
        const selector = document.getElementById(selected.selectorId);
        selector?.focus();
        selector?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    }
}

function initProviderWorkspaceSelector() {
    const providerIds = Object.keys(PROVIDER_WORKSPACES);

    providerIds.forEach((providerId) => {
        const selector = document.getElementById(PROVIDER_WORKSPACES[providerId].selectorId);
        selector?.addEventListener('keydown', (event) => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault();

            const visibleProviderIds = providerIds.filter((id) => {
                const candidate = document.getElementById(PROVIDER_WORKSPACES[id].selectorId);
                return candidate && !candidate.classList.contains('hidden');
            });
            if (!visibleProviderIds.length) return;

            const currentIndex = Math.max(0, visibleProviderIds.indexOf(providerId));
            let nextIndex = currentIndex;
            if (event.key === 'ArrowLeft') {
                nextIndex = (currentIndex - 1 + visibleProviderIds.length) % visibleProviderIds.length;
            }
            if (event.key === 'ArrowRight') {
                nextIndex = (currentIndex + 1) % visibleProviderIds.length;
            }
            if (event.key === 'Home') nextIndex = 0;
            if (event.key === 'End') nextIndex = visibleProviderIds.length - 1;

            selectProviderWorkspace(visibleProviderIds[nextIndex], true);
        });
    });

    selectProviderWorkspace(AppState.activeProviderWorkspace);
}

document.addEventListener('DOMContentLoaded', initProviderWorkspaceSelector);

const MODEL_PROVIDER_META = {
    google_antigravity: {
        name: 'Google Antigravity',
        logo: '/frontend/assets/providers/google-antigravity-logo.png'
    },
    google_ai_studio: {
        name: 'Google AI Studio',
        logo: '/frontend/assets/providers/google-ai-studio-logo.png'
    },
    grok: {
        name: 'Grok Build',
        logo: '/frontend/assets/providers/grok-build-logo.png'
    },
    xai_console: {
        name: 'SpaceXAI Console',
        logo: '/frontend/assets/providers/spacexai-console-logo.png'
    },
    codex: {
        name: 'Codex',
        logo: '/frontend/assets/providers/codex-logo.png'
    },
    openai_platform: {
        name: 'OpenAI Platform',
        logo: '/frontend/assets/providers/openai-platform-logo.png'
    },
    claude_code: {
        name: 'Claude Code',
        logo: '/frontend/assets/providers/claude-code-logo.png'
    },
    claude_platform: {
        name: 'Claude Platform',
        logo: '/frontend/assets/providers/claude-platform-logo.png'
    },
    anthropic: {
        name: 'Anthropic',
        logo: '/frontend/assets/providers/claude-platform-logo.png'
    },
    ollama: {
        name: 'Ollama',
        logo: '/frontend/assets/providers/ollama-logo.png'
    },
    xai: {
        name: 'Grok Build',
        logo: '/frontend/assets/providers/grok-build-logo.png'
    },
    openai: {
        name: 'OpenAI Platform',
        logo: '/frontend/assets/providers/openai-platform-logo.png'
    }
};
