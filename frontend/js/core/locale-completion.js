// Apply curated page translations after legacy defaults and Identity aliases.
// t() reads MESSAGE_CATALOGS first, so updating only the source maps is insufficient.
applyProviderAuthCopy();
for (const locale of Object.keys(SUPPORTED_LOCALES)) {
    Object.assign(MESSAGE_CATALOGS[locale], PAGE_LOCALE_TRANSLATIONS[locale] || {});
}
for (const [key, message] of Object.entries(MESSAGE_CATALOGS.en)) {
    if (!ENGLISH_SEMANTIC_KEYS_BY_MESSAGE.has(message)) {
        ENGLISH_SEMANTIC_KEYS_BY_MESSAGE.set(message, key);
    }
}
