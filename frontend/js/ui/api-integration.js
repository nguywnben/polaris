async function updateEndpointUrls() {
    const origin = window.location.origin;
    const apiKeyEl = document.getElementById('apiKey');

    const openaiEl = document.getElementById('openaiEndpointUrl');
    if (openaiEl) openaiEl.textContent = `${origin}/v1`;

    const anthropicEl = document.getElementById('anthropicEndpointUrl');
    if (anthropicEl) anthropicEl.textContent = origin;

    const googleGenaiEl = document.getElementById('googleGenaiEndpointUrl');
    if (googleGenaiEl) googleGenaiEl.textContent = origin;

    try {
        const response = await fetch('./api/auth/keys', { headers: getAuthHeaders() });
        if (response.ok) {
            const data = await response.json();
            if (data.success) {
                const apiKey = data.api_key || '';
                if (apiKeyEl) {
                    apiKeyEl.value = apiKey;
                    if (!apiKeyEl.dataset.visibilityInitialized) {
                        setApiKeyVisibility(false);
                    }
                }
                const regenerateBtn = document.getElementById('regenerateApiKeyBtn');
                if (regenerateBtn) {
                    const managedByEnv = Boolean(data.managed_by_env);
                    regenerateBtn.disabled = managedByEnv;
                    regenerateBtn.title = managedByEnv
                        ? t('access.api_key_managed_env')
                        : t('regenerate_api_key');
                }
            }
        }
    } catch (e) {
        console.error("Failed to fetch API key", e);
    } finally {
        if (apiKeyEl) {
            apiKeyEl.classList.remove('skeleton', 'skeleton-control');
            apiKeyEl.setAttribute('aria-busy', 'false');
            apiKeyEl.setAttribute('aria-label', t('access.api_key_copy_label'));
        }
    }
}

function setApiKeyVisibility(visible) {
    const input = document.getElementById('apiKey');
    const button = document.getElementById('toggleApiKeyVisibilityBtn');
    if (!input) return;

    input.type = visible ? 'text' : 'password';
    input.dataset.visibilityInitialized = 'true';
    input.dataset.visible = visible ? 'true' : 'false';

    if (button) {
        const label = visible ? t('access.hide_api_key') : t('show_api_key');
        button.title = label;
        button.setAttribute('aria-label', label);
        button.innerHTML = visible
            ? '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3l18 18"></path><path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"></path><path d="M9.9 5.2A9.6 9.6 0 0 1 12 5c6.5 0 10 7 10 7a18.3 18.3 0 0 1-3.1 4.3"></path><path d="M6.5 6.8C3.7 8.6 2 12 2 12s3.5 7 10 7a9.8 9.8 0 0 0 4.1-.9"></path></svg>'
            : '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"></path><circle cx="12" cy="12" r="3"></circle></svg>';
    }
}

function toggleApiKeyVisibility() {
    const input = document.getElementById('apiKey');
    if (!input) return;
    setApiKeyVisibility(input.type === 'password');
}

async function copyTextToClipboard(text) {
    const value = String(text || '');
    if (!value) return false;

    if (navigator.clipboard && window.isSecureContext) {
        try {
            await navigator.clipboard.writeText(value);
            return true;
        } catch (error) {
            // Fall through to the legacy path below. Public HTTP deployments do
            // not always expose the modern clipboard API.
        }
    }

    const textarea = document.createElement('textarea');
    textarea.value = value;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.inset = '0 auto auto 0';
    textarea.style.width = '1px';
    textarea.style.height = '1px';
    textarea.style.opacity = '0';
    textarea.style.pointerEvents = 'none';

    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);

    let copied = false;
    try {
        copied = document.execCommand('copy');
    } catch (error) {
        copied = false;
    } finally {
        document.body.removeChild(textarea);
    }

    return copied;
}

async function copyTextWithStatus(text) {
    const copied = await copyTextToClipboard(text);
    showStatus(t(copied ? 'copy_success' : 'copy_fail'), copied ? 'success' : 'error');
    return copied;
}

function cpUrl(element) {
    const text = element.textContent || element.innerText;
    if (!text) return;
    copyTextWithStatus(text.trim());
}

function copyInputValue(inputId) {
    const input = document.getElementById(inputId);
    if (!input || !input.value || input.value === '...') return;
    if (document.activeElement === input) {
        input.blur();
    }
    copyTextWithStatus(input.value);
}

async function regenerateApiKey() {
    if (!(await showConfirmModal(t('confirm_regenerate_key'), {
        title: t('confirm_regenerate_key_title'),
        confirmLabel: t('btn_regenerate')
    }))) {
        return;
    }
    try {
        const response = await fetch('./api/auth/keys/reset', {
            method: 'POST',
            headers: getAuthHeaders()
        });
        const data = await response.json().catch(() => ({}));
        if (response.ok) {
            if (data.success) {
                const el = document.getElementById('apiKey');
                const apiKey = data.api_key || '';
                if (el) {
                    el.value = apiKey;
                    if (!el.dataset.visibilityInitialized) {
                        setApiKeyVisibility(false);
                    }
                }
                showStatus(t('regenerate_success'), 'success');
            } else {
                showStatus(data.error || t('api_key.regenerate_failed'), 'error');
            }
        } else {
            showStatus(data.detail || data.message || t('api_key.regenerate_failed'), 'error');
        }
    } catch (e) {
        console.error("Failed to regenerate the API key.", e);
        showStatus(t('status_net_error', {error: e.message}), 'error');
    }
}
