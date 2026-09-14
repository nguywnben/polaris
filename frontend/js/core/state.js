
// =====================================================================

// =====================================================================

// =====================================================================

// =====================================================================

const AppState = {

    authenticated: false,

    setupRequired: false,

    authInProgress: false,

    currentProjectId: '',

    primaryAuthState: null,

    primaryAuthInProgress: false,

    primaryCredentialFilename: '',

    creds: createCredsManager('normal'),

    primaryCreds: createCredsManager('primary'),

    credentialCardIndex: {},

    uploadFiles: createUploadManager('normal'),

    primaryUploadFiles: createUploadManager('primary'),

    googleAiStudioUploadFiles: createUploadManager('googleAiStudio', {
        endpoint: './api/providers/google-ai-studio/credentials/import',
        elementPrefix: 'googleAiStudio',
        credentialType: 'Google AI Studio',
        timeoutMs: 900000,
        onComplete: () => AppState.primaryCreds.refresh()
    }),

    grokUploadFiles: createUploadManager('grok', {
        endpoint: './api/providers/xai/credentials/import?credential_type=oauth',
        elementPrefix: 'grok',
        credentialType: 'Grok Build OAuth',
        timeoutMs: 900000,
        onComplete: async () => {
            await AppState.primaryCreds.refresh();
            await loadModelCatalog(true);
            await refreshUsageStats();
        }
    }),

    xaiConsoleUploadFiles: createUploadManager('xaiConsole', {
        endpoint: './api/providers/xai/credentials/import?credential_type=api_key',
        elementPrefix: 'xaiConsole',
        credentialType: 'SpaceXAI Console',
        timeoutMs: 900000,
        onComplete: async () => {
            await AppState.primaryCreds.refresh();
            await loadModelCatalog(true);
            await refreshUsageStats();
        }
    }),

    codexUploadFiles: createUploadManager('codex', {
        endpoint: './api/providers/openai/credentials/import?credential_type=oauth',
        elementPrefix: 'codex',
        credentialType: 'Codex',
        timeoutMs: 900000,
        onComplete: async () => {
            await AppState.primaryCreds.refresh();
            await loadModelCatalog(true);
            await refreshUsageStats();
        }
    }),

    openaiPlatformUploadFiles: createUploadManager('openaiPlatform', {
        endpoint: './api/providers/openai/credentials/import?credential_type=api_key',
        elementPrefix: 'openaiPlatform',
        credentialType: 'OpenAI Platform',
        timeoutMs: 900000,
        onComplete: async () => {
            await AppState.primaryCreds.refresh();
            await loadModelCatalog(true);
            await refreshUsageStats();
        }
    }),

    claudeCodeUploadFiles: createUploadManager('claudeCode', {
        endpoint: './api/providers/anthropic/credentials/import?credential_type=oauth',
        elementPrefix: 'claudeCode',
        credentialType: 'Claude Code',
        timeoutMs: 900000,
        onComplete: async () => {
            await AppState.primaryCreds.refresh();
            await loadModelCatalog(true);
            await refreshUsageStats();
        }
    }),

    claudePlatformUploadFiles: createUploadManager('claudePlatform', {
        endpoint: './api/providers/anthropic/credentials/import?credential_type=api_key',
        elementPrefix: 'claudePlatform',
        credentialType: 'Claude Platform',
        timeoutMs: 900000,
        onComplete: async () => {
            await AppState.primaryCreds.refresh();
            await loadModelCatalog(true);
            await refreshUsageStats();
        }
    }),

    ollamaUploadFiles: createUploadManager('ollama', {
        endpoint: './api/providers/ollama/credentials/import',
        elementPrefix: 'ollama',
        credentialType: 'Ollama',
        timeoutMs: 900000,
        onComplete: async () => {
            await AppState.primaryCreds.refresh();
            await loadModelCatalog(true);
            await refreshUsageStats();
        }
    }),

    currentConfig: {},

    configLoaded: false,

    envLockedFields: new Set(),

    qualityPolicy: null,

    qualityEffectiveSettings: null,

    qualityProfileDefaults: {},

    qualityEnvLockedFields: new Set(),

    qualityPolicyLoaded: false,

    antigravityConfig: {},

    antigravityConfigLoaded: false,

    antigravityEnvLockedFields: new Set(),

    activeProviderWorkspace: 'google_antigravity',

    modelCatalog: [],

    modelCatalogLoaded: false,

    modelBlacklist: [],

    selectedModels: [],

    modelPoolEnabled: true,

    modelPoolConfigured: false,

    modelPoolRevision: '',
    savedModelSelection: [],

    modelRouteValidation: null,

    modelProviderCatalogs: [],

    modelRoutingPolicy: { strategy: 'balanced', preferred_provider: '' },

    playground: {

        initialized: false,

        messages: [{role: 'user', content: ''}],

        controller: null,

        running: false,

        cancelReason: '',

        hasRun: false,

        outcomeKey: 'playground.not_run',

        outcomeType: 'muted',

        runStateKey: 'playground.ready'

    },

    logWebSocket: null,

    allLogs: [],

    filteredLogs: [],

    currentLogFilter: 'all',

    activeActivityView: 'traces',

    teamAccessEnabled: null,

    usageStatsData: {},

    usageStatsLoaded: false,

    operationalHealth: null,

    dashboardAggregate: null,

    usagePeriod: '1d',

    usagePage: 1,

    usagePageSize: 10,

    historicalUsagePage: 1,

    historicalUsagePageSize: 10,

    tabLoadTimes: {},

    tabLoadPromises: {},

    quotaPreviewCache: {},

    cooldownTimerInterval: null

};

const STORAGE_KEYS = {
    logAutoScroll: 'polaris_log_auto_scroll',
};

// =====================================================================

// =====================================================================
