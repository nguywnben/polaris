const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
class Element {
    constructor() { this.textContent = ''; this.children = []; this.attributes = {}; this.classList = {add() {}, remove() {}}; }
    setAttribute(key, value) { this.attributes[key] = value; }
    removeAttribute(key) { delete this.attributes[key]; }
    replaceChildren() { this.children = []; }
    append(...children) { this.children.push(...children); }
    appendChild(child) { this.children.push(child); }
}
const elements = new Map(['UploadResult', 'UploadResultTitle', 'UploadResultText', 'UploadResultDetails'].map(key => ['fixture' + key, new Element()]));
global.document = {getElementById: id => elements.get(id), createElement: () => new Element()};
global.t = key => `localized:${key}`;
global.ensureTerminalPunctuation = value => value;
global.escapeHtml = value => String(value);
global.escapeAttribute = value => String(value);
global.formatUsageNumber = value => value;
global.formatConsoleNumber = value => value;
global.renderMessageResultRows = () => '';
global.getCredentialProviderMeta = () => ({name: 'Codex', logo: ''});
vm.runInThisContext(fs.readFileSync(path.join(root, 'frontend/js/core/upload-manager.js'), 'utf8'));
vm.runInThisContext(fs.readFileSync(path.join(root, 'frontend/js/features/credential-pool.js'), 'utf8'));
const manager = createUploadManager('primary', {elementPrefix: 'fixture'});
const result = {status: 'success', validation_status: 'unverified', filename: 'fixture.json', message: 'UNTRANSLATED-RAW'};
manager.renderUploadResult({uploaded_count: 1, message: 'UNTRANSLATED-TOP', results: [result]});
assert.equal(elements.get('fixtureUploadResultText').textContent, 'localized:provider.ownership.import_unverified');
assert.equal(elements.get('fixtureUploadResultDetails').children[0].children[1].textContent, 'localized:provider.ownership.import_unverified');
assert.equal(elements.get('fixtureUploadResultText').attributes['data-i18n'], 'provider.ownership.import_unverified');
assert.equal(elements.get('fixtureUploadResultDetails').children[0].children[1].attributes['data-i18n'], 'provider.ownership.import_unverified');
const html = buildPoolImportResultHtml({uploaded_count: 1, total_count: 1, results: [result]});
assert(html.includes('localized:provider.ownership.import_unverified'));
assert(!html.includes('UNTRANSLATED-RAW'));
assert(html.includes('data-i18n="import.archive_intro"'));
manager.renderUploadResult({results: [{status: 'skipped', validation_status: 'unverified', message: 'skipped'}]});
assert.equal(elements.get('fixtureUploadResultDetails').children[0].children[1].textContent, 'skipped');
assert.equal(elements.get('fixtureUploadResultText').attributes['data-i18n'], undefined);
const mapping = fs.readFileSync(path.join(root, 'frontend/js/core/credential-manager.js'), 'utf8');
assert(mapping.includes("validation_status: item.validation_status === 'unverified'"));
console.log('Unverified import console contract passed');
