// Polaris management console: settings.

function initLogAutoScrollPreference() {

    const autoScroll = document.getElementById('autoScroll');

    if (!autoScroll) return;

    const savedValue = localStorage.getItem(STORAGE_KEYS.logAutoScroll);

    if (savedValue !== null) {

        autoScroll.checked = savedValue === 'true';

    }

    autoScroll.addEventListener('change', () => {

        localStorage.setItem(STORAGE_KEYS.logAutoScroll, String(autoScroll.checked));

    });

}

document.addEventListener('DOMContentLoaded', initLogAutoScrollPreference);

function connectWebSocket() {

    if (AppState.logWebSocket && AppState.logWebSocket.readyState === WebSocket.OPEN) {

        // showStatus(t('websocket_connected'), 'info');

        return;

    }

    try {

        const wsPath = new URL('./api/logs/stream', window.location.href).href;

        const wsUrl = wsPath.replace(/^http/, 'ws');

        document.getElementById('connectionStatusText').textContent = t('connecting');

        document.getElementById('logConnectionStatus').className = 'status info';

        AppState.logWebSocket = new WebSocket(wsUrl);

        AppState.logWebSocket.onopen = () => {

            document.getElementById('connectionStatusText').textContent = t('connected');

            document.getElementById('logConnectionStatus').className = 'status success';

            // showStatus(t('log_stream_connected_successfully'), 'success');

            clearLogsDisplay();

        };

        AppState.logWebSocket.onmessage = (event) => {

            const logLine = event.data;

            if (logLine.trim()) {

                AppState.allLogs.push(logLine);

                if (AppState.allLogs.length > 1000) {

                    AppState.allLogs = AppState.allLogs.slice(-1000);

                }

                filterLogs();

                if (document.getElementById('autoScroll')?.checked) {

                    const logContainer = document.getElementById('logContainer');

                    logContainer.scrollTop = logContainer.scrollHeight;

                }

            }

        };

        AppState.logWebSocket.onclose = () => {

            document.getElementById('connectionStatusText').textContent = t('connection_lost');

            document.getElementById('logConnectionStatus').className = 'status error';

            // showStatus(t('log_stream_connection_disconnected'), 'info');

        };

        AppState.logWebSocket.onerror = (error) => {

            document.getElementById('connectionStatusText').textContent = t('connection_error');

            document.getElementById('logConnectionStatus').className = 'status error';

            showStatus(t('status_log_stream_error_prefix') + error, 'error');

        };

    } catch (error) {

        showStatus(t('status_log_stream_connection_failed') + error.message, 'error');

        document.getElementById('connectionStatusText').textContent = t('connection_failed');

        document.getElementById('logConnectionStatus').className = 'status error';

    }

}

function disconnectWebSocket() {

    if (AppState.logWebSocket) {

        AppState.logWebSocket.close();

        AppState.logWebSocket = null;

        document.getElementById('connectionStatusText').textContent = t('disconnected');

        document.getElementById('logConnectionStatus').className = 'status info';

        showStatus(t('log_stream_connection_disconnected_dup'), 'info');

    }

}

function clearLogsDisplay({cleared = false} = {}) {

    AppState.allLogs = [];

    AppState.filteredLogs = [];

    document.getElementById('logContent').textContent = t(cleared ? 'logs_cleared_waiting_for_new_logs' : 'no_logs_yet');

}

async function downloadLogs() {

    try {

        const response = await fetch('./api/logs/download', { headers: getAuthHeaders() });

        if (response.ok) {

            const contentDisposition = response.headers.get('Content-Disposition');

            let filename = 'logs.txt';

            if (contentDisposition) {

                const match = contentDisposition.match(/filename=(.+)/);

                if (match) filename = match[1];

            }

            const blob = await response.blob();

            const url = window.URL.createObjectURL(blob);

            const a = document.createElement('a');

            a.href = url;

            a.download = filename;

            a.click();

            window.URL.revokeObjectURL(url);

            showStatus(t('log_file_download_successful_filena', {filename: filename}), 'success');

        } else {

            const data = await response.json();

            showStatus(t('failed_to_download_logs_datadetail', {data_detail____data_error: data.detail || data.error || t('unknown_error')}), 'error');

        }

    } catch (error) {

        showStatus(t('network_error_while_downloading_log', {error_message: error.message}), 'error');

    }

}

async function clearLogs() {

    const confirmed = await showConfirmModal(t('confirm_clear_logs'), {

        title: t('confirm_clear_logs_title'),

        confirmLabel: t('btn_clear_logs')

    });

    if (!confirmed) return;

    try {

        const response = await fetch('./api/logs/clear', {

            method: 'POST',

            headers: getAuthHeaders()

        });

        const data = await response.json();

        if (response.ok) {

            clearLogsDisplay({cleared: true});

            showStatus(data.message, 'success');

        } else {

            showStatus(t('failed_to_clear_logs_datadetail_dat', {data_detail____data_error: data.detail || data.error || t('unknown_error')}), 'error');

        }

    } catch (error) {

        showStatus(t('network_error_while_clearing_logs_e', {error_message: error.message}), 'error');

    }

}

function filterLogs() {

    const filter = document.getElementById('logLevelFilter').value;

    AppState.currentLogFilter = filter;

    if (filter === 'all') {

        AppState.filteredLogs = [...AppState.allLogs];

    } else {

        AppState.filteredLogs = AppState.allLogs.filter(log => log.toUpperCase().includes(filter));

    }

    if (typeof activityLogLineMatches === 'function') {

        AppState.filteredLogs = AppState.filteredLogs.filter(log => activityLogLineMatches(log));

    }

    displayLogs();

}

function displayLogs() {

    const logContent = document.getElementById('logContent');

    if (AppState.filteredLogs.length === 0) {

        logContent.textContent = AppState.currentLogFilter === 'all' ?

            t('no_logs_yet') : t('no_logs_at_appstatecurrentlogfilter', {AppState_currentLogFilter: AppState.currentLogFilter});

    } else {

        logContent.textContent = AppState.filteredLogs.join('\n');

    }

}

// =====================================================================

// =====================================================================
