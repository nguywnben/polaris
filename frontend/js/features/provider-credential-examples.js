// Illustrative files only: never read form values, account state or saved secrets.
function providerCredentialExample(provider) {
    if (provider === 'google_antigravity') return {
        provider, credential_type: 'oauth', client_id: '<YOUR_CLIENT_ID>',
        client_secret: '<YOUR_CLIENT_SECRET>', refresh_token: '<YOUR_REFRESH_TOKEN>',
        token_uri: 'https://oauth2.googleapis.com/token'
    };
    if (['codex', 'grok', 'claude_code'].includes(provider)) {
        const example = {provider, credential_type: 'oauth', access_token: '<YOUR_ACCESS_TOKEN>', refresh_token: '<YOUR_REFRESH_TOKEN>'};
        if (provider === 'codex') example.account_id = '<YOUR_ACCOUNT_ID>';
        return example;
    }
    if (provider === 'ollama') return {provider, credential_type: 'connection', base_url: 'http://localhost:11434'};
    if (provider === 'kiro') return {
        provider, credential_type: 'oauth', auth_method: 'social',
        refresh_token: '<YOUR_REFRESH_TOKEN>', region: 'us-east-1'
    };
    if (!['google_ai_studio', 'xai_console', 'openai_platform', 'claude_platform'].includes(provider)
        && !Object.hasOwn(EXTENDED_PROVIDER_UI, provider)) throw new Error('unsupported-example-provider');
    const example = {provider, credential_type: 'api_key', api_key: '<YOUR_API_KEY>'};
    if (provider === 'cloudflare') example.account_id = '<YOUR_CLOUDFLARE_ACCOUNT_ID>';
    if (provider === 'opencode') example.plan = 'zen';
    return example;
}

function addProviderCredentialExample(panel, provider) {
    if (!panel || panel.querySelector('[data-provider-example]')) return;
    const title = panel.querySelector(':scope > .card-title');
    if (!title) return;
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'btn btn-secondary btn-small';
    button.dataset.i18n = 'provider.ext.template'; button.textContent = t('provider.ext.template');
    button.dataset.providerExample = provider;
    button.addEventListener('click', () => {
        const example = providerCredentialExample(provider);
        const url = URL.createObjectURL(new Blob([JSON.stringify(example, null, 2)], {type: 'application/json'}));
        const link = document.createElement('a'); link.href = url; link.download = `${provider}-example.json`;
        link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    const header = document.createElement('div'); header.className = 'provider-import-heading';
    header.append(title, button); panel.prepend(header);
}
