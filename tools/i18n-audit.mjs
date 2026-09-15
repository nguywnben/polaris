import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const root = path.resolve(import.meta.dirname, '..');
const frontend = path.join(root, 'frontend');

function walk(directory, extension) {
    return fs.readdirSync(directory, {withFileTypes: true}).flatMap((entry) => {
        const target = path.join(directory, entry.name);
        if (entry.isDirectory()) return walk(target, extension);
        return entry.name.endsWith(extension) ? [target] : [];
    });
}

const sources = [
    ...walk(path.join(frontend, 'fragments'), '.html'),
    ...walk(path.join(frontend, 'js'), '.js'),
];
const referenced = new Set();
const referencesByFile = new Map();
const patterns = [
    /\bt\(\s*['"]([^'"]+)['"]/g,
    /data-i18n(?:-(?:title|alt|placeholder|aria-label))?=['"]([^'"]+)['"]/g,
];
for (const file of sources) {
    const source = fs.readFileSync(file, 'utf8');
    const fileReferences = new Set();
    for (const pattern of patterns) {
        for (const match of source.matchAll(pattern)) {
            referenced.add(match[1]);
            fileReferences.add(match[1]);
        }
    }
    for (const match of source.matchAll(/data-provider-form-copy=['"]([^'"]+)['"]/g)) {
        const key = `provider.form.${match[1]}`;
        referenced.add(key);
        fileReferences.add(key);
    }
    if (fileReferences.size) referencesByFile.set(path.relative(root, file), fileReferences);
}

const context = vm.createContext({document: {addEventListener() {}}, console});
const localeSource = fs.readFileSync(path.join(frontend, 'js/core/locales.js'), 'utf8');
const pageLocaleSource = fs.readFileSync(path.join(frontend, 'js/core/page-locales.js'), 'utf8');
const auditLocaleSource = fs.readFileSync(path.join(frontend, 'js/core/audit-locales.js'), 'utf8');
const traceLocaleSource = fs.readFileSync(path.join(frontend, 'js/core/trace-locales.js'), 'utf8');
const operationalLocaleSource = fs.readFileSync(path.join(frontend, 'js/core/operational-locales.js'), 'utf8');
const i18nSource = fs.readFileSync(path.join(frontend, 'js/core/i18n.js'), 'utf8');
const identityLocaleSource = fs.readFileSync(path.join(frontend, 'js/core/identity-locales.js'), 'utf8');
vm.runInContext(`${localeSource}\n${pageLocaleSource}\n${auditLocaleSource}\n${traceLocaleSource}\n${operationalLocaleSource}\n${i18nSource}\n${identityLocaleSource}\nglobalThis.__catalogs = {SUPPORTED_LOCALES, COMMON_UI_TRANSLATIONS, SETTINGS_LOCALE_TRANSLATIONS, AUTH_LOCALE_TRANSLATIONS, DIALOG_LOCALE_TRANSLATIONS, PAGE_LOCALE_TRANSLATIONS, TRANSLATIONS, LEGACY_UI_FALLBACKS, PROVIDER_COPY_FALLBACKS, PROVIDER_LABEL_TRANSLATIONS, PROVIDER_LABEL_KEYS, PRESERVED_TECHNICAL_TRANSLATION_KEYS, resolveLegacyFallback};`, context);

const catalogs = context.__catalogs;
for (const file of ['oidc-entry-locales.js', 'backup-locales.js']) {
    vm.runInContext(fs.readFileSync(path.join(frontend, 'js/core', file), 'utf8'), context);
}
vm.runInContext(fs.readFileSync(path.join(frontend, 'js/core/provider-copy-locales.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(frontend, 'js/core/provider-expansion-locales.js'), 'utf8'), context);
// Load the same late locale overrides as the shipped bundle, including Identity aliases.
const completionDirectory = path.join(frontend, 'js/locales');
if (fs.existsSync(completionDirectory)) {
    for (const file of fs.readdirSync(completionDirectory).filter(name => name.endsWith('.js')).sort()) {
        vm.runInContext(fs.readFileSync(path.join(completionDirectory, file), 'utf8'), context);
    }
}
const completionRegistration = path.join(frontend, 'js/core/locale-completion.js');
if (fs.existsSync(completionRegistration)) {
    vm.runInContext(fs.readFileSync(completionRegistration, 'utf8'), context);
}
const strict = process.argv.includes('--strict');
const runtimeCatalogs = vm.runInContext('MESSAGE_CATALOGS', context);
const exactProviderCopy = vm.runInContext('PROVIDER_EXACT_COPY', context);
const preservedNames = new Set([
    'Google Antigravity', 'Google AI Studio', 'Grok Build', 'SpaceXAI Console',
    'Code Assist', 'OpenAI Platform', 'Claude Code', 'Claude Platform', 'Top P',
]);
const effectiveCatalog = locale => ({
    ...(catalogs.TRANSLATIONS[locale] || {}),
    ...(runtimeCatalogs[locale] || {}),
});
const english = effectiveCatalog('en');
const variables = text => JSON.stringify([...text.matchAll(/\{([\w]+)\}/g)].map(match => match[1]).sort());
const verbose = process.argv.includes('--verbose');
if (process.argv.includes('--by-file')) {
    for (const [file, keys] of [...referencesByFile.entries()].sort()) {
        console.log(`${file}: ${keys.size}`);
    }
}
let hasMissing = false;
if (strict) {
    const providerHtml = fs.readFileSync(path.join(frontend, 'fragments/pages/providers.html'), 'utf8');
    for (const [, attributes, text] of providerHtml.matchAll(/<p\b([^>]*)>([^<]+)<\/p>/g)) {
        if (/data-i18n|data-provider-form-copy/.test(attributes)) continue;
        const source = text.trim();
        if (source.split(/\s+/).length < 5) continue;
        const exact = vm.runInContext(`translateEnglishSource(${JSON.stringify(source)}, 'en')`, context);
        if (!exact) {
            hasMissing = true;
            console.error(`Provider instructions lack an exact translation key: ${source}`);
        }
    }
}
const fallbackCategories = ['complete', 'failed', 'progress', 'confirm', 'unavailable', 'required', 'notice'];
const providerFallbackCategories = ['configure', 'import', 'instruction', 'files', 'drop', 'loading', 'unavailable'];
for (const locale of Object.keys(catalogs.SUPPORTED_LOCALES)) {
    const available = effectiveCatalog(locale);
    if (strict) {
        const unresolvedProviderCopy = [];
        for (const [suffix, [source]] of Object.entries(exactProviderCopy)) {
            const key = `provider.copy.${suffix}`;
            const actual = vm.runInContext(`translateProviderCopy(${JSON.stringify(source)}, ${JSON.stringify(locale)})`, context);
            if (actual !== available[key]) {
                hasMissing = true;
                unresolvedProviderCopy.push(key);
            }
        }
        if (unresolvedProviderCopy.length) console.error(`${locale}: ${unresolvedProviderCopy.length} provider instructions do not resolve exactly: ${unresolvedProviderCopy.slice(0, 6).join(', ')}`);
        const incomplete = Object.keys(english).filter(key => typeof available[key] !== 'string' || !available[key].trim());
        const mismatches = Object.keys(english).filter(key => available[key] && variables(english[key]) !== variables(available[key]));
        const englishCopies = locale === 'en' ? [] : Object.keys(english).filter(key =>
            available[key] === english[key] && /[a-z]{3} [a-z]{3}/i.test(english[key])
            && !preservedNames.has(english[key])
            && !catalogs.PRESERVED_TECHNICAL_TRANSLATION_KEYS.has(key)
        );
        for (const [kind, keys] of [['incomplete', incomplete], ['variable mismatch', mismatches], ['English fallback', englishCopies]]) {
            if (!keys.length) continue;
            hasMissing = true;
            console.error(`${locale}: ${keys.length} ${kind}: ${keys.slice(0, 12).join(', ')}`);
        }
    }
    const fallbackMessages = catalogs.LEGACY_UI_FALLBACKS[locale] || {};
    const invalidFallbacks = fallbackCategories.filter((category) => (
        typeof fallbackMessages[category] !== 'string' || fallbackMessages[category].trim().length === 0
    ));
    if (invalidFallbacks.length) {
        hasMissing = true;
        console.error(`${locale}: invalid legacy fallback categories: ${invalidFallbacks.join(', ')}`);
    }
    const providerFallbacks = catalogs.PROVIDER_COPY_FALLBACKS[locale] || {};
    const invalidProviderFallbacks = providerFallbackCategories.filter((category) => (
        typeof providerFallbacks[category] !== 'string' || providerFallbacks[category].trim().length === 0
    ));
    const providerLabels = catalogs.PROVIDER_LABEL_TRANSLATIONS[locale] || {};
    const invalidProviderLabels = catalogs.PROVIDER_LABEL_KEYS.filter((label) => (
        typeof providerLabels[label] !== 'string' || providerLabels[label].trim().length === 0
    ));
    if (invalidProviderFallbacks.length || invalidProviderLabels.length) {
        hasMissing = true;
        console.error(`${locale}: incomplete provider localization fallback catalog`);
    }

    const missing = [...referenced].filter((key) => {
        if (typeof available[key] === 'string' && available[key].trim().length > 0) return false;
        const source = catalogs.TRANSLATIONS.en?.[key];
        if (typeof source !== 'string' || source.trim().length === 0) return true;
        if (catalogs.PRESERVED_TECHNICAL_TRANSLATION_KEYS.has(key)) return false;
        const fallback = catalogs.resolveLegacyFallback(key, source, locale);
        return typeof fallback !== 'string' || fallback.trim().length === 0 || (locale !== 'en' && fallback === source);
    }).sort();
    if (missing.length) {
        hasMissing = true;
        console.error(`${locale}: ${missing.length} missing key(s)`);
        if (verbose) console.error(missing.join('\n'));
        else console.error(`${missing.slice(0, 12).join(', ')}${missing.length > 12 ? ', ...' : ''}`);
    }
}

if (hasMissing) process.exitCode = 1;
else console.log(`All ${referenced.size} referenced keys are translated for every locale.`);
