const VirtualKeyAccessState = {
    records: [],
    loaded: false,
    loading: false,
    query: '',
    status: ''
};

const ACCESS_CLIENT_KEY_PLACEHOLDER = '<YOUR_OMNI_VIRTUAL_KEY>';

function loadAccessPage() {
    renderAccessClientExample();
    return Promise.all([updateEndpointUrls(), loadVirtualKeys()]);
}

function buildAccessClientExample(
    protocol,
    origin = window.location.origin,
    format = document.getElementById('accessClientFormat')?.value || 'curl'
) {
    const baseUrl = String(origin || '').replace(/\/$/, '');
    const examples = {
        curl: {
            openai_chat: `curl "${baseUrl}/v1/chat/completions" \\
  -H "Authorization: Bearer ${ACCESS_CLIENT_KEY_PLACEHOLDER}" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"omway","messages":[{"role":"user","content":"Hello"}]}'`,
            openai_responses: `curl "${baseUrl}/v1/responses" \\
  -H "Authorization: Bearer ${ACCESS_CLIENT_KEY_PLACEHOLDER}" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"omway","input":"Hello"}'`,
            anthropic: `curl "${baseUrl}/v1/messages" \\
  -H "x-api-key: ${ACCESS_CLIENT_KEY_PLACEHOLDER}" \\
  -H "anthropic-version: 2023-06-01" \\
  -H "content-type: application/json" \\
  -d '{"model":"omway","max_tokens":256,"messages":[{"role":"user","content":"Hello"}]}'`,
            gemini: `curl "${baseUrl}/v1beta/models/omway:generateContent" \\
  -H "x-goog-api-key: ${ACCESS_CLIENT_KEY_PLACEHOLDER}" \\
  -H "Content-Type: application/json" \\
  -d '{"contents":[{"role":"user","parts":[{"text":"Hello"}]}]}'`
        },
        powershell: {
            openai_chat: `curl.exe '${baseUrl}/v1/chat/completions' \`
  -H 'Authorization: Bearer ${ACCESS_CLIENT_KEY_PLACEHOLDER}' \`
  -H 'Content-Type: application/json' \`
  --data-raw '{"model":"omway","messages":[{"role":"user","content":"Hello"}]}'`,
            openai_responses: `curl.exe '${baseUrl}/v1/responses' \`
  -H 'Authorization: Bearer ${ACCESS_CLIENT_KEY_PLACEHOLDER}' \`
  -H 'Content-Type: application/json' \`
  --data-raw '{"model":"omway","input":"Hello"}'`,
            anthropic: `curl.exe '${baseUrl}/v1/messages' \`
  -H 'x-api-key: ${ACCESS_CLIENT_KEY_PLACEHOLDER}' \`
  -H 'anthropic-version: 2023-06-01' \`
  -H 'Content-Type: application/json' \`
  --data-raw '{"model":"omway","max_tokens":256,"messages":[{"role":"user","content":"Hello"}]}'`,
            gemini: `curl.exe '${baseUrl}/v1beta/models/omway:generateContent' \`
  -H 'x-goog-api-key: ${ACCESS_CLIENT_KEY_PLACEHOLDER}' \`
  -H 'Content-Type: application/json' \`
  --data-raw '{"contents":[{"role":"user","parts":[{"text":"Hello"}]}]}'`
        },
        python: {
            openai_chat: `# pip install openai\nfrom openai import OpenAI\n\nclient = OpenAI(api_key="${ACCESS_CLIENT_KEY_PLACEHOLDER}", base_url="${baseUrl}/v1")\nresponse = client.chat.completions.create(model="omway", messages=[{"role": "user", "content": "Hello"}])\nprint(response)`,
            openai_responses: `# pip install openai\nfrom openai import OpenAI\n\nclient = OpenAI(api_key="${ACCESS_CLIENT_KEY_PLACEHOLDER}", base_url="${baseUrl}/v1")\nresponse = client.responses.create(model="omway", input="Hello")\nprint(response)`,
            anthropic: `# pip install anthropic\nfrom anthropic import Anthropic\n\nclient = Anthropic(api_key="${ACCESS_CLIENT_KEY_PLACEHOLDER}", base_url="${baseUrl}")\nresponse = client.messages.create(model="omway", max_tokens=256, messages=[{"role": "user", "content": "Hello"}])\nprint(response)`,
            gemini: `# pip install google-genai\nfrom google import genai\nfrom google.genai import types\n\nclient = genai.Client(api_key="${ACCESS_CLIENT_KEY_PLACEHOLDER}", http_options=types.HttpOptions(base_url="${baseUrl}"))\nresponse = client.models.generate_content(model="omway", contents="Hello")\nprint(response)`
        },
        node: {
            openai_chat: `// npm install openai\n// ESM: save as client.mjs, then run: node client.mjs\nimport OpenAI from "openai";\n\nconst client = new OpenAI({ apiKey: "${ACCESS_CLIENT_KEY_PLACEHOLDER}", baseURL: "${baseUrl}/v1" });\nconst response = await client.chat.completions.create({ model: "omway", messages: [{ role: "user", content: "Hello" }] });\nconsole.log(response);`,
            openai_responses: `// npm install openai\n// ESM: save as client.mjs, then run: node client.mjs\nimport OpenAI from "openai";\n\nconst client = new OpenAI({ apiKey: "${ACCESS_CLIENT_KEY_PLACEHOLDER}", baseURL: "${baseUrl}/v1" });\nconst response = await client.responses.create({ model: "omway", input: "Hello" });\nconsole.log(response);`,
            anthropic: `// npm install @anthropic-ai/sdk\n// ESM: save as client.mjs, then run: node client.mjs\nimport Anthropic from "@anthropic-ai/sdk";\n\nconst client = new Anthropic({ apiKey: "${ACCESS_CLIENT_KEY_PLACEHOLDER}", baseURL: "${baseUrl}" });\nconst response = await client.messages.create({ model: "omway", max_tokens: 256, messages: [{ role: "user", content: "Hello" }] });\nconsole.log(response);`,
            gemini: `// npm install @google/genai\n// ESM: save as client.mjs, then run: node client.mjs\nimport { GoogleGenAI } from "@google/genai";\n\nconst client = new GoogleGenAI({ apiKey: "${ACCESS_CLIENT_KEY_PLACEHOLDER}", httpOptions: { baseUrl: "${baseUrl}" } });\nconst response = await client.models.generateContent({ model: "omway", contents: "Hello" });\nconsole.log(response);`
        }
    };
    const selected = examples[format] || examples.curl;
    return selected[protocol] || selected.openai_chat;
}

function renderAccessClientExample(protocol = document.getElementById('accessProtocol')?.value) {
    const output = document.getElementById('accessClientExample');
    if (!output) return '';
    const example = buildAccessClientExample(protocol || 'openai_chat');
    output.textContent = example;
    return example;
}

function copyAccessClientExample() {
    const example = renderAccessClientExample();
    if (example) void copyTextWithStatus(example);
}

async function virtualKeyApi(path = '', options = {}) {
    const response = await fetch(`./api/virtual-keys${path}`, {
        ...options,
        headers: {
            ...getAuthHeaders(options.body !== undefined),
            ...(options.headers || {})
        }
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.success === false) {
        const detail = typeof payload.detail === 'string'
            ? payload.detail
            : t('access.request_failed');
        const error = new Error(detail);
        error.status = response.status;
        throw error;
    }
    return payload;
}

async function loadVirtualKeys({ announce = false } = {}) {
    if (VirtualKeyAccessState.loading) return;
    const list = document.getElementById('virtualKeyList');
    const preserveContent = VirtualKeyAccessState.loaded;
    VirtualKeyAccessState.loading = true;
    clearPageState('virtualKeyState');
    if (list) list.setAttribute('aria-busy', 'true');
    try {
        const payload = await virtualKeyApi('', { headers: getAuthHeaders(false) });
        VirtualKeyAccessState.records = Array.isArray(payload.data) ? payload.data : [];
        VirtualKeyAccessState.loaded = true;
        clearPageState('virtualKeyState');
        renderVirtualKeys();
        if (announce) showStatus(t('access.keys_refreshed'), 'success');
    } catch (error) {
        if (!preserveContent) {
            VirtualKeyAccessState.records = [];
            document.getElementById('virtualKeyEmptyState')?.classList.add('hidden');
        }
        const message = t('access.keys_load_failed', { error: error.message });
        showPageState('virtualKeyState', {
            kind: preserveContent ? 'stale' : 'error',
            title: t(preserveContent ? 'warning' : 'error'),
            message,
            actionLabel: t('refresh'),
            onAction: () => loadVirtualKeys({announce: true})
        });
        showStatus(message, 'error');
    } finally {
        VirtualKeyAccessState.loading = false;
        if (list) list.setAttribute('aria-busy', 'false');
    }
}

function formatVirtualKeyDate(value) {
    if (!value) return t('access.never');
    const date = new Date(Number(value) * 1000);
    if (!Number.isFinite(date.getTime())) return t('access.unknown');
    return new Intl.DateTimeFormat(getActiveLocale(), {
        dateStyle: 'medium',
        timeStyle: 'short'
    }).format(date);
}

function formatVirtualKeyNumber(value) {
    return formatConsoleNumber(value, {maximumFractionDigits: 2});
}

function formatVirtualKeyLimits(record) {
    const limits = [];
    if (record.rpm_limit) limits.push(`${formatVirtualKeyNumber(record.rpm_limit)} RPM`);
    if (record.tpm_limit) limits.push(`${formatVirtualKeyNumber(record.tpm_limit)} TPM`);
    if (record.budget_daily_usd !== null && record.budget_daily_usd !== undefined) {
        limits.push(t('access.daily_budget_value', { value: formatVirtualKeyNumber(record.budget_daily_usd) }));
    }
    if (record.budget_monthly_usd !== null && record.budget_monthly_usd !== undefined) {
        limits.push(t('access.monthly_budget_value', { value: formatVirtualKeyNumber(record.budget_monthly_usd) }));
    }
    return limits.length ? limits.join(' · ') : t('access.no_limits');
}

function formatVirtualKeyPricingPolicy(record) {
    const policy = record.unknown_pricing_policy || 'deny';
    const label = t(`access.pricing_${policy}`);
    const fallback = Number(record.fallback_price_usd_per_million);
    if (policy !== 'fallback' || !Number.isFinite(fallback) || fallback <= 0) return label;
    return `${label} ($${formatVirtualKeyNumber(fallback)}/1M)`;
}

function virtualKeyStatusLabel(status) {
    const supported = new Set(['active', 'disabled', 'expired', 'revoked']);
    const safeStatus = supported.has(status) ? status : 'unknown';
    return t(`access.status_${safeStatus}`);
}

function visibleVirtualKeys() {
    const query = VirtualKeyAccessState.query.trim().toLocaleLowerCase();
    return VirtualKeyAccessState.records.filter((record) => {
        if (VirtualKeyAccessState.status && record.status !== VirtualKeyAccessState.status) return false;
        if (!query) return true;
        return [record.name, record.id, record.key_preview]
            .some((value) => String(value || '').toLocaleLowerCase().includes(query));
    });
}

function renderVirtualKeys() {
    const list = document.getElementById('virtualKeyList');
    const empty = document.getElementById('virtualKeyEmptyState');
    if (!list || !empty) return;
    const records = visibleVirtualKeys();
    list.replaceChildren(...records.map(renderVirtualKeyCard));
    empty.classList.toggle('hidden', records.length > 0);
}

function renderVirtualKeyCard(record) {
    const article = document.createElement('article');
    const status = ['active', 'disabled', 'expired', 'revoked'].includes(record.status)
        ? record.status
        : 'unknown';
    const terminal = status === 'revoked';
    const scopes = Array.isArray(record.scopes) ? record.scopes : [];
    const models = Array.isArray(record.allowed_models) ? record.allowed_models : [];
    article.className = 'virtual-key-card';
    article.dataset.keyId = String(record.id || '');
    article.innerHTML = `
        <div class="virtual-key-card-heading">
            <div class="virtual-key-identity">
                <strong>${escapeHtml(record.name || record.id)}</strong>
                <code>${escapeHtml(record.key_preview || record.id)}</code>
            </div>
            <span class="status-badge virtual-key-status ${escapeAttribute(status)}">${escapeHtml(virtualKeyStatusLabel(status))}</span>
        </div>
        <dl class="virtual-key-metadata">
            <div><dt>${escapeHtml(t('access.last_used'))}</dt><dd>${escapeHtml(formatVirtualKeyDate(record.last_used_at))}</dd></div>
            <div><dt>${escapeHtml(t('access.expires'))}</dt><dd>${escapeHtml(formatVirtualKeyDate(record.expires_at))}</dd></div>
            <div><dt>${escapeHtml(t('access.limits'))}</dt><dd>${escapeHtml(formatVirtualKeyLimits(record))}</dd></div>
            <div><dt>${escapeHtml(t('access.pricing_policy'))}</dt><dd>${escapeHtml(formatVirtualKeyPricingPolicy(record))}</dd></div>
        </dl>
        <div class="virtual-key-policy-row">
            <div><span class="virtual-key-policy-label">${escapeHtml(t('access.scopes'))}</span><div class="virtual-key-chips">${scopes.map((scope) => `<code>${escapeHtml(scope)}</code>`).join('')}</div></div>
            <div><span class="virtual-key-policy-label">${escapeHtml(t('access.models'))}</span><div class="virtual-key-chips">${(models.length ? models : [t('access.all_models')]).map((model) => `<code>${escapeHtml(model)}</code>`).join('')}</div></div>
        </div>
        <div class="virtual-key-actions">
            <button type="button" class="btn btn-secondary btn-small" data-ui-action="virtual-key-usage" data-key-id="${escapeAttribute(record.id)}">${escapeHtml(t('access.view_usage'))}</button>
            <button type="button" class="btn btn-secondary btn-small" data-ui-action="virtual-key-edit" data-key-id="${escapeAttribute(record.id)}" ${terminal ? 'disabled' : ''}>${escapeHtml(t('access.edit_key'))}</button>
            <button type="button" class="btn btn-secondary btn-small" data-ui-action="virtual-key-rotate" data-key-id="${escapeAttribute(record.id)}" ${terminal ? 'disabled' : ''}>${escapeHtml(t('access.rotate_key'))}</button>
            <button type="button" class="btn btn-danger btn-small" data-ui-action="virtual-key-revoke" data-key-id="${escapeAttribute(record.id)}" ${terminal ? 'disabled' : ''}>${escapeHtml(t('access.revoke_key'))}</button>
        </div>
    `;
    return article;
}

function findVirtualKeyRecord(keyId) {
    return VirtualKeyAccessState.records.find((record) => record.id === keyId) || null;
}

function editVirtualKey(keyId) {
    const record = findVirtualKeyRecord(keyId);
    if (record) openVirtualKeyForm(record);
}

function trapVirtualKeyModalFocus(modal, event) {
    if (event.key !== 'Tab') return;
    const focusable = Array.from(modal.querySelectorAll(
        'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [href], [tabindex]:not([tabindex="-1"])'
    )).filter((element) => !element.hidden && element.getClientRects().length > 0);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
    }
}

function virtualKeyDateTimeValue(timestamp) {
    if (!timestamp) return '';
    const date = new Date(Number(timestamp) * 1000);
    if (!Number.isFinite(date.getTime())) return '';
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 16);
}

function virtualKeyOptionalNumber(value) {
    return value === null || value === undefined ? '' : String(value);
}

function openVirtualKeyForm(record = null) {
    const editing = Boolean(record);
    const modal = document.createElement('div');
    modal.className = 'message-modal-overlay';
    modal.innerHTML = `
        <div class="message-modal virtual-key-form-modal" role="dialog" aria-modal="true" aria-labelledby="virtualKeyFormTitle">
            <div class="message-modal-header"><h3 id="virtualKeyFormTitle">${escapeHtml(t(editing ? 'access.edit_key_title' : 'access.create_key_title'))}</h3></div>
            <form id="virtualKeyForm">
                <div class="message-modal-body virtual-key-form-body">
                    <div class="form-grid">
                        <label class="form-group"><span>${escapeHtml(t('access.key_name'))}</span><input name="name" required maxlength="128" autocomplete="off" placeholder="${escapeAttribute(t('access.key_name_placeholder'))}" value="${escapeAttribute(record?.name || '')}"></label>
                        ${editing ? `<label class="form-group virtual-key-enabled"><span>${escapeHtml(t('access.key_enabled'))}</span><input type="checkbox" class="config-checkbox" name="enabled" ${record.enabled ? 'checked' : ''}></label>` : ''}
                        <label class="form-group"><span>${escapeHtml(t('access.expires_at'))}</span><input type="datetime-local" name="expires_at" value="${escapeAttribute(virtualKeyDateTimeValue(record?.expires_at))}"></label>
                        <label class="form-group"><span>${escapeHtml(t('access.rpm_limit'))}</span><input type="number" name="rpm_limit" min="1" step="1" inputmode="numeric" placeholder="${escapeAttribute(t('access.rpm_limit_placeholder'))}" value="${escapeAttribute(virtualKeyOptionalNumber(record?.rpm_limit))}"></label>
                        <label class="form-group"><span>${escapeHtml(t('access.tpm_limit'))}</span><input type="number" name="tpm_limit" min="1" step="1" inputmode="numeric" placeholder="${escapeAttribute(t('access.tpm_limit_placeholder'))}" value="${escapeAttribute(virtualKeyOptionalNumber(record?.tpm_limit))}"></label>
                        <label class="form-group"><span>${escapeHtml(t('access.daily_budget'))}</span><input type="number" name="budget_daily_usd" min="0" step="0.01" inputmode="decimal" placeholder="${escapeAttribute(t('access.daily_budget_placeholder'))}" value="${escapeAttribute(virtualKeyOptionalNumber(record?.budget_daily_usd))}"></label>
                        <label class="form-group"><span>${escapeHtml(t('access.monthly_budget'))}</span><input type="number" name="budget_monthly_usd" min="0" step="0.01" inputmode="decimal" placeholder="${escapeAttribute(t('access.monthly_budget_placeholder'))}" value="${escapeAttribute(virtualKeyOptionalNumber(record?.budget_monthly_usd))}"></label>
                    </div>
                    <fieldset class="virtual-key-fieldset">
                        <legend>${escapeHtml(t('access.scopes'))}</legend>
                        ${virtualKeyScopeOptions(record)}
                    </fieldset>
                    <label class="form-group"><span>${escapeHtml(t('access.allowed_models'))}</span><textarea name="allowed_models" rows="3" maxlength="8256" placeholder="${escapeAttribute(t('access.allowed_models_placeholder'))}">${escapeHtml((record?.allowed_models || []).join('\n'))}</textarea></label>
                    <div class="form-grid">
                        <label class="form-group"><span>${escapeHtml(t('access.pricing_policy'))}</span><select name="unknown_pricing_policy" data-ui-change="virtual-key-pricing"><option value="deny" ${record?.unknown_pricing_policy !== 'warn' && record?.unknown_pricing_policy !== 'fallback' ? 'selected' : ''}>${escapeHtml(t('access.pricing_deny'))}</option><option value="warn" ${record?.unknown_pricing_policy === 'warn' ? 'selected' : ''}>${escapeHtml(t('access.pricing_warn'))}</option><option value="fallback" ${record?.unknown_pricing_policy === 'fallback' ? 'selected' : ''}>${escapeHtml(t('access.pricing_fallback'))}</option></select></label>
                        <label class="form-group"><span>${escapeHtml(t('access.fallback_price'))}</span><input type="number" name="fallback_price_usd_per_million" min="0.000001" max="100000" step="0.01" inputmode="decimal" placeholder="${escapeAttribute(t('access.fallback_price_placeholder'))}" value="${escapeAttribute(virtualKeyOptionalNumber(record?.fallback_price_usd_per_million))}"></label>
                    </div>
                </div>
                <div class="message-modal-footer"><button type="button" class="message-modal-btn" data-virtual-key-cancel>${escapeHtml(t('btn_cancel'))}</button><button type="submit" class="message-modal-btn message-modal-btn-primary">${escapeHtml(t(editing ? 'access.save_key' : 'access.create_key'))}</button></div>
            </form>
        </div>
    `;
    const form = modal.querySelector('#virtualKeyForm');
    const close = () => {
        document.removeEventListener('keydown', onEscape);
        void unmountModal(modal);
    };
    const onEscape = (event) => {
        if (event.key === 'Escape') close();
        trapVirtualKeyModalFocus(modal, event);
    };
    modal.addEventListener('click', (event) => {
        if (event.target === modal || event.target.closest('[data-virtual-key-cancel]')) close();
    });
    form?.addEventListener('submit', (event) => submitVirtualKeyForm(event, record, close));
    document.addEventListener('keydown', onEscape);
    void mountModal(modal).then(() => {
        syncVirtualKeyPricingControl(form);
        form?.elements.namedItem('name')?.focus();
    });
}

function virtualKeyScopeOptions(record) {
    const selected = new Set(record?.scopes || [
        'inference:openai', 'inference:anthropic', 'inference:gemini'
    ]);
    return [
        ['inference:openai', 'OpenAI'],
        ['inference:anthropic', 'Anthropic'],
        ['inference:gemini', 'Google GenAI'],
        ['management:read', t('access.management_read')],
        ['management:write', t('access.management_write')]
    ].map(([scope, label]) => {
        const detail = scope === 'management:write'
            ? `${scope} · ${t('access.management_write_requires_read')}`
            : scope;
        return `<label class="switch-row"><input type="checkbox" class="config-checkbox" name="scopes" value="${escapeAttribute(scope)}" data-ui-change="virtual-key-scope" ${selected.has(scope) ? 'checked' : ''}><span><strong>${escapeHtml(label)}</strong><small>${escapeHtml(detail)}</small></span></label>`;
    }).join('');
}

function syncVirtualKeyScopeControl(input) {
    const form = input?.form;
    if (!form) return;
    const read = form.querySelector('input[name="scopes"][value="management:read"]');
    const write = form.querySelector('input[name="scopes"][value="management:write"]');
    if (input === write && write.checked) read.checked = true;
    if (input === read && !read.checked) write.checked = false;
}

function syncVirtualKeyPricingControl(form = document.getElementById('virtualKeyForm')) {
    if (!form) return;
    const policy = form.elements.namedItem('unknown_pricing_policy');
    const fallback = form.elements.namedItem('fallback_price_usd_per_million');
    if (!policy || !fallback) return;
    const enabled = policy.value === 'fallback';
    fallback.disabled = !enabled;
    fallback.required = enabled;
    if (!enabled) fallback.value = '';
}

function parseVirtualKeyNumber(form, name) {
    const value = form.elements.namedItem(name)?.value?.trim();
    return value ? Number(value) : null;
}

async function submitVirtualKeyForm(event, record, close) {
    event.preventDefault();
    const form = event.currentTarget;
    const scopes = Array.from(form.querySelectorAll('input[name="scopes"]:checked'))
        .map((input) => input.value);
    if (!scopes.length) {
        showStatus(t('access.scope_required'), 'error');
        return;
    }
    const expiryValue = form.elements.namedItem('expires_at').value;
    const models = form.elements.namedItem('allowed_models').value
        .split(/[\n,]+/)
        .map((value) => value.trim())
        .filter(Boolean);
    const payload = {
        name: form.elements.namedItem('name').value.trim(),
        expires_at: expiryValue ? new Date(expiryValue).getTime() / 1000 : null,
        rpm_limit: parseVirtualKeyNumber(form, 'rpm_limit'),
        tpm_limit: parseVirtualKeyNumber(form, 'tpm_limit'),
        budget_daily_usd: parseVirtualKeyNumber(form, 'budget_daily_usd'),
        budget_monthly_usd: parseVirtualKeyNumber(form, 'budget_monthly_usd'),
        allowed_models: models,
        scopes,
        unknown_pricing_policy: form.elements.namedItem('unknown_pricing_policy').value,
        fallback_price_usd_per_million: parseVirtualKeyNumber(form, 'fallback_price_usd_per_million')
    };
    if (record) {
        payload.enabled = form.elements.namedItem('enabled').checked;
        payload.expected_revision = record.revision;
    }
    const submit = form.querySelector('[type="submit"]');
    if (submit) submit.disabled = true;
    try {
        const path = record ? `/${encodeURIComponent(record.id)}` : '';
        const response = await virtualKeyApi(path, {
            method: record ? 'PATCH' : 'POST',
            body: JSON.stringify(payload)
        });
        close();
        await loadVirtualKeys();
        if (record) {
            showStatus(t('access.key_saved'), 'success');
        } else {
            showVirtualKeySecret(response.key, 'access.key_created_title');
        }
    } catch (error) {
        await handleVirtualKeyMutationError(error);
        if (submit) submit.disabled = false;
    }
}

async function handleVirtualKeyMutationError(error) {
    if (error.status === 409) {
        showStatus(t('access.key_conflict'), 'warning');
        await loadVirtualKeys();
        return;
    }
    showStatus(error.message || t('access.request_failed'), 'error');
}

function showVirtualKeySecret(secret, titleKey) {
    let ephemeralSecret = String(secret || '');
    const modal = document.createElement('div');
    modal.className = 'message-modal-overlay';
    modal.innerHTML = `
        <div class="message-modal virtual-key-secret-modal" role="dialog" aria-modal="true" aria-labelledby="virtualKeySecretTitle">
            <div class="message-modal-header"><h3 id="virtualKeySecretTitle">${escapeHtml(t(titleKey))}</h3></div>
            <div class="message-modal-body">
                <p>${escapeHtml(t('access.secret_once'))}</p>
                <div class="secret-field"><input id="virtualKeySecret" type="text" readonly autocomplete="off" aria-label="${escapeAttribute(t('access.new_key_secret'))}"><button type="button" class="btn btn-secondary" data-virtual-key-copy>${escapeHtml(t('access.copy_secret'))}</button></div>
            </div>
            <div class="message-modal-footer"><button type="button" class="message-modal-btn message-modal-btn-primary" data-virtual-key-secret-close>${escapeHtml(t('access.secret_saved'))}</button></div>
        </div>
    `;
    const secretInput = modal.querySelector('#virtualKeySecret');
    secretInput.value = ephemeralSecret;
    const clearVirtualKeySecret = () => {
        secretInput.value = '';
        secretInput.removeAttribute('value');
        ephemeralSecret = '';
    };
    let closed = false;
    const close = () => {
        if (closed) return;
        closed = true;
        clearVirtualKeySecret();
        document.removeEventListener('keydown', onEscape);
        window.removeEventListener('pagehide', close);
        void unmountModal(modal).then(() => modal.replaceChildren());
    };
    const onEscape = (event) => {
        if (event.key === 'Escape') close();
        trapVirtualKeyModalFocus(modal, event);
    };
    modal.addEventListener('click', async (event) => {
        if (event.target.closest('[data-virtual-key-copy]')) {
            await copyTextWithStatus(secretInput.value);
        }
        if (event.target === modal || event.target.closest('[data-virtual-key-secret-close]')) close();
    });
    document.addEventListener('keydown', onEscape);
    window.addEventListener('pagehide', close, { once: true });
    void mountModal(modal).then(() => secretInput.focus());
}

async function rotateVirtualKey(keyId) {
    const record = findVirtualKeyRecord(keyId);
    if (!record) return;
    const confirmed = await showConfirmModal(t('access.rotate_confirm', { name: record.name }), {
        title: t('access.rotate_key_title'),
        confirmLabel: t('access.rotate_key')
    });
    if (!confirmed) return;
    try {
        const response = await virtualKeyApi(`/${encodeURIComponent(record.id)}/rotate`, {
            method: 'POST',
            body: JSON.stringify({ expected_revision: record.revision })
        });
        await loadVirtualKeys();
        showVirtualKeySecret(response.key, 'access.key_rotated_title');
    } catch (error) {
        await handleVirtualKeyMutationError(error);
    }
}

async function revokeVirtualKey(keyId) {
    const record = findVirtualKeyRecord(keyId);
    if (!record) return;
    const confirmed = await showConfirmModal(t('access.revoke_confirm', { name: record.name }), {
        title: t('access.revoke_key_title'),
        confirmLabel: t('access.revoke_key')
    });
    if (!confirmed) return;
    try {
        await virtualKeyApi(`/${encodeURIComponent(record.id)}/revoke`, {
            method: 'POST',
            body: JSON.stringify({ expected_revision: record.revision })
        });
        await loadVirtualKeys();
        showStatus(t('access.key_revoked'), 'success');
    } catch (error) {
        await handleVirtualKeyMutationError(error);
    }
}

async function showVirtualKeyUsage(keyId) {
    const record = findVirtualKeyRecord(keyId);
    if (!record) return;
    try {
        const response = await virtualKeyApi(`/${encodeURIComponent(record.id)}/usage`, {
            headers: getAuthHeaders(false)
        });
        const modal = document.createElement('div');
        modal.className = 'message-modal-overlay';
        modal.innerHTML = `
            <div class="message-modal" role="dialog" aria-modal="true" aria-labelledby="virtualKeyUsageTitle">
                <div class="message-modal-header"><h3 id="virtualKeyUsageTitle">${escapeHtml(t('access.usage_title', { name: record.name }))}</h3></div>
                <div class="message-modal-body"><div class="virtual-key-usage-grid">${renderVirtualKeyUsageWindow('access.last_24_hours', response.data?.daily)}${renderVirtualKeyUsageWindow('access.last_30_days', response.data?.monthly)}</div></div>
                <div class="message-modal-footer"><button type="button" class="message-modal-btn message-modal-btn-primary" data-virtual-key-usage-close>${escapeHtml(t('btn_close'))}</button></div>
            </div>
        `;
        let close = () => {};
        const onKeydown = (event) => {
            if (event.key === 'Escape') close();
            trapVirtualKeyModalFocus(modal, event);
        };
        close = () => {
            document.removeEventListener('keydown', onKeydown);
            void unmountModal(modal);
        };
        modal.addEventListener('click', (event) => {
            if (event.target === modal || event.target.closest('[data-virtual-key-usage-close]')) close();
        });
        document.addEventListener('keydown', onKeydown);
        void mountModal(modal).then(() => modal.querySelector('[data-virtual-key-usage-close]')?.focus());
    } catch (error) {
        showStatus(t('access.usage_load_failed', { error: error.message }), 'error');
    }
}

function renderVirtualKeyUsageWindow(labelKey, usage = {}) {
    return `<section class="virtual-key-usage-card"><h4>${escapeHtml(t(labelKey))}</h4><dl><div><dt>${escapeHtml(t('access.calls'))}</dt><dd>${escapeHtml(formatVirtualKeyNumber(usage.calls || 0))}</dd></div><div><dt>${escapeHtml(t('access.tokens'))}</dt><dd>${escapeHtml(formatVirtualKeyNumber(usage.total_tokens || 0))}</dd></div><div><dt>${escapeHtml(t('access.spend'))}</dt><dd>${escapeHtml(formatConsoleCurrency(usage.cost_usd || 0))}</dd></div></dl></section>`;
}

function updateVirtualKeySearch(value) {
    VirtualKeyAccessState.query = String(value || '');
    renderVirtualKeys();
}

function updateVirtualKeyStatus(value) {
    VirtualKeyAccessState.status = String(value || '');
    renderVirtualKeys();
}
