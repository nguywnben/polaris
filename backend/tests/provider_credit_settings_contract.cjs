const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync(process.argv[2], 'utf8');

class TestClassList {
    constructor() { this.values = new Set(); }
    add(value) { this.values.add(value); }
    remove(value) { this.values.delete(value); }
    toggle(value, force) {
        if (force === undefined ? !this.values.has(value) : force) this.values.add(value);
        else this.values.delete(value);
    }
    contains(value) { return this.values.has(value); }
}

class TestElement {
    constructor(id = '') {
        this.id = id;
        this.classList = new TestClassList();
        this.children = [];
        this.disabled = false;
        this.hidden = false;
        this.textContent = '';
        this.value = '';
        this.dataset = {};
        this.listeners = {};
    }
    addEventListener(name, handler) { this.listeners[name] = handler; }
    setAttribute(name, value) { this[name] = String(value); }
    replaceChildren(...children) {
        this.children = children;
        if (children.length && !this.value) this.value = children[0].value;
    }
}

const ids = [
    'antigravityCreditSettings', 'antigravityCreditLoading', 'antigravityCreditContent',
    'antigravityCreditEmpty', 'antigravityCreditError', 'antigravityCreditSelect',
    'antigravityCreditToggleBtn', 'antigravityCreditRefreshBtn', 'antigravityCreditPrevBtn',
    'antigravityCreditNextBtn', 'antigravityCreditPageInfo', 'antigravityCreditState'
];
const elements = new Map(ids.map((id) => [id, new TestElement(id)]));
const domListeners = {};
global.document = {
    getElementById(id) { return elements.get(id) || null; },
    createElement() { return new TestElement(); },
    addEventListener(name, handler) { domListeners[name] = handler; }
};
global.t = (key, values = {}) => `${key}:${JSON.stringify(values)}`;
global.getAuthHeaders = () => ({Authorization: 'panel'});
global.showConfirmModal = async () => true;
global.showStatus = () => {};

const requests = [];
let actionShouldFail = false;
global.fetch = async (url, options = {}) => {
    requests.push({url: String(url), options});
    if (String(url).includes('/status?')) {
        return {
            ok: true,
            async json() {
                return {
                    total: 2,
                    items: [
                        {filename: 'first.json', user_email: 'first@example.com', enable_credit: false},
                        {filename: 'second.json', user_email: '', enable_credit: true}
                    ]
                };
            }
        };
    }
    return {
        ok: !actionShouldFail,
        async json() {
            return actionShouldFail ? {detail: 'server rejected action'} : {message: 'updated'};
        }
    };
};

vm.runInThisContext(
    source + '\n;globalThis.__creditTest = {'
        + 'loadAntigravityCreditSettings, toggleAntigravityCredentialCredit, '
        + 'antigravityCreditState};'
);

function assert(condition, message) {
    if (!condition) throw new Error(message);
}

(async () => {
    const api = global.__creditTest;
    await api.loadAntigravityCreditSettings({page: 1});

    const statusRequest = requests[0];
    const statusUrl = new URL(statusRequest.url, 'https://polaris.test');
    assert(statusUrl.pathname.endsWith('/api/credentials/status'), 'wrong status endpoint');
    assert(statusUrl.searchParams.get('mode') === 'provider', 'provider mode missing');
    assert(statusUrl.searchParams.get('provider_filter') === 'google_antigravity', 'provider filter missing');
    assert(statusUrl.searchParams.get('limit') === '20', 'page bound must be 20');
    assert(!statusUrl.searchParams.has('include_content'), 'credential content must not be requested');
    assert(elements.get('antigravityCreditSelect').children.length === 2, 'safe summaries not rendered');
    assert(api.antigravityCreditState.items.length === 2, 'bounded page state missing');

    elements.get('antigravityCreditSelect').value = 'first.json';
    actionShouldFail = true;
    await api.toggleAntigravityCredentialCredit();
    assert(api.antigravityCreditState.items[0].enable_credit === false, 'error mutated credit state');
    assert(!elements.get('antigravityCreditContent').classList.contains('hidden'), 'error hid prior state');
    assert(!elements.get('antigravityCreditError').classList.contains('hidden'), 'error not exposed');

    actionShouldFail = false;
    await api.toggleAntigravityCredentialCredit();
    const actionRequest = requests.at(-1);
    const body = JSON.parse(actionRequest.options.body);
    assert(body.filename === 'first.json', 'selected credential not targeted');
    assert(body.action === 'enable_credit', 'wrong credit action');
    assert(api.antigravityCreditState.items[0].enable_credit === true, 'success did not update state');
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
