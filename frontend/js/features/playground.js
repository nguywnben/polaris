const PLAYGROUND_MAX_MESSAGES = 32;
const PLAYGROUND_MAX_MESSAGE_CHARS = 65536;
const PLAYGROUND_MAX_TOTAL_CHARS = 524288;
const PLAYGROUND_MAX_OUTPUT_BYTES = 2 * 1024 * 1024;
const PLAYGROUND_RENDER_INTERVAL_MS = 50;
const PLAYGROUND_KEY_PLACEHOLDER = '<YOUR_POLARIS_KEY>';
const PLAYGROUND_HANDOFF_KEY = 'polaris_playground_handoff_v1';
const PLAYGROUND_PROTOCOLS = new Set([
    'openai_chat', 'openai_responses', 'anthropic_messages', 'gemini'
]);

function normalizePlaygroundDraft(draft) {
    const protocol = String(draft?.protocol || 'openai_chat');
    const model = String(draft?.model || '').trim();
    const system = String(draft?.system || '');
    const messages = Array.isArray(draft?.messages) ? draft.messages.map(message => ({
        role: message?.role === 'assistant' ? 'assistant' : 'user',
        content: String(message?.content || '')
    })) : [];
    if (!PLAYGROUND_PROTOCOLS.has(protocol)) throw new Error('playground.error_protocol');
    if (!model || model.length > 256 || /[\u0000-\u001f]/.test(model)) {
        throw new Error('playground.error_model');
    }
    if (!messages.length || messages.length > PLAYGROUND_MAX_MESSAGES) {
        throw new Error('playground.error_message_count');
    }
    if (system.length > PLAYGROUND_MAX_MESSAGE_CHARS ||
        messages.some(message => message.content.length > PLAYGROUND_MAX_MESSAGE_CHARS)) {
        throw new Error('playground.error_message_length');
    }
    if (messages.some(message => !message.content.trim())) {
        throw new Error('playground.error_empty_message');
    }
    if (!messages.some(message => message.role === 'user' && message.content.trim())) {
        throw new Error('playground.error_user_message');
    }
    const totalChars = system.length + messages.reduce((sum, message) => sum + message.content.length, 0);
    if (totalChars > PLAYGROUND_MAX_TOTAL_CHARS) throw new Error('playground.error_total_length');
    const timeoutSeconds = Number(draft?.timeoutSeconds);
    const maxTokens = Number(draft?.maxTokens);
    if (!Number.isInteger(timeoutSeconds) || timeoutSeconds < 1 || timeoutSeconds > 120) {
        throw new Error('playground.error_timeout');
    }
    if (!Number.isInteger(maxTokens) || maxTokens < 1 || maxTokens > 65536) {
        throw new Error('playground.error_max_tokens');
    }
    const optionalNumber = (value, minimum, maximum, errorKey) => {
        if (value === null || value === undefined || value === '') return null;
        const number = Number(value);
        if (!Number.isFinite(number) || number < minimum || number > maximum) {
            throw new Error(errorKey);
        }
        return number;
    };
    return {
        protocol, model, system, messages, timeoutSeconds, maxTokens,
        stream: draft?.stream === true,
        temperature: optionalNumber(draft?.temperature, 0, protocol === 'anthropic_messages' ? 1 : 2, 'playground.error_temperature'),
        topP: optionalNumber(draft?.topP, 0, 1, 'playground.error_top_p')
    };
}

function buildPlaygroundRequest(draft) {
    const value = normalizePlaygroundDraft(draft);
    let request;
    if (value.protocol === 'openai_chat') {
        request = {
            messages: [
                ...(value.system ? [{role: 'system', content: value.system}] : []),
                ...value.messages
            ],
            max_tokens: value.maxTokens
        };
    } else if (value.protocol === 'openai_responses') {
        request = {input: value.messages, max_output_tokens: value.maxTokens};
        if (value.system) request.instructions = value.system;
    } else if (value.protocol === 'anthropic_messages') {
        request = {messages: value.messages, max_tokens: value.maxTokens};
        if (value.system) request.system = value.system;
    } else {
        request = {
            contents: value.messages.map(message => ({
                role: message.role === 'assistant' ? 'model' : 'user',
                parts: [{text: message.content}]
            })),
            generationConfig: {maxOutputTokens: value.maxTokens}
        };
        if (value.system) request.systemInstruction = {parts: [{text: value.system}]};
    }
    const parameters = value.protocol === 'gemini' ? request.generationConfig : request;
    if (value.temperature !== null) parameters.temperature = value.temperature;
    if (value.topP !== null) parameters[value.protocol === 'gemini' ? 'topP' : 'top_p'] = value.topP;
    return {
        schema_version: 'playground-request.v1',
        protocol: value.protocol,
        model: value.model,
        stream: value.stream,
        timeout_seconds: value.timeoutSeconds,
        request
    };
}

function playgroundPublicRequest(draft) {
    const boundary = buildPlaygroundRequest(draft);
    if (boundary.protocol === 'gemini') return boundary.request;
    return {...boundary.request, model: boundary.model, stream: boundary.stream};
}

function playgroundPublicPath(boundary) {
    if (boundary.protocol === 'openai_chat') return '/v1/chat/completions';
    if (boundary.protocol === 'openai_responses') return '/v1/responses';
    if (boundary.protocol === 'anthropic_messages') return '/v1/messages';
    const action = boundary.stream ? 'streamGenerateContent' : 'generateContent';
    return `/v1beta/models/${encodeURIComponent(boundary.model)}:${action}`;
}

function shellSingleQuoted(value) {
    return `'${String(value).replace(/'/g, `'"'"'`)}'`;
}

function powershellSingleQuoted(value) {
    return `'${String(value).replace(/'/g, "''")}'`;
}

function pythonJsonLiteral(value) {
    return JSON.stringify(JSON.stringify(value));
}

function buildPlaygroundExample(draft, format = 'curl', origin = '') {
    const boundary = buildPlaygroundRequest(draft);
    const baseUrl = String(origin || '').replace(/\/$/, '');
    const payload = playgroundPublicRequest(draft);
    if (format === 'curl') {
        const headers = boundary.protocol === 'anthropic_messages'
            ? [`x-api-key: ${PLAYGROUND_KEY_PLACEHOLDER}`, 'anthropic-version: 2023-06-01']
            : boundary.protocol === 'gemini'
                ? [`x-goog-api-key: ${PLAYGROUND_KEY_PLACEHOLDER}`]
                : [`Authorization: Bearer ${PLAYGROUND_KEY_PLACEHOLDER}`];
        return [
            `curl ${shellSingleQuoted(baseUrl + playgroundPublicPath(boundary))} \\`,
            ...headers.map(header => `  -H ${shellSingleQuoted(header)} \\`),
            `  -H 'Content-Type: application/json' \\`,
            `  -d ${shellSingleQuoted(JSON.stringify(payload))}`
        ].join('\n');
    }
    if (format === 'powershell') {
        const headers = boundary.protocol === 'anthropic_messages'
            ? [`x-api-key: ${PLAYGROUND_KEY_PLACEHOLDER}`, 'anthropic-version: 2023-06-01']
            : boundary.protocol === 'gemini'
                ? [`x-goog-api-key: ${PLAYGROUND_KEY_PLACEHOLDER}`]
                : [`Authorization: Bearer ${PLAYGROUND_KEY_PLACEHOLDER}`];
        const continuation = '`';
        return [
            `curl.exe ${powershellSingleQuoted(baseUrl + playgroundPublicPath(boundary))} ${continuation}`,
            ...headers.map(header => `  -H ${powershellSingleQuoted(header)} ${continuation}`),
            `  -H 'Content-Type: application/json' ${continuation}`,
            `  --data-raw ${powershellSingleQuoted(JSON.stringify(payload))}`
        ].join('\n');
    }
    if (format === 'node') {
        const requestLiteral = JSON.stringify(payload, null, 2);
        const printResponse = boundary.stream
            ? 'for await (const event of response) console.log(event);'
            : 'console.log(response);';
        if (boundary.protocol === 'anthropic_messages') {
            return `// npm install @anthropic-ai/sdk\n// ESM: save as client.mjs, then run: node client.mjs\nimport Anthropic from "@anthropic-ai/sdk";\n\nconst client = new Anthropic({ apiKey: "${PLAYGROUND_KEY_PLACEHOLDER}", baseURL: "${baseUrl}" });\nconst request = ${requestLiteral};\nconst response = await client.messages.create(request);\n${printResponse}`;
        }
        if (boundary.protocol === 'gemini') {
            const method = boundary.stream ? 'generateContentStream' : 'generateContent';
            return `// npm install @google/genai\n// ESM: save as client.mjs, then run: node client.mjs\nimport { GoogleGenAI } from "@google/genai";\n\nconst client = new GoogleGenAI({ apiKey: "${PLAYGROUND_KEY_PLACEHOLDER}", httpOptions: { baseUrl: "${baseUrl}" } });\nconst request = ${requestLiteral};\nconst response = await client.models.${method}({\n  model: ${JSON.stringify(boundary.model)},\n  contents: request.contents,\n  config: {\n    ...request.generationConfig,\n    ...(request.systemInstruction ? { systemInstruction: request.systemInstruction } : {})\n  }\n});\n${printResponse}`;
        }
        const method = boundary.protocol === 'openai_responses'
            ? 'responses.create'
            : 'chat.completions.create';
        return `// npm install openai\n// ESM: save as client.mjs, then run: node client.mjs\nimport OpenAI from "openai";\n\nconst client = new OpenAI({ apiKey: "${PLAYGROUND_KEY_PLACEHOLDER}", baseURL: "${baseUrl}/v1" });\nconst request = ${requestLiteral};\nconst response = await client.${method}(request);\n${printResponse}`;
    }
    const requestLiteral = pythonJsonLiteral(payload);
    if (boundary.protocol === 'anthropic_messages') {
        const consume = boundary.stream ? 'for event in response:\n    print(event)' : 'print(response)';
        return `# pip install anthropic\nimport json\nfrom anthropic import Anthropic\n\nclient = Anthropic(api_key="${PLAYGROUND_KEY_PLACEHOLDER}", base_url="${baseUrl}")\nrequest = json.loads(${requestLiteral})\nsampling = {}\nif "temperature" in request:\n    sampling["temperature"] = request.pop("temperature")\nif "top_p" in request:\n    sampling["top_p"] = request.pop("top_p")\nif sampling:\n    request["extra_body"] = sampling\nresponse = client.messages.create(**request)\n${consume}`;
    }
    if (boundary.protocol === 'gemini') {
        const method = boundary.stream ? 'generate_content_stream' : 'generate_content';
        const generation = boundary.request.generationConfig || {};
        const sdkConfig = {max_output_tokens: generation.maxOutputTokens};
        if (generation.temperature !== undefined) sdkConfig.temperature = generation.temperature;
        if (generation.topP !== undefined) sdkConfig.top_p = generation.topP;
        if (boundary.request.systemInstruction) {
            sdkConfig.system_instruction = boundary.request.systemInstruction.parts[0].text;
        }
        const configLiteral = pythonJsonLiteral(sdkConfig);
        const consume = boundary.stream ? 'for chunk in response:\n    print(chunk)' : 'print(response)';
        return `# pip install google-genai\nimport json\nfrom google import genai\nfrom google.genai import types\n\nclient = genai.Client(api_key="${PLAYGROUND_KEY_PLACEHOLDER}", http_options=types.HttpOptions(base_url="${baseUrl}"))\nrequest = json.loads(${requestLiteral})\nconfig = types.GenerateContentConfig(**json.loads(${configLiteral}))\nresponse = client.models.${method}(model=${JSON.stringify(boundary.model)}, contents=request["contents"], config=config)\n${consume}`;
    }
    const method = boundary.protocol === 'openai_responses' ? 'responses.create' : 'chat.completions.create';
    const consume = boundary.stream ? 'for event in response:\n    print(event)' : 'print(response)';
    return `# pip install openai\nimport json\nfrom openai import OpenAI\n\nclient = OpenAI(api_key="${PLAYGROUND_KEY_PLACEHOLDER}", base_url="${baseUrl}/v1")\nrequest = json.loads(${requestLiteral})\nresponse = client.${method}(**request)\n${consume}`;
}

function decodePlaygroundMetadataHeader(value) {
    if (!value) return null;
    const normalized = String(value).replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized + '='.repeat((4 - normalized.length % 4) % 4);
    const binary = typeof atob === 'function'
        ? atob(padded)
        : Buffer.from(padded, 'base64').toString('binary');
    const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
}

function splitPlaygroundStream(source) {
    const frames = String(source || '').replace(/\r\n/g, '\n').split('\n\n');
    const output = [];
    let metadata = null;
    for (const frame of frames) {
        if (!frame) continue;
        const lines = frame.split('\n');
        if (lines.some(line => line.trim() === 'event: polaris.playground.metadata')) {
            const data = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trim()).join('\n');
            try { metadata = JSON.parse(data); } catch (_error) { metadata = null; }
            continue;
        }
        output.push(frame);
    }
    return {output: output.join('\n\n') + (output.length ? '\n\n' : ''), metadata};
}

function replacePlaygroundText(element, value) {
    if (element) element.textContent = String(value ?? '');
}

function playgroundRuntimeState() {
    if (!AppState.playground) {
        AppState.playground = {
            initialized: false,
            messages: [{role: 'user', content: ''}],
            controller: null,
            running: false,
            cancelReason: '',
            hasRun: false,
            outcomeKey: 'playground.not_run',
            outcomeType: 'muted',
            runStateKey: 'playground.ready'
        };
    }
    const state = AppState.playground;
    if (!state.outcomeKey) state.outcomeKey = 'playground.not_run';
    if (!state.outcomeType) state.outcomeType = 'muted';
    if (!state.runStateKey) state.runStateKey = 'playground.ready';
    if (typeof state.hasRun !== 'boolean') state.hasRun = false;
    return state;
}

function createPlaygroundOption(value, label, selected) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    option.selected = selected;
    return option;
}

function createPlaygroundMessageRow(message, index) {
    const row = document.createElement('div');
    row.className = 'playground-message';
    row.dataset.playgroundMessage = String(index);

    const header = document.createElement('div');
    header.className = 'playground-message-header';
    const title = document.createElement('strong');
    title.className = 'playground-message-title';
    title.textContent = t('playground.message_number', {number: index + 1});
    const actions = document.createElement('div');
    actions.className = 'playground-message-actions';

    const roleLabel = document.createElement('label');
    roleLabel.className = 'playground-message-role';
    const roleText = document.createElement('span');
    roleText.className = 'visually-hidden';
    roleText.textContent = t('playground.role');
    const role = document.createElement('select');
    role.dataset.playgroundRole = String(index);
    role.dataset.uiChange = 'playground-draft';
    role.append(
        createPlaygroundOption('user', t('playground.role_user'), message.role === 'user'),
        createPlaygroundOption('assistant', t('playground.role_assistant'), message.role === 'assistant')
    );
    roleLabel.append(roleText, role);

    const contentLabel = document.createElement('label');
    contentLabel.className = 'playground-message-content';
    const contentText = document.createElement('span');
    contentText.className = 'playground-message-label';
    contentText.textContent = t('playground.content');
    const content = document.createElement('textarea');
    content.rows = 4;
    content.maxLength = PLAYGROUND_MAX_MESSAGE_CHARS;
    content.required = true;
    content.dataset.playgroundContent = String(index);
    content.setAttribute('data-playground-input', '');
    content.placeholder = t('playground.message_placeholder');
    content.value = message.content;
    contentLabel.append(contentText, content);

    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'btn btn-secondary btn-small playground-message-remove';
    remove.dataset.uiAction = 'playground-remove-message';
    remove.dataset.messageIndex = String(index);
    remove.disabled = playgroundRuntimeState().messages.length === 1;
    remove.textContent = t('playground.remove');
    remove.setAttribute('aria-label', t('playground.remove_message', {number: index + 1}));

    actions.append(roleLabel, remove);
    header.append(title, actions);
    row.append(header, contentLabel);
    return row;
}

function syncPlaygroundMessagesFromDom() {
    const state = playgroundRuntimeState();
    const rows = Array.from(document.querySelectorAll('[data-playground-message]'));
    if (!rows.length) return;
    state.messages = rows.map(row => ({
        role: row.querySelector('[data-playground-role]')?.value === 'assistant' ? 'assistant' : 'user',
        content: row.querySelector('[data-playground-content]')?.value || ''
    }));
}

function renderPlaygroundMessages() {
    const state = playgroundRuntimeState();
    const container = document.getElementById('playgroundMessages');
    if (!container) return;
    container.replaceChildren(...state.messages.map(createPlaygroundMessageRow));
    replacePlaygroundText(
        document.getElementById('playgroundMessageCount'),
        `${state.messages.length} / ${PLAYGROUND_MAX_MESSAGES}`
    );
    const addButton = document.getElementById('playgroundAddMessage');
    if (addButton) addButton.disabled = state.running || state.messages.length >= PLAYGROUND_MAX_MESSAGES;
}

function addPlaygroundMessage() {
    const state = playgroundRuntimeState();
    if (state.running || state.messages.length >= PLAYGROUND_MAX_MESSAGES) return;
    syncPlaygroundMessagesFromDom();
    state.messages.push({role: 'user', content: ''});
    renderPlaygroundMessages();
    document.querySelector('[data-playground-message]:last-child textarea')?.focus();
    updatePlaygroundExample();
}

function removePlaygroundMessage(index) {
    const state = playgroundRuntimeState();
    if (state.running || state.messages.length <= 1) return;
    syncPlaygroundMessagesFromDom();
    state.messages.splice(Number(index), 1);
    renderPlaygroundMessages();
    updatePlaygroundExample();
}

function readPlaygroundDraft() {
    syncPlaygroundMessagesFromDom();
    const value = id => document.getElementById(id)?.value ?? '';
    return {
        protocol: value('playgroundProtocol'),
        model: value('playgroundModel'),
        stream: Boolean(document.getElementById('playgroundStream')?.checked),
        timeoutSeconds: Number(value('playgroundTimeout')),
        system: value('playgroundSystem'),
        messages: playgroundRuntimeState().messages,
        maxTokens: Number(value('playgroundMaxTokens')),
        temperature: value('playgroundTemperature'),
        topP: value('playgroundTopP')
    };
}

function playgroundErrorText(error) {
    const key = error instanceof Error ? error.message : '';
    return key.startsWith('playground.') ? t(key) : t('playground.error_unavailable');
}

function updatePlaygroundExample() {
    const target = document.getElementById('playgroundExample');
    if (!target) return;
    try {
        const format = document.getElementById('playgroundExampleFormat')?.value || 'curl';
        replacePlaygroundText(target, buildPlaygroundExample(readPlaygroundDraft(), format, window.location.origin));
        renderPlaygroundValidation('');
    } catch (_error) {
        replacePlaygroundText(target, t('playground.example_incomplete'));
    }
}

function syncPlaygroundProtocol() {
    const protocol = document.getElementById('playgroundProtocol')?.value || 'openai_chat';
    replacePlaygroundText(document.getElementById('playgroundProtocolHint'), t(`playground.protocol_${protocol}`));
    const temperature = document.getElementById('playgroundTemperature');
    if (temperature) {
        temperature.max = protocol === 'anthropic_messages' ? '1' : '2';
        if (temperature.value && Number(temperature.value) > Number(temperature.max)) {
            temperature.value = temperature.max;
        }
    }
    updatePlaygroundExample();
}

function readPlaygroundHandoff() {
    let handoff = null;
    try {
        const stored = sessionStorage.getItem(PLAYGROUND_HANDOFF_KEY);
        sessionStorage.removeItem(PLAYGROUND_HANDOFF_KEY);
        if (stored) handoff = JSON.parse(stored);
    } catch (_error) {
        handoff = null;
    }
    const query = new URLSearchParams(window.location.search);
    const queryModel = query.get('source') === 'models' ? query.get('model') : '';
    const candidate = queryModel || (
        handoff?.schema_version === 'playground-handoff.v1' && handoff?.source === 'models'
            ? handoff.model
            : ''
    );
    if (typeof candidate === 'string' && candidate === candidate.trim() &&
        candidate.length > 0 && candidate.length <= 256 && !/[\u0000-\u001f]/.test(candidate)) {
        return candidate;
    }
    return '';
}

function initializePlayground() {
    const state = playgroundRuntimeState();
    const handoffModel = readPlaygroundHandoff();
    if (handoffModel) document.getElementById('playgroundModel').value = handoffModel;
    if (!state.initialized) {
        state.initialized = true;
    }
    renderPlaygroundMessages();
    syncPlaygroundProtocol();
    setPlaygroundOutcome(state.outcomeKey, state.outcomeType);
    setPlaygroundRunState(state.runStateKey);
    if (!state.hasRun) {
        replacePlaygroundText(document.getElementById('playgroundOutput'), t('playground.empty_prompt'));
    }
    syncPlaygroundPresentation();
}

function syncPlaygroundPresentation() {
    const state = playgroundRuntimeState();
    document.getElementById('playgroundOutputCard')?.classList.toggle('is-pristine', !state.hasRun);
}

function setPlaygroundRunning(running) {
    const state = playgroundRuntimeState();
    state.running = running;
    const run = document.getElementById('playgroundRun');
    const cancel = document.getElementById('playgroundCancel');
    if (run) {
        run.disabled = running;
        run.dataset.i18n = running ? 'playground.running' : 'playground.run';
        run.textContent = t(run.dataset.i18n);
        if (running) run.setAttribute('aria-busy', 'true');
        else run.removeAttribute('aria-busy');
    }
    if (cancel) cancel.disabled = !running;
    document.querySelectorAll('#playgroundForm input, #playgroundForm select, #playgroundForm textarea, #playgroundAddMessage, [data-ui-action="playground-remove-message"]').forEach(control => {
        if (control.id !== 'playgroundCancel' && control.id !== 'playgroundRun') control.disabled = running;
    });
    if (!running) renderPlaygroundMessages();
}

function renderPlaygroundError(message) {
    const target = document.getElementById('playgroundError');
    if (!target) return;
    replacePlaygroundText(target, message);
    target.classList.toggle('hidden', !message);
    if (message) target.focus();
}

function renderPlaygroundValidation(message) {
    const target = document.getElementById('playgroundValidation');
    if (!target) return;
    replacePlaygroundText(target, message);
    target.classList.toggle('hidden', !message);
    if (message) target.focus();
}

function setPlaygroundOutcome(outcomeKey, type = 'muted') {
    const state = playgroundRuntimeState();
    state.outcomeKey = outcomeKey;
    state.outcomeType = type;
    const badge = document.getElementById('playgroundOutcome');
    if (!badge) return;
    badge.className = `status-badge ${['success', 'warning', 'danger', 'muted'].includes(type) ? type : 'muted'}`;
    replacePlaygroundText(badge, t(outcomeKey));
}

function setPlaygroundRunState(runStateKey) {
    playgroundRuntimeState().runStateKey = runStateKey;
    const runState = document.getElementById('playgroundRunState');
    replacePlaygroundText(runState, t(runStateKey));
    if (runState) runState.hidden = runStateKey === 'playground.ready';
}

function renderPlaygroundMetadata(metadata) {
    const panel = document.getElementById('playgroundMetadata');
    if (!panel) return;
    panel.classList.toggle('hidden', !metadata);
    if (!metadata) return;
    const route = metadata.route || {};
    const usage = metadata.usage || {};
    const quality = metadata.quality || {};
    replacePlaygroundText(document.getElementById('playgroundMetadataOutcome'), metadata.outcome || '—');
    replacePlaygroundText(document.getElementById('playgroundMetadataRequestId'), metadata.request_id || '—');
    replacePlaygroundText(document.getElementById('playgroundMetadataRoute'),
        [route.selected_provider, route.selected_model].filter(Boolean).join(' / ') || t('playground.route_unavailable'));
    replacePlaygroundText(document.getElementById('playgroundMetadataAttempts'),
        `${formatConsoleNumber(route.attempts)} / ${formatConsoleNumber(route.fallbacks)}`);
    replacePlaygroundText(document.getElementById('playgroundMetadataTokens'),
        `${formatConsoleNumber(usage.input_tokens)} / ${formatConsoleNumber(usage.output_tokens)}`);
    replacePlaygroundText(document.getElementById('playgroundMetadataDuration'), `${formatConsoleNumber(metadata.duration_ms)} ms`);
    replacePlaygroundText(document.getElementById('playgroundMetadataQuality'),
        `${quality.profile || '—'} · r${formatConsoleNumber(quality.policy_revision)}`);
    replacePlaygroundText(document.getElementById('playgroundMetadataCompression'),
        `${quality.compression_action || '—'} · ${formatConsoleNumber(quality.estimated_tokens_before)} → ${formatConsoleNumber(quality.estimated_tokens_after)}`);
}

function playgroundResponseError(source, statusCode) {
    const candidates = [
        String(source || ''),
        ...String(source || '').split('\n')
            .filter(line => line.startsWith('data:'))
            .map(line => line.slice(5).trim())
    ];
    for (const candidate of candidates) {
        try {
            const payload = JSON.parse(candidate);
            const detail = typeof payload.detail === 'string' ? payload.detail : '';
            const message = typeof payload.error?.message === 'string' ? payload.error.message : '';
            const code = typeof payload.error?.code === 'string' ? payload.error.code : '';
            const nativeError = [code, message || detail].filter(Boolean).join(': ');
            if (nativeError) return nativeError;
        } catch (_error) {
            // Continue through the bounded response and use the stable status fallback below.
        }
    }
    return t('playground.error_status', {status: statusCode});
}

async function readBoundedPlaygroundResponse(response, onChunk, onLimit) {
    if (!response.body?.getReader) {
        const source = await response.text();
        if (new TextEncoder().encode(source).byteLength > PLAYGROUND_MAX_OUTPUT_BYTES) {
            throw new Error('playground.error_output_limit');
        }
        onChunk(source);
        return source;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let source = '';
    let receivedBytes = 0;
    let lastRenderAt = 0;
    try {
        while (true) {
            const {value, done} = await reader.read();
            if (done) break;
            receivedBytes += value.byteLength;
            if (receivedBytes > PLAYGROUND_MAX_OUTPUT_BYTES) {
                await reader.cancel();
                onLimit?.();
                throw new Error('playground.error_output_limit');
            }
            source += decoder.decode(value, {stream: true});
            const now = Date.now();
            if (now - lastRenderAt >= PLAYGROUND_RENDER_INTERVAL_MS) {
                onChunk(source);
                lastRenderAt = now;
            }
        }
        source += decoder.decode();
        onChunk(source);
        return source;
    } finally {
        reader.releaseLock();
    }
}

async function runPlayground() {
    const state = playgroundRuntimeState();
    if (state.running) return;
    let boundary;
    try {
        boundary = buildPlaygroundRequest(readPlaygroundDraft());
    } catch (error) {
        renderPlaygroundValidation(playgroundErrorText(error));
        return;
    }
    renderPlaygroundValidation('');
    renderPlaygroundError('');
    renderPlaygroundMetadata(null);
    state.hasRun = true;
    syncPlaygroundPresentation();
    replacePlaygroundText(document.getElementById('playgroundOutput'), t('playground.connecting'));
    setPlaygroundOutcome('playground.running', 'warning');
    setPlaygroundRunState('playground.running');
    state.controller = new AbortController();
    state.cancelReason = '';
    setPlaygroundRunning(true);
    try {
        const response = await fetch('./api/playground/runs', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(boundary),
            signal: state.controller.signal
        });
        const source = await readBoundedPlaygroundResponse(
            response,
            partial => {
                replacePlaygroundText(document.getElementById('playgroundOutput'), partial || t('playground.waiting'));
            },
            () => {
                state.cancelReason = 'limit';
                state.controller?.abort();
            }
        );
        const streamed = boundary.stream ? splitPlaygroundStream(source) : {output: source, metadata: null};
        let metadata = streamed.metadata;
        if (!metadata) {
            try { metadata = decodePlaygroundMetadataHeader(response.headers.get('x-polaris-playground-metadata')); }
            catch (_error) { metadata = null; }
        }
        let output = streamed.output;
        if (!boundary.stream) {
            try { output = JSON.stringify(JSON.parse(source), null, 2); } catch (_error) { output = source; }
        }
        replacePlaygroundText(document.getElementById('playgroundOutput'), output || t('playground.empty_output'));
        renderPlaygroundMetadata(metadata);
        const effectiveStatus = Number(metadata?.status_code || response.status);
        if (!response.ok || effectiveStatus >= 400) {
            renderPlaygroundError(playgroundResponseError(boundary.stream ? streamed.output : source, effectiveStatus));
            setPlaygroundOutcome('playground.failed', 'danger');
            setPlaygroundRunState('playground.failed');
        } else {
            setPlaygroundOutcome('playground.succeeded', 'success');
            setPlaygroundRunState('playground.succeeded');
        }
    } catch (error) {
        if (error?.name === 'AbortError' || state.cancelReason === 'user') {
            setPlaygroundOutcome('playground.cancelled', 'warning');
            setPlaygroundRunState('playground.cancelled');
        } else {
            const message = playgroundErrorText(error);
            renderPlaygroundError(message);
            setPlaygroundOutcome('playground.failed', 'danger');
            setPlaygroundRunState('playground.failed');
        }
    } finally {
        state.controller = null;
        state.cancelReason = '';
        setPlaygroundRunning(false);
    }
}

function cancelPlayground() {
    const state = playgroundRuntimeState();
    if (!state.controller) return;
    state.cancelReason = 'user';
    AppState.playground.controller.abort();
    setPlaygroundRunState('playground.cancelling');
}

async function copyPlaygroundExample() {
    try {
        const format = document.getElementById('playgroundExampleFormat')?.value || 'curl';
        const example = buildPlaygroundExample(readPlaygroundDraft(), format, window.location.origin);
        await copyTextWithStatus(example);
    } catch (error) {
        renderPlaygroundValidation(playgroundErrorText(error));
    }
}

if (typeof document !== 'undefined') {
    document.addEventListener('polaris:locale-change', () => {
        const state = playgroundRuntimeState();
        if (!state.initialized) return;
        syncPlaygroundMessagesFromDom();
        renderPlaygroundMessages();
        syncPlaygroundProtocol();
        setPlaygroundOutcome(state.outcomeKey, state.outcomeType);
        setPlaygroundRunState(state.runStateKey);
        if (!state.hasRun) {
            replacePlaygroundText(document.getElementById('playgroundOutput'), t('playground.empty_prompt'));
        }
    });
}
