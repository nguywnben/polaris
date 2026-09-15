const SYSTEM_CONFIG_FIELD_KEYS = Object.freeze({
    host: 'host',
    port: 'port',
    credentialsDir: 'credentials_dir',
    proxy: 'proxy',
    streamToNonstream: 'stream_to_nonstream',
    switchCredentialEnabled: 'switch_credential_enabled',
    autoBanEnabled: 'auto_disable_enabled',
    autoBanErrorCodes: 'auto_disable_error_codes',
    retry429Enabled: 'retry_429_enabled',
    retry429MaxRetries: 'retry_429_max_retries',
    retry429Interval: 'retry_429_interval',
    upstreamTimeoutSeconds: 'upstream_timeout_seconds',
    runtimeLogLevel: 'log_level',
    runtimeLogMaxMb: 'log_max_mb',
    runtimeLogBackupCount: 'log_backup_count',
    keepaliveUrl: 'keepalive_url',
    keepaliveInterval: 'keepalive_interval'
});

function normalizeSettingsMetadata(payload) {
    if (!Array.isArray(payload)) throw new Error(t('settings.metadata_invalid'));
    const expectedKeys = new Set(Object.values(SYSTEM_CONFIG_FIELD_KEYS));
    const metadata = new Map();
    for (const item of payload) {
        if (!item || typeof item !== 'object' || !expectedKeys.has(item.config_key)) continue;
        if (
            item.surface !== 'system'
            || !['basic', 'advanced', 'experimental'].includes(item.group)
            || !['live', 'restart', 'read_only'].includes(item.apply)
            || !['string', 'integer', 'number', 'boolean', 'csv', 'space_list', 'integer_list', 'json'].includes(item.value_type)
            || typeof item.environment_locked !== 'boolean'
            || typeof item.secret !== 'boolean'
        ) {
            throw new Error(t('settings.metadata_invalid'));
        }
        metadata.set(item.config_key, Object.freeze({...item}));
    }
    if (metadata.size !== expectedKeys.size) throw new Error(t('settings.metadata_incomplete'));
    return metadata;
}

function settingsConfigKey(field) {
    return field?.dataset?.configKey || SYSTEM_CONFIG_FIELD_KEYS[field?.id] || '';
}

function renderSettingsMetadata(metadata) {
    const counts = {live: 0, restart: 0, managed: 0};
    for (const field of document.querySelectorAll('[data-config-key]')) {
        const item = metadata.get(settingsConfigKey(field));
        if (!item) continue;
        counts[item.apply] = (counts[item.apply] || 0) + 1;
        if (item.environment_locked) counts.managed += 1;
        field.dataset.applyMode = item.apply;
        field.dataset.settingsGroup = item.group;
        const container = field.closest('.form-group, .switch-row');
        if (!container) continue;
        container.classList.toggle('is-environment-managed', item.environment_locked);
        if (item.environment_locked) {
            field.title = t('settings.managed_environment');
        } else {
            field.removeAttribute('title');
        }
    }
    const summary = document.getElementById('settingsApplySummary');
    if (summary) {
        summary.textContent = t('settings.apply_summary', Object.fromEntries(
            Object.entries(counts).map(([key, value]) => [key, formatConsoleNumber(value)])
        ));
    }
}

globalThis.document?.addEventListener?.('polaris:locale-change', () => {
    if (AppState.settingsMetadata instanceof Map) {
        renderSettingsMetadata(AppState.settingsMetadata);
    }
});

async function loadConfig(options = {}) {

    const loadingElements = ['configLoading']
        .map(id => document.getElementById(id))
        .filter(Boolean);

    const formElements = ['configForm']
        .map(id => document.getElementById(id))
        .filter(Boolean);

    const preserveContent = options.preserveContent ?? AppState.configLoaded;
    clearPageState('configState');

    try {

        if (!preserveContent) loadingElements.forEach(element => { element.hidden = false; });

        if (!preserveContent) formElements.forEach(element => element.classList.add('hidden'));

        const response = await fetch('./api/config/get', { headers: getAuthHeaders() });

        const data = await response.json();

        if (response.ok) {

            const metadata = normalizeSettingsMetadata(data.metadata);

            AppState.currentConfig = data.config;

            AppState.configLoaded = true;

            AppState.envLockedFields = new Set(data.env_locked || []);

            AppState.settingsMetadata = metadata;

            populateConfigForm();

            renderSettingsMetadata(metadata);

            const retentionLoaders = [];
            if (typeof loadTraceRetention === 'function') retentionLoaders.push(loadTraceRetention());
            if (typeof loadAuditRetention === 'function') retentionLoaders.push(loadAuditRetention());
            await Promise.all(retentionLoaders);

            formElements.forEach(element => element.classList.remove('hidden'));
            clearPageState('configState');

            // showStatus(t('configuration_loaded_successfully'), 'success');

        } else {
            throw new Error(t('failed_to_load_configuration_datade', {data_detail____data_error: data.detail || data.error || t('unknown_error')}));
        }

    } catch (error) {

        const message = error.message || t('status_net_error', {error: t('unknown_error')});
        showPageState('configState', {
            kind: preserveContent ? 'stale' : 'error',
            title: t(preserveContent ? 'warning' : 'error'),
            message,
            actionLabel: t('refresh'),
            onAction: () => loadConfig({preserveContent: AppState.configLoaded})
        });
        showStatus(message, 'error');

    } finally {

        loadingElements.forEach(element => { element.hidden = true; });

    }

}

function populateConfigForm() {

    const c = AppState.currentConfig;

    setConfigField('host', c.host || '0.0.0.0');

    setConfigField('port', c.port || 4283);

    populateAccessCredentialStatus(c);

    setConfigField('credentialsDir', c.credentials_dir || '');

    setConfigField('proxy', c.proxy || '');

    setConfigCheckbox('streamToNonstream', c.stream_to_nonstream !== false);
    setConfigCheckbox('switchCredentialEnabled', c.switch_credential_enabled !== false);

    setConfigCheckbox('autoBanEnabled', Boolean(c.auto_disable_enabled));

    setConfigField('autoBanErrorCodes', (c.auto_disable_error_codes || []).join(','));

    setConfigCheckbox('retry429Enabled', Boolean(c.retry_429_enabled));

    setConfigField('retry429MaxRetries', c.retry_429_max_retries ?? 5);

    setConfigField('retry429Interval', c.retry_429_interval ?? 1);

    setConfigField('upstreamTimeoutSeconds', c.upstream_timeout_seconds ?? 300);

    setConfigField('runtimeLogLevel', c.log_level || 'info');

    setConfigField('runtimeLogMaxMb', c.log_max_mb ?? 10);

    setConfigField('runtimeLogBackupCount', c.log_backup_count ?? 3);

    setConfigField('keepaliveUrl', c.keepalive_url || '');

    setConfigField('keepaliveInterval', c.keepalive_interval || 60);

}

function setConfigField(fieldId, value) {

    const field = document.getElementById(fieldId);

    if (field) {

        field.value = value;

        const configKey = settingsConfigKey(field);

        if (AppState.envLockedFields.has(configKey)) {

            field.disabled = true;

            field.classList.add('env-locked');

        } else {

            field.disabled = false;

            field.classList.remove('env-locked');

        }

    }

}

function setConfigCheckbox(fieldId, checked) {

    const field = document.getElementById(fieldId);

    if (!field) return;

    field.checked = checked;

    const configKey = settingsConfigKey(field);

    const isLocked = AppState.envLockedFields.has(configKey);

    field.disabled = isLocked;

    field.classList.toggle('env-locked', isLocked);

    field.closest('.switch-row')?.classList.toggle('env-locked', isLocked);

}

function collectSystemConfigForm() {
    const getValue = (id, fallback = '') => document.getElementById(id)?.value.trim() || fallback;
    const getNumber = (id, fallback, parser) => {
        const parsed = parser(document.getElementById(id)?.value ?? '');
        return Number.isFinite(parsed) ? parsed : fallback;
    };
    const getChecked = (id, fallback = false) => {
        const field = document.getElementById(id);
        return field ? field.checked : fallback;
    };
    const config = {

            host: getValue('host', '0.0.0.0'),

            port: getNumber('port', 4283, Number.parseInt),


            credentials_dir: getValue('credentialsDir'),

            proxy: getValue('proxy'),
            stream_to_nonstream: getChecked('streamToNonstream'),
            switch_credential_enabled: getChecked('switchCredentialEnabled'),

            auto_disable_enabled: getChecked('autoBanEnabled'),

            auto_disable_error_codes: getValue('autoBanErrorCodes').split(',')

                .map(c => parseInt(c.trim())).filter(c => !isNaN(c)),

            retry_429_enabled: getChecked('retry429Enabled'),

            retry_429_max_retries: getNumber('retry429MaxRetries', 5, Number.parseInt),

            retry_429_interval: getNumber('retry429Interval', 1, Number.parseFloat),

            upstream_timeout_seconds: getNumber('upstreamTimeoutSeconds', 300, Number.parseFloat),

            log_level: getValue('runtimeLogLevel', 'info'),

            log_max_mb: getNumber('runtimeLogMaxMb', 10, Number.parseInt),

            log_backup_count: getNumber('runtimeLogBackupCount', 3, Number.parseInt),

            keepalive_url: getValue('keepaliveUrl'),

            keepalive_interval: getNumber('keepaliveInterval', 60, Number.parseInt)

        };
    const locked = typeof AppState !== 'undefined' ? AppState.envLockedFields : undefined;
    if (locked instanceof Set) {
        for (const key of locked) delete config[key];
    }
    return config;
}

async function saveConfig() {

    for (const field of document.querySelectorAll('#configForm input[data-config-key], #configForm select[data-config-key], #configForm textarea[data-config-key]')) {
        if (!field.disabled && !field.reportValidity()) return;
    }

    try {

        const config = collectSystemConfigForm();

        const response = await fetch('./api/config/save', {

            method: 'POST',

            headers: getAuthHeaders(),

            body: JSON.stringify({ config })

        });

        const data = await response.json();

        if (response.ok) {
            if (data.restart_required && data.restart_required.length > 0) {
                showStatus(data.restart_notice || t('settings.restart_to_apply'), 'info');
            } else {
                showStatus(data.message || t('configuration_saved_successfully'), 'success');
            }

            setTimeout(() => loadConfig(), 1000);

        } else {

            showStatus(t('failed_to_save_config_datadetail_da', {data_detail____data_error: data.detail || data.error || t('unknown_error')}), 'error');

        }

    } catch (error) {

        showStatus(t('status_net_error', {error: error.message}), 'error');

    }

}

function populateAccessCredentialStatus(config) {
    const panelLocked = AppState.envLockedFields.has('panel_password');
    const panelStatus = document.getElementById('panelPasswordStatus');
    if (panelStatus) {
        panelStatus.textContent = panelLocked
            ? t('settings.managed_environment')
            : (config.panel_password_configured ? t('settings.configured') : t('settings.not_configured'));
    }
    for (const id of ['newPanelPassword', 'confirmPanelPassword']) {
        const field = document.getElementById(id);
        if (field) field.disabled = panelLocked;
    }
    const button = document.getElementById('updateAccessCredentialsBtn');
    if (button) button.disabled = panelLocked;
}

async function saveAccessCredentials() {
    const currentPassword = document.getElementById('currentConsolePassword')?.value || '';
    const panelPassword = document.getElementById('newPanelPassword')?.value || '';
    const panelConfirmation = document.getElementById('confirmPanelPassword')?.value || '';

    if (!currentPassword) {
        showStatus(t('settings.current_password_required'), 'error');
        return;
    }
    if (!panelPassword) {
        showStatus(t('settings.new_password_required'), 'error');
        return;
    }
    if (panelPassword !== panelConfirmation) {
        showStatus(t('settings.password_confirmation_mismatch'), 'error');
        return;
    }
    const button = document.getElementById('updateAccessCredentialsBtn');
    if (button) button.disabled = true;
    try {
        const response = await fetch('./api/config/access', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                current_password: currentPassword,
                panel_password: panelPassword || null,
                panel_password_confirm: panelConfirmation || null
            })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.detail || data.error || t('unknown_error'));
        }
        for (const id of [
            'currentConsolePassword',
            'newPanelPassword',
            'confirmPanelPassword'
        ]) {
            const field = document.getElementById(id);
            if (field) {
                field.value = '';
                setSetupSecretVisibility(field, false);
            }
        }
        showStatus(data.message || t('configuration_saved_successfully'), 'success');
        await loadConfig();
    } catch (error) {
        showStatus(t('settings.password_update_failed', {error: error.message}), 'error');
    } finally {
        if (button) button.disabled = false;
    }
}

async function resetConfig() {

    const confirmed = await showConfirmModal(
        t('settings.reset_confirm'),
        {
            title: t('confirm_reset_system_config_title'),
            confirmLabel: t('btn_reset_defaults')
        }
    );

    if (!confirmed) return;

    try {

        const response = await fetch('./api/config/reset?scope=system', {
            method: 'POST',
            headers: getAuthHeaders()
        });

        const data = await response.json().catch(() => ({}));

        if (response.ok) {
            const requiresRestart = Array.isArray(data.restart_required) && data.restart_required.length > 0;
            const message = requiresRestart
                ? `${data.message || t('configuration_saved_successfully')} ${t('settings.restart_to_apply')}`
                : (data.message || t('configuration_saved_successfully'));
            showStatus(message, requiresRestart ? 'info' : 'success');

            setTimeout(() => loadConfig(), 600);

        } else {

            showStatus(t('settings.reset_failed', {error: data.detail || data.error || t('unknown_error')}), 'error');

        }

    } catch (error) {

        showStatus(t('status_net_error', {error: error.message}), 'error');

    }

}

// =====================================================================

// =====================================================================
