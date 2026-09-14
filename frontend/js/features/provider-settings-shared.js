const PROVIDER_FIELD_DEFAULTS = Object.freeze({
    type: 'text', required: false, minLength: 0, maxLength: 512, autocomplete: 'off',
    secretLifetime: 'none', environmentLock: false, helpKey: 'provider.form.text_help',
    advanced: true, validation: 'text', resetBehavior: 'provider-default'
});

function defineProviderField(options) {
    return Object.freeze({...PROVIDER_FIELD_DEFAULTS, ...options});
}

const PROVIDER_FORM_CONTRACT = Object.freeze({
    'grok.oauth': Object.freeze([
        defineProviderField({
            id: 'xaiAuthorizationCode', type: 'password', required: true, minLength: 1,
            maxLength: 4096, autocomplete: 'one-time-code', secretLifetime: 'submit',
            environmentLock: false, helpKey: 'provider.form.oauth_code_help', advanced: false,
            validation: 'secret', resetBehavior: 'clear'
        })
    ]),
    'grok.settings': Object.freeze([
        defineProviderField({id: 'xaiClientId', configKey: 'xai_client_id', required: true,
            minLength: 3, environmentLock: true, helpKey: 'provider.form.client_id_help',
            validation: 'trimmed'}),
        defineProviderField({id: 'xaiOauthIssuer', configKey: 'xai_oauth_issuer', type: 'url',
            required: true, minLength: 8, maxLength: 2048, autocomplete: 'url',
            environmentLock: true, helpKey: 'provider.form.endpoint_help', validation: 'http-url'})
    ]),
    'xai.credential': Object.freeze([
        defineProviderField({
            id: 'xaiApiKey', type: 'password', required: true, minLength: 16,
            maxLength: 1024, autocomplete: 'one-time-code', secretLifetime: 'submit',
            environmentLock: false, helpKey: 'provider.form.api_key_help', advanced: false,
            validation: 'secret', resetBehavior: 'clear'
        })
    ]),
    'xai.settings': Object.freeze([
        defineProviderField({id: 'xaiApiUrl', configKey: 'xai_api_url', type: 'url',
            required: true, minLength: 8, maxLength: 2048, autocomplete: 'url',
            environmentLock: true, helpKey: 'provider.form.endpoint_help', validation: 'http-url'}),
        defineProviderField({id: 'xaiUserAgent', configKey: 'xai_user_agent', required: true,
            minLength: 3, environmentLock: true, helpKey: 'provider.form.user_agent_help',
            validation: 'trimmed'})
    ]),
    'google-ai-studio.credential': Object.freeze([
        defineProviderField({
            id: 'googleAiStudioApiKey', type: 'password', required: true, minLength: 1,
            maxLength: 4096, autocomplete: 'one-time-code', secretLifetime: 'submit',
            environmentLock: false, helpKey: 'provider.form.api_key_help', advanced: false,
            validation: 'secret', resetBehavior: 'clear'
        })
    ]),
    'google-ai-studio.settings': Object.freeze([
        defineProviderField({id: 'googleAiStudioApiUrl', configKey: 'google_ai_studio_api_url',
            type: 'url', required: true, minLength: 8, maxLength: 2048, autocomplete: 'url',
            environmentLock: true, helpKey: 'provider.form.endpoint_help', validation: 'http-url'})
    ]),
    'codex.settings': Object.freeze([
        defineProviderField({id: 'codexApiUrl', configKey: 'codex_api_url', type: 'url',
            required: true, minLength: 8, maxLength: 2048, autocomplete: 'url',
            environmentLock: true, helpKey: 'provider.form.endpoint_help', validation: 'http-url'}),
        defineProviderField({id: 'codexUsageUrl', configKey: 'codex_usage_url', type: 'url',
            required: true, minLength: 8, maxLength: 2048, autocomplete: 'url',
            environmentLock: true, helpKey: 'provider.form.endpoint_help', validation: 'http-url'}),
        defineProviderField({id: 'codexAuthBase', configKey: 'codex_auth_base', type: 'url',
            required: true, minLength: 8, maxLength: 2048, autocomplete: 'url',
            environmentLock: true, helpKey: 'provider.form.endpoint_help', validation: 'http-url'}),
        defineProviderField({id: 'codexClientId', configKey: 'codex_client_id', required: true,
            minLength: 3, environmentLock: true, helpKey: 'provider.form.client_id_help',
            validation: 'trimmed'}),
        defineProviderField({id: 'codexUserAgent', configKey: 'codex_user_agent', required: true,
            minLength: 3, environmentLock: true, helpKey: 'provider.form.user_agent_help',
            validation: 'trimmed'})
    ]),
    'openai-platform.credential': Object.freeze([
        defineProviderField({
            id: 'openaiPlatformApiKey', type: 'password', required: true, minLength: 1,
            maxLength: 1024, autocomplete: 'one-time-code', secretLifetime: 'submit',
            environmentLock: false, helpKey: 'provider.form.api_key_help', advanced: false,
            validation: 'secret', resetBehavior: 'clear'
        })
    ]),
    'openai-platform.settings': Object.freeze([
        defineProviderField({id: 'openaiApiUrl', configKey: 'openai_api_url', type: 'url',
            required: true, minLength: 8, maxLength: 2048, autocomplete: 'url',
            environmentLock: true, helpKey: 'provider.form.endpoint_help', validation: 'http-url'})
    ]),
    'claude-code.oauth': Object.freeze([
        defineProviderField({
            id: 'claudeAuthorizationCode', type: 'password', required: true, minLength: 1,
            maxLength: 4096, autocomplete: 'one-time-code', secretLifetime: 'submit',
            environmentLock: false, helpKey: 'provider.form.oauth_code_help', advanced: false,
            validation: 'secret', resetBehavior: 'clear'
        })
    ]),
    'claude-code.settings': Object.freeze([
        defineProviderField({id: 'anthropicApiUrlCode', configKey: 'anthropic_api_url',
            type: 'url', required: true, minLength: 8, maxLength: 2048, autocomplete: 'url',
            environmentLock: true, helpKey: 'provider.form.endpoint_help', validation: 'http-url'}),
        defineProviderField({id: 'claudeAuthorizeUrl', configKey: 'claude_oauth_authorize_url',
            type: 'url', required: true, minLength: 8, maxLength: 2048, autocomplete: 'url',
            environmentLock: true, helpKey: 'provider.form.endpoint_help', validation: 'http-url'}),
        defineProviderField({id: 'claudeTokenUrl', configKey: 'claude_oauth_token_url', type: 'url',
            required: true, minLength: 8, maxLength: 2048, autocomplete: 'url',
            environmentLock: true, helpKey: 'provider.form.endpoint_help', validation: 'http-url'}),
        defineProviderField({id: 'claudeClientId', configKey: 'claude_client_id', required: true,
            minLength: 3, environmentLock: true, helpKey: 'provider.form.client_id_help',
            validation: 'trimmed'}),
        defineProviderField({id: 'claudeUserAgent', configKey: 'claude_user_agent', required: true,
            minLength: 3, environmentLock: true, helpKey: 'provider.form.user_agent_help',
            validation: 'trimmed'})
    ]),
    'claude-platform.credential': Object.freeze([
        defineProviderField({
            id: 'claudePlatformApiKey', type: 'password', required: true, minLength: 1,
            maxLength: 1024, autocomplete: 'one-time-code', secretLifetime: 'submit',
            environmentLock: false, helpKey: 'provider.form.api_key_help', advanced: false,
            validation: 'secret', resetBehavior: 'clear'
        })
    ]),
    'claude-platform.settings': Object.freeze([
        defineProviderField({id: 'anthropicApiUrlPlatform', configKey: 'anthropic_api_url',
            type: 'url', required: true, minLength: 8, maxLength: 2048, autocomplete: 'url',
            environmentLock: true, helpKey: 'provider.form.endpoint_help', validation: 'http-url'})
    ]),
    'ollama.credential': Object.freeze([
        defineProviderField({id: 'ollamaBaseUrl', type: 'url', required: true, minLength: 8,
            maxLength: 2048, autocomplete: 'url', secretLifetime: 'none', environmentLock: false,
            helpKey: 'provider.form.ollama_endpoint_help', advanced: false, validation: 'http-url',
            resetBehavior: 'retain'}),
        defineProviderField({
            id: 'ollamaApiKey', type: 'password', required: false, minLength: 0,
            maxLength: 4096, autocomplete: 'one-time-code', secretLifetime: 'submit',
            environmentLock: false, helpKey: 'provider.form.optional_api_key_help', advanced: false,
            validation: 'optional-secret', resetBehavior: 'clear'
        })
    ]),
    'antigravity.oauth': Object.freeze([
        defineProviderField({
            id: 'primaryCallbackUrlInput', type: 'textarea', required: false, minLength: 0,
            maxLength: 8192, autocomplete: 'off', secretLifetime: 'submit',
            environmentLock: false, helpKey: 'provider.form.callback_url_help', advanced: false,
            validation: 'optional-http-url', resetBehavior: 'clear'
        })
    ]),
    'antigravity.settings': Object.freeze([
        defineProviderField({id: 'antigravityOauthClientId', configKey: 'antigravity_client_id',
            required: true, minLength: 3, environmentLock: true,
            helpKey: 'provider.form.client_id_help', validation: 'trimmed'}),
        defineProviderField({
            id: 'antigravityOauthClientSecret', configKey: 'antigravity_client_secret',
            type: 'password', required: true, minLength: 8, maxLength: 4096,
            autocomplete: 'new-password', secretLifetime: 'edit-session', environmentLock: true,
            helpKey: 'provider.form.client_secret_help', advanced: true,
            validation: 'secret', resetBehavior: 'clear'
        }),
        defineProviderField({id: 'antigravityApiUrl', configKey: 'antigravity_api_url', type: 'url',
            required: true, minLength: 8, maxLength: 2048, autocomplete: 'url',
            environmentLock: true, helpKey: 'provider.form.endpoint_help', validation: 'http-url'}),
        defineProviderField({id: 'antigravityOauthUrl', configKey: 'oauth_url', type: 'url',
            required: true, minLength: 8, maxLength: 2048, autocomplete: 'url',
            environmentLock: true, helpKey: 'provider.form.endpoint_help', validation: 'http-url'}),
        defineProviderField({id: 'antigravityGoogleApisUrl', configKey: 'google_apis_url', type: 'url',
            required: true, minLength: 8, maxLength: 2048, autocomplete: 'url',
            environmentLock: true, helpKey: 'provider.form.endpoint_help', validation: 'http-url'}),
        defineProviderField({id: 'antigravityResourceManagerUrl', configKey: 'resource_manager_url',
            type: 'url', required: true, minLength: 8, maxLength: 2048, autocomplete: 'url',
            environmentLock: true, helpKey: 'provider.form.endpoint_help', validation: 'http-url'}),
        defineProviderField({id: 'antigravityServiceUsageUrl', configKey: 'service_usage_url',
            type: 'url', required: true, minLength: 8, maxLength: 2048, autocomplete: 'url',
            environmentLock: true, helpKey: 'provider.form.endpoint_help', validation: 'http-url'}),
        defineProviderField({id: 'antigravityUserAgent', configKey: 'antigravity_user_agent',
            required: true, minLength: 3, environmentLock: true,
            helpKey: 'provider.form.user_agent_help', validation: 'trimmed'}),
        defineProviderField({id: 'antigravityPayloadUserAgent',
            configKey: 'antigravity_payload_user_agent', required: true, minLength: 3,
            environmentLock: true, helpKey: 'provider.form.user_agent_help', validation: 'trimmed'}),
        defineProviderField({id: 'antigravityStreamToNonstream', configKey: 'stream_to_nonstream',
            type: 'checkbox', maxLength: 0, autocomplete: 'off', environmentLock: true,
            helpKey: 'provider.form.streaming_help', validation: 'boolean'}),
        defineProviderField({id: 'antigravitySwitchCredential',
            configKey: 'switch_credential_enabled', type: 'checkbox', maxLength: 0,
            autocomplete: 'off', environmentLock: true,
            helpKey: 'provider.form.credential_switch_help', validation: 'boolean'})
    ])
});

const PROVIDER_FORM_COPY_CONTRACT = Object.freeze([
    {selector: '#providerWorkspaceClaudeCode .provider-settings-header h2', key: 'advanced_settings', provider: 'Claude Code'},
    {selector: '#claudeCodeSettingsForm label[for="claudeAuthorizeUrl"]', key: 'authorization_service'},
    {selector: '#claudeCodeSettingsForm label[for="claudeTokenUrl"]', key: 'token_service'},
    {selector: '#claudeCodeSettingsForm label[for="claudeClientId"]', key: 'oauth_client_id'},
    {selector: '#providerWorkspaceClaudePlatform .provider-tools-grid .tool-panel:first-child h2', key: 'api_key_title', provider: 'Claude Platform'},
    {selector: '#providerWorkspaceClaudePlatform .provider-settings-header h2', key: 'advanced_settings', provider: 'Claude Platform'},
    {selector: '#providerWorkspaceOllama .provider-tools-grid .tool-panel:first-child h2', key: 'connection_title', provider: 'Ollama'},
    {selector: '#ollamaCredentialForm label[for="ollamaBaseUrl"]', key: 'endpoint_label'},
    {selector: '#ollamaCredentialForm .field-optional', key: 'optional'}
]);

function getProviderFormFields(scope) {
    return PROVIDER_FORM_CONTRACT[scope] || [];
}

function applyProviderFormContract() {
    applyProviderFormCopy();
    Object.entries(PROVIDER_FORM_CONTRACT).forEach(([scope, definitions]) => {
        definitions.forEach((definition) => {
            const field = document.getElementById(definition.id);
            if (!field) return;
            if (definition.type !== 'textarea') field.setAttribute('type', definition.type);
            field.required = definition.required;
            if (definition.minLength > 0 && definition.type !== 'checkbox') {
                field.setAttribute('minlength', String(definition.minLength));
            } else {
                field.removeAttribute('minlength');
            }
            if (definition.maxLength > 0 && definition.type !== 'checkbox') {
                field.setAttribute('maxlength', String(definition.maxLength));
            } else {
                field.removeAttribute('maxlength');
            }
            field.setAttribute('autocomplete', definition.autocomplete);
            field.dataset.providerFormScope = scope;
            field.dataset.providerValidation = definition.validation;
            field.dataset.secretLifetime = definition.secretLifetime;
            field.dataset.resetBehavior = definition.resetBehavior;
            field.dataset.environmentLock = String(definition.environmentLock);
            field.dataset.advanced = String(definition.advanced);
            field.dataset.helpKey = definition.helpKey;
            if (definition.secretLifetime === 'submit') {
                field.placeholder = t(definition.helpKey);
            }
            field.removeAttribute('aria-describedby');
        });
    });
}

function applyProviderFormCopy() {
    PROVIDER_FORM_COPY_CONTRACT.forEach((definition) => {
        document.querySelectorAll(definition.selector).forEach((element) => {
            element.textContent = t(`provider.form.${definition.key}`, {
                provider: definition.provider || ''
            });
        });
    });
    document.querySelectorAll('[data-provider-form-copy]').forEach((element) => {
        const key = `provider.form.${element.dataset.providerFormCopy}`;
        element.textContent = t(key, {provider: element.dataset.providerName || ''});
    });
    Object.values(PROVIDER_FORM_CONTRACT).flat().forEach((definition) => {
        if (definition.secretLifetime !== 'submit') return;
        const field = document.getElementById(definition.id);
        if (field) field.placeholder = t(definition.helpKey);
    });
}

function applyProviderEnvironmentLocks(scopes, lockedKeys) {
    const requestedScopes = Array.isArray(scopes) ? scopes : [scopes];
    const locked = new Set(lockedKeys || []);
    requestedScopes.flatMap(getProviderFormFields).forEach((definition) => {
        if (!definition.environmentLock || !definition.configKey) return;
        const field = document.getElementById(definition.id);
        if (!field) return;
        const isLocked = locked.has(definition.configKey);
        field.disabled = isLocked;
        field.classList.toggle('env-locked', isLocked);
        field.closest('.switch-row')?.classList.toggle('env-locked', isLocked);
    });
}

function validateProviderFormScope(scope, {report = true} = {}) {
    let firstInvalid = null;
    getProviderFormFields(scope).forEach((definition) => {
        const field = document.getElementById(definition.id);
        if (!field || field.disabled || definition.type === 'checkbox') return;
        const value = field.value.trim();
        let errorKey = '';
        const configuredSecret = definition.secretLifetime === 'edit-session'
            && field.dataset.secretConfigured === 'true';
        if (definition.required && !value && !configuredSecret) {
            errorKey = 'provider.form.required_error';
        }
        else if (value && definition.minLength > 0 && value.length < definition.minLength) {
            errorKey = 'provider.form.too_short_error';
        } else if (definition.maxLength > 0 && value.length > definition.maxLength) {
            errorKey = 'provider.form.too_long_error';
        } else if (value && ['http-url', 'optional-http-url'].includes(definition.validation)) {
            try {
                const parsed = new URL(value);
                if (!['http:', 'https:'].includes(parsed.protocol)) errorKey = 'provider.form.url_error';
            } catch (_error) {
                errorKey = 'provider.form.url_error';
            }
        }
        field.setCustomValidity(errorKey ? t(errorKey) : '');
        if (errorKey && !firstInvalid) firstInvalid = field;
    });
    if (firstInvalid && report) {
        firstInvalid.reportValidity();
        firstInvalid.focus();
    }
    return !firstInvalid;
}

function resetProviderTransientSecrets(scope) {
    getProviderFormFields(scope).forEach((definition) => {
        if (definition.secretLifetime !== 'submit' || definition.resetBehavior !== 'clear') return;
        const field = document.getElementById(definition.id);
        if (field) field.value = '';
    });
}

function setProviderSettingsLoading(loadingIds, formIds, isLoading, preserveContent = false) {
    loadingIds.forEach((id) => {
        const element = document.getElementById(id);
        if (!element) return;
        element.hidden = !isLoading || preserveContent;
        element.setAttribute('aria-busy', String(isLoading));
    });

    formIds.forEach((id) => {
        document.getElementById(id)?.classList.toggle('hidden', isLoading && !preserveContent);
    });
}

const PROVIDER_REQUEST_REMEDIATION_KEYS = Object.freeze({
    credential: 'providers.remediation_credential',
    permission: 'providers.remediation_permission',
    quota: 'providers.remediation_quota',
    rate_limit: 'providers.remediation_rate_limit',
    invalid_model: 'providers.remediation_invalid_model',
    network: 'providers.remediation_network',
    upstream: 'providers.remediation_upstream'
});

function classifyProviderRequestFailure(response, data) {
    const diagnosticCategory = data?.diagnostic?.category;
    if (PROVIDER_REQUEST_REMEDIATION_KEYS[diagnosticCategory]) return diagnosticCategory;
    const status = Number(response?.status || 0);
    if (!status) return 'network';
    if (status === 401 || status === 400) return 'credential';
    if (status === 403) return 'permission';
    if (status === 402) return 'quota';
    if (status === 429) return 'rate_limit';
    if (status === 404) return 'invalid_model';
    return 'upstream';
}

function createProviderRequestError(response, data) {
    const message = data?.detail || data?.error || data?.message || t('unknown_error');
    const error = new Error(message);
    error.providerCategory = classifyProviderRequestFailure(response, data);
    error.providerDiagnostic = data?.diagnostic || null;
    return error;
}

function formatProviderRequestError(error) {
    const category = PROVIDER_REQUEST_REMEDIATION_KEYS[error?.providerCategory]
        ? error.providerCategory
        : (error instanceof TypeError ? 'network' : 'upstream');
    const remediation = error?.providerDiagnostic?.remediation
        || t(PROVIDER_REQUEST_REMEDIATION_KEYS[category]);
    const message = String(error?.message || t('unknown_error')).trim();
    return remediation && !message.includes(remediation)
        ? `${message} ${remediation}`
        : message;
}

document.addEventListener('DOMContentLoaded', applyProviderFormContract, {once: true});
document.addEventListener('polaris:locale-change', applyProviderFormCopy);
