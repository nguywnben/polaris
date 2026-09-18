const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('frontend/js/features/usage-pagination.js', 'utf8');

function setup() {
    const requests = [], statuses = [], sections = new Map();
    let period = '1d', renders = 0, healthRenders = 0, lastRenderGroup = null;
    const context = vm.createContext({
        URLSearchParams, Date,
        AppState: {usagePageSize: 10, historicalUsagePageSize: 10, usagePage: 1, historicalUsagePage: 1},
        getUsagePeriodConfig: () => ({value: period}), getAuthHeaders: () => ({}), t: key => key,
        renderUsageList: group => { renders++; lastRenderGroup = group; },
        renderProviderHealthMatrix: () => { healthRenders++; },
        showStatus: (...args) => statuses.push(args),
        document: {getElementById: id => {
            if (!sections.has(id)) sections.set(id, {
                setAttribute(name, value) { this[name] = value; },
                removeAttribute(name) { delete this[name]; },
            });
            return sections.get(id);
        }},
    });
    context.fetch = async url => {
        const query = new URL(url, 'http://test').searchParams;
        requests.push(query);
        return context.respond(query);
    };
    context.respond = query => response(query);
    vm.runInContext(source + '\n;globalThis.pages = UsagePages;', context);
    return {context, requests, statuses, sections, setPeriod: value => { period = value; },
        get renders() { return renders; }, get lastRenderGroup() { return lastRenderGroup; },
        get healthRenders() { return healthRenders; }};
}

function response(query, {total = 205, empty = false, marker = ''} = {}) {
    const offset = Number(query.get('offset')), size = Number(query.get('page_size'));
    const group = query.get('group');
    const data = Object.fromEntries(Array.from({length: empty ? 0 : Math.min(size, Math.max(0, total - offset))},
        (_, index) => [`${group}-${offset + index}.json`, {calls: 1, marker}]));
    return {ok: true, json: async () => ({success: true, data, total_items: total,
        offset, page_size: size, has_more: offset + size < total, provider_totals: []})};
}

function defer() {
    let resolve;
    const promise = new Promise(done => { resolve = done; });
    return {promise, resolve};
}

async function pagesBeyond100AndIndependentGroups() {
    const test = setup(), c = test.context;
    await c.loadUsagePages();
    assert.equal(test.requests.length, 2, 'initial detail load has exactly one bounded request per group');
    for (let index = 0; index < 10; index++) await c.moveUsagePage('current', 1);
    assert.equal(c.AppState.usagePage, 11);
    assert.equal(c.pages.current.offset, 100);
    assert.equal(c.AppState.usageStatsData['current-100.json'].calls, 1);
    await c.moveUsagePage('historical', 1);
    assert.equal(c.AppState.historicalUsagePage, 2);
    assert.equal(c.pages.historical.offset, 10);
    assert.equal(c.pages.current.offset, 100, 'moving historical must retain the current page');
    assert.equal(test.requests.at(-1).get('group'), 'historical',
        'changing a page only fetches the requested usage group');
    assert(test.requests.every(query => query.get('order') === 'name' && query.get('page_size') === '10'));
}

async function failedFetchRetainsBothPages() {
    const test = setup(), c = test.context;
    await c.loadUsagePages();
    const oldCurrent = c.pages.current, oldHistorical = c.pages.historical, oldData = c.AppState.usageStatsData;
    c.respond = query => query.get('group') === 'current' ? {ok: false} : response(query);
    await c.moveUsagePage('current', 1);
    assert.equal(c.pages.current, oldCurrent);
    assert.equal(c.pages.historical, oldHistorical);
    assert.equal(c.AppState.usageStatsData, oldData);
    assert.equal(c.AppState.usagePage, 1);
    assert.equal(test.renders, 0);
    assert.deepEqual(test.statuses, [['failed_to_load_usage_statistics', 'error']]);
    assert.equal(c.pages.busy, false);
    assert.equal(test.sections.get('usageList')['aria-busy'], undefined);
}

async function staleResponseCannotReplaceNewPeriod() {
    const test = setup(), c = test.context, pending = [];
    c.respond = query => {
        const item = defer(); pending.push({query, ...item}); return item.promise;
    };
    const oldLoad = c.loadUsagePages();
    test.setPeriod('7d');
    c.respond = query => response(query, {marker: 'new-period'});
    assert.equal(await c.loadUsagePages(), true);
    const newest = c.AppState.usageStatsData;
    for (const item of pending) item.resolve(response(item.query, {marker: 'old-period'}));
    assert.equal(await oldLoad, false);
    assert.equal(c.AppState.usageStatsData, newest);
    assert.equal(c.pages.period, '7d');
    assert.equal(c.AppState.usageStatsData['current-0.json'].marker, 'new-period');
}

async function clampOnceAfterDeletion() {
    const test = setup(), c = test.context;
    await c.loadUsagePages();
    await c.loadUsagePages({current: 21});
    test.requests.length = 0;
    c.respond = query => response(query, {total: 15});
    await c.loadUsagePages();
    assert.deepEqual(test.requests.filter(query => query.get('group') === 'current')
        .map(query => Number(query.get('offset'))), [200, 10]);
    assert.equal(c.AppState.usagePage, 2);
    assert.equal(Object.keys(c.pages.current.data).length, 5);
    test.requests.length = 0;
    c.respond = query => response(query, {total: 15, empty: true});
    await c.loadUsagePages({current: 3});
    assert.equal(test.requests.filter(query => query.get('group') === 'current').length, 2,
        'another deletion during clamp must not trigger an unbounded retry');
}

async function busyDoubleDispatchDoesNotAdvanceTwice() {
    const test = setup(), c = test.context, pending = [];
    await c.loadUsagePages();
    test.requests.length = 0;
    c.respond = query => {
        const item = defer(); pending.push({query, ...item}); return item.promise;
    };
    const move = c.moveUsagePage('current', 1);
    assert.equal(test.sections.get('usageList')['aria-busy'], 'true');
    await c.moveUsagePage('current', 1);
    assert.equal(test.requests.length, 1, 'busy navigation permits only one request for the requested group');
    for (const item of pending) item.resolve(response(item.query));
    await move;
    assert.equal(c.AppState.usagePage, 2);
    assert.equal(test.renders, 1);
    assert.equal(test.lastRenderGroup, 'current', 'page changes render only the requested usage table');
    assert.equal(test.healthRenders, 0, 'changing a page does not rebuild the provider health matrix');
    assert.equal(c.pages.busy, false);
}

(async () => {
    for (const test of [pagesBeyond100AndIndependentGroups, failedFetchRetainsBothPages,
        staleResponseCannotReplaceNewPeriod, clampOnceAfterDeletion, busyDoubleDispatchDoesNotAdvanceTwice]) {
        await test();
        console.log(`${test.name}: passed`);
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
