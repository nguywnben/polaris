function createCredsManager(type) {

    const modeParam = type === 'primary' ? 'mode=provider' : 'mode=code_assist';

    return {

        type: type,

        data: {},

        filteredData: {},

        currentPage: 1,

        pageSize: 20,

        selectedFiles: new Set(),

        totalCount: 0,

        hasLoaded: false,

        currentStatusFilter: 'all',

        currentErrorCodeFilter: 'all',

        currentCooldownFilter: 'all',

        currentPreviewFilter: 'all',

        currentTierFilter: 'all',

        currentProviderFilter: 'all',

        currentCredentialKindFilter: 'all',

        currentHealthFilter: 'all',

        currentQuotaStateFilter: 'all',

        currentSourceFilter: 'all',

        filtersRestored: false,

        selectionScope: 'page',

        allMatchingSelection: null,

        facets: {},

        capabilityByVariant: {},

        capabilityCatalogPromise: null,

        statsData: { total: 0, normal: 0, disabled: 0 },

        getEndpoint: (action) => {

            const endpoints = {

                status: `./api/credentials/status`,

                action: `./api/credentials/action`,

                batchAction: `./api/credentials/batch-action`,

                download: `./api/credentials/download`,

                downloadAll: `./api/credentials/download-all`,

                detail: `./api/credentials/detail`,

                models: `./api/credentials/models`,

                refreshAllEmails: `./api/credentials/refresh-all-emails`,

                deduplicate: `./api/credentials/deduplicate-by-email`,

                verify: `./api/credentials/verify`,

                quota: `./api/credentials/quota`

            };

            return endpoints[action] || '';

        },

        async loadCapabilityCatalog() {

            if (this.type !== 'primary' || Object.keys(this.capabilityByVariant).length > 0) return;

            if (!this.capabilityCatalogPromise) {

                this.capabilityCatalogPromise = fetch('./api/providers/capabilities', { headers: getAuthHeaders() })

                    .then(async (response) => {

                        if (!response.ok) throw new Error('capability_catalog_unavailable');

                        const catalog = await response.json();

                        this.capabilityByVariant = Object.fromEntries(

                            (catalog.credential_variants || []).map(variant => [variant.variant_id, variant])

                        );

                    })

                    .catch(() => {

                        this.capabilityByVariant = {};

                    })

                    .finally(() => {

                        this.capabilityCatalogPromise = null;

                    });

            }

            await this.capabilityCatalogPromise;

        },

        getModeParam: () => modeParam,

        getFilterDefinitions() {

            return {

                provider: { state: 'currentProviderFilter', suffix: 'ProviderFilter', values: ['all', 'google_antigravity', 'google_ai_studio', 'grok', 'xai_console', 'codex', 'openai_platform', 'claude_code', 'claude_platform', 'ollama'] },

                status: { state: 'currentStatusFilter', suffix: 'StatusFilter', values: ['all', 'enabled', 'disabled'] },

                error: { state: 'currentErrorCodeFilter', suffix: 'ErrorCodeFilter', values: ['all', 'none', '400', '401', '403', '429', '500', '502', '503'], advanced: true },

                cooldown: { state: 'currentCooldownFilter', suffix: 'CooldownFilter', values: ['all', 'in_cooldown', 'no_cooldown'], advanced: true },

                tier: { state: 'currentTierFilter', suffix: 'TierFilter', values: ['all', 'free', 'pro', 'ultra', 'not_applicable'], advanced: true },

                kind: { state: 'currentCredentialKindFilter', suffix: 'CredentialKindFilter', values: ['all', 'oauth', 'api_key', 'connection'], advanced: true },

                health: { state: 'currentHealthFilter', suffix: 'HealthFilter', values: ['all', 'healthy', 'degraded', 'unhealthy', 'disabled'] },

                quota: { state: 'currentQuotaStateFilter', suffix: 'QuotaStateFilter', values: ['all', 'available', 'limited', 'exhausted', 'unsupported'], advanced: true },

                source: { state: 'currentSourceFilter', suffix: 'SourceFilter', values: ['all', 'managed', 'environment'], advanced: true }

            };

        },

        restoreFilterState() {

            if (this.filtersRestored || this.type !== 'primary') return;

            this.filtersRestored = true;

            let stored = {};

            try {

                const raw = sessionStorage.getItem('omni.pool.filters.v1') || '';

                if (raw.length <= 512) stored = JSON.parse(raw) || {};

            } catch (_error) {

                stored = {};

            }

            const params = new URLSearchParams(window.location.search);

            Object.entries(this.getFilterDefinitions()).forEach(([key, definition]) => {

                const candidate = params.get(`pool_${key}`) || stored[key] || 'all';

                const value = definition.values.includes(candidate) ? candidate : 'all';

                this[definition.state] = value;

                const element = document.getElementById(this.getElementId(definition.suffix));

                if (element) element.value = value;

            });

            const pageSize = Number(params.get('pool_page_size') || stored.pageSize);

            if ([20, 50, 100, 200].includes(pageSize)) this.pageSize = pageSize;

            const page = Number(params.get('pool_page') || stored.page);

            if (Number.isInteger(page) && page >= 1 && page <= 10000) this.currentPage = page;

            const pageSizeElement = document.getElementById(this.getElementId('PageSizeSelect'));

            if (pageSizeElement) pageSizeElement.value = String(this.pageSize);

            this.updateActiveFilterSummary();

        },

        persistFilterState() {

            if (this.type !== 'primary') return;

            const state = {};

            const url = new URL(window.location.href);

            Object.entries(this.getFilterDefinitions()).forEach(([key, definition]) => {

                const value = definition.values.includes(this[definition.state]) ? this[definition.state] : 'all';

                state[key] = value;

                if (value === 'all') url.searchParams.delete(`pool_${key}`);

                else url.searchParams.set(`pool_${key}`, value);

            });

            state.pageSize = this.pageSize;

            state.page = this.currentPage;

            if (this.pageSize === 20) url.searchParams.delete('pool_page_size');

            else url.searchParams.set('pool_page_size', String(this.pageSize));

            if (this.currentPage === 1) url.searchParams.delete('pool_page');

            else url.searchParams.set('pool_page', String(this.currentPage));

            try {

                const serialized = JSON.stringify(state);

                if (serialized.length <= 512) sessionStorage.setItem('omni.pool.filters.v1', serialized);

            } catch (_error) {

                // Session persistence is optional in privacy-restricted browsers.

            }

            window.history.replaceState(window.history.state, '', url);

        },

        getElementId: (suffix) => {

            if (type === 'primary') {

                return 'primary' + suffix.charAt(0).toUpperCase() + suffix.slice(1);

            }

            return suffix.charAt(0).toLowerCase() + suffix.slice(1);

        },

        async refresh(options = {}) {

            const loading = document.getElementById(this.getElementId('CredsLoading'));

            const list = document.getElementById(this.getElementId('CredsList'));

            const stateHost = this.getElementId('CredsState');

            const preserveContent = options.preserveContent ?? this.hasLoaded;

            clearPageState(stateHost);

            try {

                this.restoreFilterState();

                await this.loadCapabilityCatalog();

                if (loading && !preserveContent) loading.hidden = false;

                if (!preserveContent) list.innerHTML = '';

                const offset = (this.currentPage - 1) * this.pageSize;

                const errorCodeFilter = this.currentErrorCodeFilter || 'all';

                const cooldownFilter = this.currentCooldownFilter || 'all';

                const previewFilter = this.currentPreviewFilter || 'all';

                const tierFilter = this.currentTierFilter || 'all';

                const providerFilter = this.currentProviderFilter || 'all';

                const credentialKindFilter = this.currentCredentialKindFilter || 'all';

                const healthFilter = this.currentHealthFilter || 'all';

                const quotaStateFilter = this.currentQuotaStateFilter || 'all';

                const sourceFilter = this.currentSourceFilter || 'all';

                const query = new URLSearchParams({

                    offset: String(offset),

                    limit: String(this.pageSize),

                    status_filter: this.currentStatusFilter,

                    error_code_filter: errorCodeFilter,

                    cooldown_filter: cooldownFilter,

                    preview_filter: previewFilter,

                    tier_filter: tierFilter,

                    provider_filter: providerFilter,

                    credential_kind_filter: credentialKindFilter,

                    health_filter: healthFilter,

                    quota_state_filter: quotaStateFilter,

                    source_filter: sourceFilter

                });

                query.set('mode', this.type === 'primary' ? 'provider' : 'code_assist');

                const response = await fetch(

                    `${this.getEndpoint('status')}?${query.toString()}`,

                    { headers: getAuthHeaders() }

                );

                const data = await response.json();

                if (response.ok) {

                    const totalPages = Math.max(1, Math.ceil(Number(data.total || 0) / this.pageSize));

                    if (this.currentPage > totalPages) {

                        this.currentPage = totalPages;

                        this.persistFilterState();

                        await this.refresh({ preserveContent });

                        return;

                    }

                    clearPageState(stateHost);

                    this.data = {};

                    data.items.forEach(item => {

                        this.data[item.filename] = {

                            filename: item.filename,

                            status: {

                                disabled: item.disabled,

                                error_codes: item.error_codes || [],

                                last_success: item.last_success,

                            },

                            user_email: item.user_email,

                            credential_label: item.credential_label,

                            credential_type: item.credential_type,

                            provider: item.provider,

                            provider_variant: item.provider_variant,

                            model_count: Number.isFinite(Number(item.model_count)) ? Number(item.model_count) : 0,

                            model_cooldowns: item.model_cooldowns || {},

                            preview: item.preview,

                            tier: item.tier || 'pro',

                            enable_credit: !!item.enable_credit,

                            health: item.health || 'healthy',

                            cooldown_state: item.cooldown_state || 'no_cooldown',

                            quota_state: item.quota_state || 'unsupported',

                            source: item.source || 'managed'

                        };

                    });

                    this.totalCount = data.total;

                    this.facets = data.facets || {};

                    this.allMatchingSelection = data.selection || null;

                    this.retainVisibleSelection();

                    this.hasLoaded = true;

                    if (data.stats) {

                        this.statsData = data.stats;

                    } else {

                        this.calculateStats();

                    }

                    this.updateStatsDisplay();

                    this.filteredData = this.data;

                    this.renderList();

                    this.updatePagination();

                    const credentialLabel = `${data.total} ${t('credential')}`;
                    let msg = t('status_loaded_creds', {credentials: credentialLabel});

                    if (this.currentStatusFilter !== 'all') {

                        msg += t('status_filter_suffix', {filter: this.currentStatusFilter === 'enabled' ? t('enable_only') : t('disable_only')});

                    }

                    // showStatus(msg, 'success');

                } else {

                    throw new Error(data.detail || data.error || t('unknown_error'));

                }

            } catch (error) {

                const message = t('status_load_failed', {error: error.message || t('unknown_error')});

                showPageState(stateHost, {

                    kind: preserveContent ? 'stale' : 'error',

                    title: t(preserveContent ? 'warning' : 'error'),

                    message,

                    actionLabel: t('refresh'),

                    onAction: () => this.refresh({preserveContent: this.hasLoaded})

                });

                showStatus(message, 'error');

            } finally {

                if (loading) loading.hidden = true;

            }

        },

        calculateStats() {

            this.statsData = { total: this.totalCount, normal: 0, disabled: 0 };

            Object.values(this.data).forEach(credInfo => {

                if (credInfo.status.disabled) {

                    this.statsData.disabled++;

                } else {

                    this.statsData.normal++;

                }

            });

        },

        updateStatsDisplay() {

            document.getElementById(this.getElementId('StatTotal')).textContent = this.statsData.total;

            document.getElementById(this.getElementId('StatNormal')).textContent = this.statsData.normal;

            document.getElementById(this.getElementId('StatDisabled')).textContent = this.statsData.disabled;

        },

        renderList() {

            const list = document.getElementById(this.getElementId('CredsList'));

            list.innerHTML = '';
            list.classList.remove('is-empty');

            const entries = Object.entries(this.filteredData);

            if (entries.length === 0) {

                const msg = this.totalCount === 0 ? t('status_no_creds') : t('status_no_filter_data');

                list.classList.add('is-empty');

                const emptyState = document.createElement('div');
                emptyState.className = 'creds-empty-state';
                emptyState.textContent = msg;
                list.appendChild(emptyState);

                document.getElementById(this.getElementId('PaginationContainer')).style.display = 'none';

                this.updateBatchControls();

                return;

            }

            if (this.type === 'primary') {

                const providerGroups = new Map();

                entries.forEach(([, credInfo]) => {

                    const providerMeta = getCredentialProviderMeta(credInfo, this.type);

                    if (!providerGroups.has(providerMeta.id)) {

                        providerGroups.set(providerMeta.id, { providerMeta, credentials: [] });

                    }

                    providerGroups.get(providerMeta.id).credentials.push(credInfo);

                });

                providerGroups.forEach(({ providerMeta, credentials }) => {

                    list.appendChild(createCredentialProviderGroup(providerMeta, credentials, this));

                });

            } else {

                entries.forEach(([, credInfo]) => {

                    list.appendChild(createCredCard(credInfo, this));

                });

            }

            document.getElementById(this.getElementId('PaginationContainer')).style.display =

                this.getTotalPages() > 1 ? 'flex' : 'none';

            this.updateBatchControls();

        },

        getTotalPages() {

            return Math.ceil(this.totalCount / this.pageSize);

        },

        updatePagination() {

            const totalPages = this.getTotalPages();

            const startItem = (this.currentPage - 1) * this.pageSize + 1;

            const endItem = Math.min(this.currentPage * this.pageSize, this.totalCount);

            document.getElementById(this.getElementId('PaginationInfo')).textContent =

                t('status_page_info', {
                    page: formatConsoleNumber(this.currentPage),
                    total: formatConsoleNumber(totalPages),
                    start: formatConsoleNumber(startItem),
                    end: formatConsoleNumber(endItem),
                    count: formatConsoleNumber(this.totalCount)
                });

            document.getElementById(this.getElementId('PrevPageBtn')).disabled = this.currentPage <= 1;

            document.getElementById(this.getElementId('NextPageBtn')).disabled = this.currentPage >= totalPages;

        },

        changePage(direction) {

            const newPage = this.currentPage + direction;

            if (newPage >= 1 && newPage <= this.getTotalPages()) {

                if (this.selectionScope === 'page') this.clearSelection();

                this.currentPage = newPage;

                this.persistFilterState();

                this.refresh();

            }

        },

        changePageSize() {

            this.pageSize = parseInt(document.getElementById(this.getElementId('PageSizeSelect')).value);

            this.currentPage = 1;

            if (this.selectionScope === 'page') this.clearSelection();

            this.persistFilterState();

            this.updateActiveFilterSummary();

            this.refresh();

        },

        resetFilters() {

            Object.values(this.getFilterDefinitions()).forEach((definition) => {

                this[definition.state] = 'all';

                const element = document.getElementById(this.getElementId(definition.suffix));

                if (element) element.value = 'all';

            });

            this.currentPage = 1;

            this.clearSelection();

            const disclosure = document.getElementById('primaryAdvancedFilters');

            if (disclosure) disclosure.open = false;

            this.persistFilterState();

            this.updateActiveFilterSummary();

            this.refresh();

        },

        updateActiveFilterSummary() {

            if (this.type !== 'primary') return;

            const activeCount = Object.values(this.getFilterDefinitions())

                .filter((definition) => this[definition.state] !== 'all').length;

            const countElement = document.getElementById('primaryActiveFilterCount');

            if (countElement) {

                countElement.textContent = activeCount > 0

                    ? t('pool.filters.active', { count: formatConsoleNumber(activeCount) })

                    : t('pool.filters.none');

            }

            const disclosure = document.getElementById('primaryAdvancedFilters');

            const hasAdvancedFilter = Object.values(this.getFilterDefinitions()).some(

                (definition) => definition.advanced && this[definition.state] !== 'all'

            );

            if (disclosure && hasAdvancedFilter) disclosure.open = true;

        },

        retainVisibleSelection() {

            if (this.selectionScope !== 'page') return;

            const visibleFiles = new Set(Object.keys(this.data));

            this.selectedFiles = new Set(

                Array.from(this.selectedFiles).filter(filename => visibleFiles.has(filename))

            );

        },

        applyStatusFilter() {

            Object.values(this.getFilterDefinitions()).forEach((definition) => {

                const element = document.getElementById(this.getElementId(definition.suffix));

                if (element && definition.values.includes(element.value)) {

                    this[definition.state] = element.value;

                }

            });

            this.clearSelection();

            this.currentPage = 1;

            this.persistFilterState();

            this.updateActiveFilterSummary();

            this.refresh();

        },

        clearSelection() {

            this.selectionScope = 'page';

            this.selectedFiles.clear();

            this.updateBatchControls();

        },

        selectAllMatching() {

            if (!this.allMatchingSelection?.token || this.allMatchingSelection.matching_count < 1) return;

            this.selectionScope = 'all_matching';

            this.selectedFiles.clear();

            this.updateBatchControls();

        },

        toggleFileSelection(filename) {

            if (this.selectionScope === 'all_matching') {

                this.selectionScope = 'page';

                this.selectedFiles = new Set(Object.keys(this.data));

            }

            if (this.selectedFiles.has(filename)) this.selectedFiles.delete(filename);

            else this.selectedFiles.add(filename);

            this.updateBatchControls();

        },

        toggleVisibleSelection(checked) {

            this.selectionScope = 'page';

            this.selectedFiles.clear();

            if (checked) Object.keys(this.data).forEach(filename => this.selectedFiles.add(filename));

            this.updateBatchControls();

        },

        getSelectedVariantIds() {

            if (this.selectionScope === 'all_matching') {

                return Object.keys(this.facets.provider_variant || {});

            }

            return [...new Set(

                Array.from(this.selectedFiles)

                    .map(filename => this.data[filename]?.provider_variant)

                    .filter(Boolean)

            )];

        },

        credentialSupportsOperation(credential, operation) {

            if (this.type !== 'primary') return true;

            const variantId = String(credential?.provider_variant || '').trim();

            return (this.capabilityByVariant[variantId]?.operations || []).includes(operation);

        },

        selectedVariantsSupport(operation) {

            const variants = this.getSelectedVariantIds();

            return variants.length > 0 && variants.every((variantId) => (

                (this.capabilityByVariant[variantId]?.operations || []).includes(operation)

            ));

        },

        getBatchTargetPayload() {

            if (this.selectionScope === 'all_matching') {

                return { selection_token: this.allMatchingSelection?.token || '' };

            }

            return { filenames: Array.from(this.selectedFiles) };

        },

        updateBatchControls() {

            const allMatching = this.selectionScope === 'all_matching';

            const selectedCount = allMatching

                ? Number(this.allMatchingSelection?.matching_count || 0)

                : this.selectedFiles.size;

            document.getElementById(this.getElementId('SelectedCount')).textContent = allMatching

                ? t('pool.selection.selected_all', {count: formatConsoleNumber(selectedCount)})

                : t('pool.selection.selected_page', {count: formatConsoleNumber(selectedCount)});

            const batchBtnNames = ['Enable', 'Disable', 'Delete', 'Verify', 'Preview'];

            if (this.type === 'primary') {

                batchBtnNames.push('EnableCredit');

                batchBtnNames.push('DisableCredit');

            }

            const batchBtns = batchBtnNames.map(action =>

                document.getElementById(this.getElementId(`Batch${action}Btn`))

            );

            batchBtns.forEach(btn => btn && (btn.disabled = selectedCount === 0));

            if (this.type === 'primary') {

                const targetLimitExceeded = selectedCount > 100;

                const operationButtons = {

                    Enable: 'toggle',

                    Disable: 'toggle',

                    Delete: 'delete',

                    EnableCredit: 'credit_mode',

                    DisableCredit: 'credit_mode'

                };

                Object.entries(operationButtons).forEach(([actionName, operation]) => {

                    const button = document.getElementById(this.getElementId(`Batch${actionName}Btn`));

                    if (!button) return;

                    const supported = this.selectedVariantsSupport(operation);

                    button.hidden = selectedCount > 0 && !supported;

                    button.disabled = selectedCount === 0 || targetLimitExceeded || !supported;

                    button.title = targetLimitExceeded

                        ? t('pool.operation.limit')

                        : (!supported && selectedCount > 0 ? t('pool.operation.unsupported') : '');

                });

                const verifyButton = document.getElementById(this.getElementId('BatchVerifyBtn'));

                if (verifyButton) {

                    const supported = this.selectedVariantsSupport('verify');

                    verifyButton.hidden = selectedCount > 0 && (allMatching || !supported);

                    verifyButton.disabled = selectedCount === 0 || targetLimitExceeded || allMatching || !supported;

                    verifyButton.title = allMatching

                        ? t('pool.operation.verify_page_only')

                        : (!supported && selectedCount > 0 ? t('pool.operation.unsupported') : '');

                }

            }

            const selectAllCheckbox = document.getElementById(this.getElementId('SelectAllCheckbox'));

            const selectAllMatchingButton = document.getElementById(this.getElementId('SelectAllMatchingBtn'));

            const clearSelectionButton = document.getElementById(this.getElementId('ClearSelectionBtn'));

            if (clearSelectionButton) clearSelectionButton.hidden = selectedCount === 0;

            if (!selectAllCheckbox) return;

            const checkboxes = document.querySelectorAll(`.${this.getElementId('file-checkbox')}`);

            const currentPageSelectedCount = Array.from(checkboxes)

                .filter(cb => this.selectedFiles.has(cb.getAttribute('data-filename'))).length;

            if (allMatching) {

                selectAllCheckbox.indeterminate = false;

                selectAllCheckbox.checked = true;

            } else if (currentPageSelectedCount === 0) {

                selectAllCheckbox.indeterminate = false;

                selectAllCheckbox.checked = false;

            } else if (currentPageSelectedCount === checkboxes.length) {

                selectAllCheckbox.indeterminate = false;

                selectAllCheckbox.checked = true;

            } else {

                selectAllCheckbox.indeterminate = true;

            }

            checkboxes.forEach(cb => {

                cb.checked = allMatching || this.selectedFiles.has(cb.getAttribute('data-filename'));

            });

            if (selectAllMatchingButton) {

                const pageIsSelected = checkboxes.length > 0 && currentPageSelectedCount === checkboxes.length;

                selectAllMatchingButton.hidden = allMatching

                    || !pageIsSelected

                    || selectedCount >= this.totalCount

                    || !this.allMatchingSelection?.token;

                selectAllMatchingButton.textContent = t('pool.selection.select_all_matching', {count: formatConsoleNumber(this.totalCount)});

            }

        },

        describeSelectionQuery() {

            if (this.selectionScope !== 'all_matching') return '';

            const filters = Object.values(this.getFilterDefinitions()).flatMap((definition) => {

                if (this[definition.state] === 'all') return [];

                const element = document.getElementById(this.getElementId(definition.suffix));

                const label = document.querySelector(`label[for="${this.getElementId(definition.suffix)}"]`)?.textContent?.trim();

                const value = element?.selectedOptions?.[0]?.textContent?.trim() || this[definition.state];

                return [`${label || definition.suffix}: ${value}`];

            });

            const filterSummary = filters.length > 0 ? filters.join(', ') : t('pool.batch.query_all');

            const fingerprint = this.allMatchingSelection?.query_fingerprint || t('pool.batch.query_fingerprint_unavailable');

            return [

                t('pool.batch.query_filters', { filters: filterSummary }),

                t('pool.batch.query_fingerprint', { fingerprint })

            ].join('\n');

        },

        async action(filename, action) {

            try {

                const response = await fetch(`${this.getEndpoint('action')}?${this.getModeParam()}`, {

                    method: 'POST',

                    headers: getAuthHeaders(),

                    body: JSON.stringify({ filename, action })

                });

                const data = await response.json();

                if (response.ok) {

                    showStatus(data.message || t('status_action_success', {action: action}), 'success');

                    if (action === 'delete') {

                        this.selectedFiles.delete(filename);

                        delete AppState.quotaPreviewCache[filename];

                        Object.entries(AppState.credentialCardIndex).forEach(([pathId, context]) => {

                            if (context.filename === filename) delete AppState.credentialCardIndex[pathId];

                        });

                        this.updateBatchControls();

                    }

                    await this.refresh();

                    if (action === 'delete') await refreshUsageStats();

                } else {

                    showStatus(t('status_action_failed', {error: data.detail || data.error || t('unknown_error')}), 'error');

                }

            } catch (error) {

                showStatus(t('status_net_error', {error: error.message}), 'error');

            }

        },

        formatBatchResults(data) {

            const counts = data.outcome_counts || {};

            const lines = [

                t('pool.batch.result_summary', {

                    success: data.success_count || 0,

                    total: data.total_count || 0

                })

            ];

            const itemResults = data.results || [];

            itemResults.slice(0, 12).forEach((item) => {

                lines.push(`${item.filename || `#${item.target_index + 1}`}: ${t(`pool.batch.outcome.${item.status}`)}`);

            });

            if (itemResults.length > 12) {

                lines.push(t('pool.batch.more_results', {count: formatConsoleNumber(itemResults.length - 12)}));

            }

            if ((counts.timed_out || 0) + (counts.failed || 0) + (counts.not_found || 0) > 0) {

                lines.push('', t('pool.batch.recovery'));

            }

            return lines.join('\n');

        },

        async batchAction(action) {

            const targetCount = this.selectionScope === 'all_matching'

                ? Number(this.allMatchingSelection?.matching_count || 0)

                : this.selectedFiles.size;

            if (targetCount === 0) {

                showStatus(t('please_select_the_files_to_operate'), 'error');

                return;

            }

            const actionNames = {

                enable: t('action_enable'),

                disable: t('action_disable'),

                delete: t('action_delete'),

                enable_credit: t('action_enable_credit'),

                disable_credit: t('action_disable_credit')

            };

            const confirmationTitles = {

                enable: t('confirm_batch_enable_title'),

                disable: t('confirm_batch_disable_title'),

                delete: t('confirm_batch_delete_title'),

                enable_credit: t('confirm_batch_enable_credit_title'),

                disable_credit: t('confirm_batch_disable_credit_title')

            };

            const formattedTargetCount = formatConsoleNumber(targetCount);
            const confirmationMessages = {

                enable: t('confirm_batch_enable', {count: formattedTargetCount}),

                disable: t('confirm_batch_disable', {count: formattedTargetCount}),

                delete: t('confirm_batch_delete', {count: formattedTargetCount}),

                enable_credit: t('confirm_batch_enable_credit', {count: formattedTargetCount}),

                disable_credit: t('confirm_batch_disable_credit', {count: formattedTargetCount})

            };

            const actionLabel = actionNames[action] || action;

            const confirmOptions = {

                title: confirmationTitles[action] || t('confirm_manage_credentials_title'),

                confirmLabel: actionLabel

            };

            try {

                showStatus(t('status_batch_in_progress', {action: actionLabel}), 'info');

                const previewResponse = await fetch(`${this.getEndpoint('batchAction')}?${this.getModeParam()}`, {

                    method: 'POST',

                    headers: getAuthHeaders(),

                    body: JSON.stringify({ action, ...this.getBatchTargetPayload(), preview: true })

                });

                const previewData = await previewResponse.json();

                if (!previewResponse.ok) {

                    const previewError = previewData.error?.code === 'credential_selection_expired'

                        ? t('pool.batch.refresh_selection')

                        : (previewData.error?.message || previewData.detail || t('unknown_error'));

                    showStatus(t('status_batch_failed', {error: previewError}), 'error');

                    return;

                }

                const eligibleCount = previewData.outcome_counts?.eligible || 0;

                const skippedCount = (previewData.total_count || 0) - eligibleCount;

                const previewSummary = t('pool.batch.preview_summary', {

                    eligible: eligibleCount,

                    skipped: skippedCount,

                    total: previewData.total_count || targetCount

                });

                const selectionQuery = this.describeSelectionQuery();

                const confirmMsg = [selectionQuery, previewSummary, confirmationMessages[action] || actionLabel]

                    .filter(Boolean)

                    .join('\n\n');

                if (!(await showConfirmModal(confirmMsg, confirmOptions))) return;

                const idempotencyKey = crypto.randomUUID();

                const response = await fetch(`${this.getEndpoint('batchAction')}?${this.getModeParam()}`, {

                    method: 'POST',

                    headers: getAuthHeaders(),

                    body: JSON.stringify({

                        action,

                        ...this.getBatchTargetPayload(),

                        preview_token: previewData.preview_token,

                        idempotency_key: idempotencyKey

                    })

                });

                const data = await response.json();

                if (response.ok) {

                    const successCount = data.success_count ?? data.succeeded ?? 0;

                    showStatus(t('status_batch_complete', {success: successCount, total: data.total_count || targetCount}), 'success');

                    showMessageModal(

                        t('pool.batch.results_title'),

                        this.formatBatchResults(data),

                        successCount === (data.total_count || 0) ? 'success' : 'info'

                    );

                    if (action === 'delete') {

                        const executedFiles = (data.results || [])

                            .filter(item => item.status === 'succeeded')

                            .map(item => item.filename)

                            .filter(Boolean);

                        executedFiles.forEach((filename) => {

                            delete AppState.quotaPreviewCache[filename];

                        });

                        Object.entries(AppState.credentialCardIndex).forEach(([pathId, context]) => {

                            if (executedFiles.includes(context.filename)) delete AppState.credentialCardIndex[pathId];

                        });

                    }

                    this.clearSelection();

                    await this.refresh();

                    if (action === 'delete') await refreshUsageStats();

                } else {

                    const operationError = data.error?.code === 'credential_batch_preview_required'

                        ? t('pool.batch.preview_stale')

                        : (data.error?.message || data.detail || t('unknown_error'));

                    showStatus(t('status_batch_failed', {error: operationError}), 'error');

                }

            } catch (error) {

                showStatus(t('status_batch_net_error', {error: error.message}), 'error');

            }

        }

    };

}

// =====================================================================

// =====================================================================
