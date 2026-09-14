"""Browser-side contracts for the production Playground workflow."""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "frontend/js/features/playground.js"
FRAGMENT = ROOT / "frontend/fragments/pages/playground.html"
STYLES = ROOT / "frontend/css/playground.css"


class PlaygroundConsoleTests(unittest.TestCase):
    def _run_contract(self, assertions: str) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required for the Playground UI contract.")
        harness = f"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync({json.dumps(str(SCRIPT))}, 'utf8');
vm.runInThisContext(source + `\n;globalThis.__playgroundContract = {{
    buildPlaygroundRequest, buildPlaygroundExample, decodePlaygroundMetadataHeader,
    splitPlaygroundStream, replacePlaygroundText, readBoundedPlaygroundResponse,
    playgroundRuntimeState
}};`);
const {{buildPlaygroundRequest: build, buildPlaygroundExample: example,
    decodePlaygroundMetadataHeader: decode, splitPlaygroundStream: split,
    replacePlaygroundText: replaceText,
    readBoundedPlaygroundResponse: readBounded,
    playgroundRuntimeState: runtimeState}} = globalThis.__playgroundContract;
function assert(condition, message) {{ if (!condition) throw new Error(message); }}
{assertions}
"""
        result = subprocess.run(
            [node, "-e", harness],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_page_exposes_complete_bounded_workflow(self) -> None:
        fragment = FRAGMENT.read_text(encoding="utf-8")
        for element_id in (
            "playgroundTab",
            "playgroundForm",
            "playgroundProtocol",
            "playgroundModel",
            "playgroundStream",
            "playgroundTimeout",
            "playgroundSystem",
            "playgroundMessages",
            "playgroundAddMessage",
            "playgroundTemperature",
            "playgroundTopP",
            "playgroundMaxTokens",
            "playgroundRun",
            "playgroundCancel",
            "playgroundOutput",
            "playgroundError",
            "playgroundMetadata",
            "playgroundExample",
            "playgroundCopyExample",
        ):
            self.assertIn(f'id="{element_id}"', fragment)
        self.assertIn('maxlength="65536"', fragment)
        self.assertIn('aria-live="polite"', fragment)
        self.assertIn('data-ui-action="playground-run"', fragment)
        self.assertIn('data-ui-action="playground-cancel"', fragment)
        self.assertNotIn('data-ui-action="playground-clear"', fragment)
        self.assertNotIn('data-ui-action="playground-open-quality"', fragment)
        self.assertIn('<option value="curl">cURL (Bash)</option>', fragment)
        self.assertIn('<option value="powershell">PowerShell</option>', fragment)
        self.assertIn('<option value="node">Node.js SDK</option>', fragment)

        navigation = (ROOT / "frontend/js/features/navigation.js").read_text(encoding="utf-8")
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("'playground-clear'", navigation)
        self.assertNotIn("'playground-open-quality'", navigation)
        self.assertNotIn("function clearPlaygroundSession", source)

    def test_protocol_payloads_use_one_normalized_draft(self) -> None:
        self._run_contract(
            """
const draft = {
    model: 'polaris', stream: true, timeoutSeconds: 30, system: 'Be concise.',
    messages: [{role: 'user', content: 'Hello'}, {role: 'assistant', content: 'Hi'}],
    temperature: 0.4, topP: 0.8, maxTokens: 512
};
const chat = build({...draft, protocol: 'openai_chat'});
assert(chat.request.messages[0].role === 'system', 'chat system message');
assert(chat.request.max_tokens === 512 && chat.stream === true, 'chat parameters');
const responses = build({...draft, protocol: 'openai_responses'});
assert(responses.request.instructions === 'Be concise.', 'responses instructions');
assert(responses.request.max_output_tokens === 512, 'responses max tokens');
const anthropic = build({...draft, protocol: 'anthropic_messages'});
assert(anthropic.request.system === 'Be concise.', 'anthropic system');
assert(anthropic.request.max_tokens === 512, 'anthropic max tokens');
const gemini = build({...draft, protocol: 'gemini'});
assert(gemini.request.systemInstruction.parts[0].text === 'Be concise.', 'gemini system');
assert(gemini.request.contents[1].role === 'model', 'gemini assistant role');
assert(gemini.request.generationConfig.maxOutputTokens === 512, 'gemini max tokens');
let emptyMessageError = '';
try { build({...draft, protocol: 'openai_chat', messages: [{role: 'user', content: '   '}]}); }
catch (error) { emptyMessageError = error.message; }
assert(emptyMessageError === 'playground.error_empty_message', 'empty messages must fail locally');
"""
        )

    def test_run_button_announces_pending_and_restores_its_action(self) -> None:
        self._run_contract("""
globalThis.AppState = {};
globalThis.t = key => key;
const elements = new Map();
globalThis.document = {getElementById: id => {
    if (!elements.has(id)) elements.set(id, {disabled: false, dataset: {}, textContent: '',
        setAttribute(name, value) {this[name] = value;}, removeAttribute(name) {delete this[name];}});
    return elements.get(id);
}, querySelectorAll: () => []};
globalThis.renderPlaygroundMessages = () => {};
setPlaygroundRunning(true);
const run = elements.get('playgroundRun');
assert(run.textContent === 'playground.running', 'Pending action must be visible on the button');
assert(run.disabled && run['aria-busy'] === 'true', 'Pending submit is disabled and announced');
assert(!elements.get('playgroundCancel').disabled, 'Cancellation remains available');
setPlaygroundRunning(false);
assert(run.textContent === 'playground.run' && !run.disabled, 'Submit recovers after completion');
assert(!run['aria-busy'], 'Busy state cleared');
""")

    def test_copy_examples_are_protocol_accurate_and_never_contain_a_real_key(self) -> None:
        self._run_contract(
            """
const draft = {protocol: 'openai_chat', model: 'polaris', stream: false,
    timeoutSeconds: 30, system: '', messages: [{role: 'user', content: "What's new?"}],
    temperature: null, topP: null, maxTokens: 256};
        for (const format of ['curl', 'powershell', 'python', 'node']) {
            const text = example(draft, format, 'http://127.0.0.1:4283');
            assert(text.includes('<YOUR_POLARIS_KEY>'), `missing placeholder in ${format}`);
            assert(!text.includes('session-token') && !text.includes('AIza'), `secret in ${format}`);
        }
assert(example(draft, 'curl', 'http://127.0.0.1:4283').includes('/v1/chat/completions'), 'chat URL');
const powershell = example(draft, 'powershell', 'http://localhost');
assert(powershell.startsWith('curl.exe '), 'PowerShell must invoke curl.exe explicitly');
assert(powershell.includes(String.fromCharCode(96, 10)), 'PowerShell line continuation');
assert(example({...draft, protocol: 'openai_responses'}, 'python', 'http://localhost').includes('client.responses.create'), 'Responses SDK');
assert(example({...draft, protocol: 'anthropic_messages'}, 'python', 'http://localhost').includes('Anthropic('), 'Anthropic SDK');
const gemini = example({...draft, protocol: 'gemini', system: 'Be concise.'}, 'python', 'http://localhost');
assert(gemini.includes('genai.Client') && gemini.includes('types.GenerateContentConfig'), 'Gemini SDK');
assert(gemini.includes('system_instruction'), 'Gemini system instruction');
const nodeChat = example(draft, 'node', 'http://localhost');
assert(nodeChat.includes('new OpenAI') && nodeChat.includes('chat.completions.create'), 'Node OpenAI Chat SDK');
assert(example({...draft, protocol: 'openai_responses'}, 'node', 'http://localhost').includes('responses.create'), 'Node Responses SDK');
assert(example({...draft, protocol: 'anthropic_messages'}, 'node', 'http://localhost').includes('new Anthropic'), 'Node Anthropic SDK');
const nodeGemini = example({...draft, protocol: 'gemini', system: 'Be concise.'}, 'node', 'http://localhost');
assert(nodeGemini.includes('new GoogleGenAI') && nodeGemini.includes('generateContent'), 'Node Gemini SDK');
assert(nodeGemini.includes('systemInstruction'), 'Node Gemini system instruction');
"""
        )

    def test_python_stream_examples_consume_events_and_keep_anthropic_sampling_compatible(
        self,
    ) -> None:
        self._run_contract(
            """
const base = {model: 'polaris', stream: true, timeoutSeconds: 30, system: '',
    messages: [{role: 'user', content: 'Hello'}], temperature: null, topP: null,
    maxTokens: 256};
for (const protocol of ['openai_chat', 'openai_responses', 'anthropic_messages']) {
    const text = example({...base, protocol}, 'python', 'http://localhost');
    assert(text.includes('for event in response:'), `${protocol} must consume stream events`);
}
const geminiStream = example({...base, protocol: 'gemini'}, 'python', 'http://localhost');
assert(geminiStream.includes('for chunk in response:'), 'Gemini must consume stream chunks');
const anthropicSampling = example({...base, protocol: 'anthropic_messages', stream: false,
    temperature: 0.4, topP: 0.8}, 'python', 'http://localhost');
assert(anthropicSampling.includes('extra_body'), 'Anthropic sampling must use SDK extra_body');
assert(anthropicSampling.includes('request.pop("temperature")'), 'temperature moved from typed params');
assert(anthropicSampling.includes('request.pop("top_p")'), 'top_p moved from typed params');
assert(example({...base, protocol: 'openai_chat'}, 'node', 'http://localhost').includes('client.mjs'), 'Node ESM guidance');
"""
        )

    def test_stream_metadata_is_separated_and_untrusted_output_stays_text(self) -> None:
        self._run_contract(
            """
const metadata = {schema_version: 'playground-metadata.v1', status_code: 200};
const encoded = Buffer.from(JSON.stringify(metadata), 'utf8').toString('base64url');
assert(decode(encoded).status_code === 200, 'metadata header decode');
const hostile = '<img src=x onerror=globalThis.pwned=true>';
const stream = `data: ${JSON.stringify({choices: [{delta: {content: hostile}}]})}\n\nevent: polaris.playground.metadata\ndata: ${JSON.stringify(metadata)}\n\n`;
const result = split(stream);
assert(result.output.includes(hostile) && !result.output.includes('polaris.playground.metadata'), 'native stream split');
assert(result.metadata.status_code === 200, 'stream metadata');
const element = {textContent: '', innerHTML: 'unchanged'};
replaceText(element, hostile);
assert(element.textContent === hostile, 'output text retained');
assert(element.innerHTML === 'unchanged' && globalThis.pwned !== true, 'output must not execute');
"""
        )

    def test_runtime_state_is_memory_only_and_one_request_is_cancelable(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("new AbortController()", source)
        self.assertIn("AppState.playground.controller.abort()", source)
        self.assertIn("PLAYGROUND_MAX_MESSAGES = 32", source)
        self.assertIn("PLAYGROUND_MAX_TOTAL_CHARS = 524288", source)
        self.assertIn("PLAYGROUND_MAX_OUTPUT_BYTES = 2 * 1024 * 1024", source)
        self.assertIn("PLAYGROUND_RENDER_INTERVAL_MS = 50", source)
        self.assertIn("polaris:locale-change", source)
        self.assertIn("hasRun: false", source)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("sessionStorage.setItem", source)
        self.assertIn("sessionStorage.removeItem", source)
        self.assertNotIn(".innerHTML", source)

    def test_runtime_state_has_safe_first_visit_defaults(self) -> None:
        self._run_contract(
            """
globalThis.AppState = {};
const state = runtimeState();
assert(state.messages.length === 1 && state.messages[0].role === 'user', 'first message');
assert(state.hasRun === false, 'first visit output state');
assert(state.outcomeKey === 'playground.not_run', 'first visit outcome');
assert(state.runStateKey === 'playground.ready', 'first visit status');
"""
        )

    def test_first_visit_response_is_compact_and_quiet(self) -> None:
        fragment = FRAGMENT.read_text(encoding="utf-8")
        source = SCRIPT.read_text(encoding="utf-8")
        styles = (ROOT / "frontend/css/playground.css").read_text(encoding="utf-8")

        self.assertIn('id="playgroundOutputCard"', fragment)
        self.assertIn("syncPlaygroundPresentation", source)
        self.assertIn("playground-output-card.is-pristine", styles)
        self.assertIn("runState.hidden = runStateKey === 'playground.ready'", source)

    def test_response_display_limit_is_byte_bounded_and_cancels_the_run(self) -> None:
        self._run_contract(
            """
(async () => {
    let limitCalled = false;
    let errorKey = '';
    const response = new Response(new ReadableStream({
        start(controller) {
            controller.enqueue(new Uint8Array(1500000));
            controller.enqueue(new Uint8Array(700000));
        }
    }));
    try {
        await readBounded(response, () => {}, () => { limitCalled = true; });
    } catch (error) {
        errorKey = error.message;
    }
    assert(limitCalled, 'display limit must cancel the active request');
    assert(errorKey === 'playground.error_output_limit', 'display limit error key');
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
"""
        )

    def test_page_is_registered_and_responsive(self) -> None:
        index = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
        sidebar = (ROOT / "frontend/fragments/layout/sidebar.html").read_text(encoding="utf-8")
        navigation = (ROOT / "frontend/js/core/navigation.js").read_text(encoding="utf-8")
        root = (ROOT / "backend/core/panel/root.py").read_text(encoding="utf-8")
        styles = STYLES.read_text(encoding="utf-8")

        self.assertIn("include:fragments/pages/playground.html", index)
        self.assertIn('data-tab="playground"', sidebar)
        self.assertIn("'/playground': 'playground'", navigation)
        self.assertIn("playground: '/playground'", navigation)
        self.assertIn("playground: () => initializePlayground()", navigation)
        self.assertIn('@router.get("/playground"', root)
        self.assertIn('"pages/playground.html"', root)
        self.assertIn('"css/playground.css"', root)
        self.assertIn('"js/features/playground.js"', root)
        self.assertRegex(
            styles,
            r"(?s)@media \(max-width: 860px\).*?\.playground-workspace.*?grid-template-columns: minmax\(0, 1fr\)",
        )

    def test_page_keeps_guidance_inline_and_statuses_compact(self) -> None:
        fragment = (ROOT / "frontend/fragments/pages/playground.html").read_text(encoding="utf-8")
        styles = STYLES.read_text(encoding="utf-8")

        self.assertNotIn("playground-privacy-note", fragment)
        self.assertIn('class="status-badge muted"', fragment)
        self.assertIn("overflow-x: hidden", styles)
        self.assertIn("white-space: pre-wrap", styles)
        self.assertIn(".playground-stream-control small", styles)

    def test_stream_control_aligns_with_its_row_label_without_mouse_focus_halo(self) -> None:
        styles = STYLES.read_text(encoding="utf-8")

        self.assertRegex(
            styles,
            r"(?s)\.playground-stream-control\s*\{.*?align-self: start",
        )
        self.assertRegex(
            styles,
            r"(?s)\.playground-stream-control\s*>\s*input\[type=\"checkbox\"\]:focus\s*\{.*?box-shadow: none",
        )
        self.assertIn(
            ":where(button, a, input, select, textarea, summary):focus-visible",
            (ROOT / "frontend/css/foundation.css").read_text(encoding="utf-8"),
        )

    def test_client_example_format_matches_the_compact_action_height(self) -> None:
        styles = STYLES.read_text(encoding="utf-8")

        self.assertRegex(
            styles,
            r"(?s)\.playground-example-toolbar select\s*\{.*?min-height: 30px.*?height: 30px",
        )
        self.assertRegex(
            styles,
            r"(?s)\.playground-example\s*\{[^}]*font-size: 12px",
        )

    def test_message_editor_prioritizes_full_width_content(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        styles = STYLES.read_text(encoding="utf-8")

        for class_name in (
            "playground-message-header",
            "playground-message-title",
            "playground-message-actions",
            "playground-message-role",
            "playground-message-content",
        ):
            self.assertIn(class_name, source)
        self.assertIn("t('playground.content')", source)
        self.assertIn("row.append(header, contentLabel)", source)
        self.assertIn(".playground-message-content", styles)
        self.assertIn("width: 100%", styles)
        self.assertRegex(
            styles,
            r"(?s)\.playground-message \.playground-message-role select\s*\{.*?width: 122px.*?height: 30px",
        )
        self.assertRegex(
            styles,
            r"(?s)@media \(max-width: 600px\).*?\.playground-message-header.*?display: grid",
        )


if __name__ == "__main__":
    unittest.main()
