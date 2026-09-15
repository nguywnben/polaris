// Reuse the provider uploader; files never pass through the add-key form.
function buildExtendedProviderImport(provider) {
    const prefix = `extended-${provider}`;
    const manager = createUploadManager(prefix, {
        elementPrefix: prefix,
        endpoint: `./api/providers/extended/${provider}/credentials/import`,
        preserveFailedFiles: true,
        onBusyChange: busy => {
            panel.setAttribute('aria-busy', String(busy));
            panel.querySelectorAll('button, input').forEach(control => { control.disabled = busy; });
        }
    });
    const panel = extendedElement('section', 'tool-panel provider-import-panel extended-provider-import');
    panel.append(extendedElement('h3', 'card-title', 'providers.import_credentials'),
        extendedElement('p', 'card-copy provider-tool-copy', 'provider.ext.import_description'));
    const fileInput = document.createElement('input');
    fileInput.type = 'file'; fileInput.multiple = true; fileInput.accept = '.json,.zip';
    fileInput.hidden = true; fileInput.id = manager.getElementId('FileInput');
    const drop = extendedElement('button', 'upload-area'); drop.type = 'button';
    const help = extendedElement('p', 'upload-copy', 'provider.copy.supports_files');
    help.id = `${prefix}-upload-help`;
    drop.setAttribute('aria-describedby', help.id);
    const dropContent = document.createElement('div');
    dropContent.append(extendedElement('div', 'upload-title', 'provider.copy.drop_keys'), help);
    drop.append(dropContent);
    drop.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', event => { manager.handleFileSelect(event); fileInput.value = ''; });
    for (const name of ['dragenter', 'dragover', 'dragleave', 'drop']) {
        drop.addEventListener(name, event => {
            event.preventDefault();
            drop.classList.toggle('dragover', name === 'dragenter' || name === 'dragover');
            if (name === 'drop') manager.addFiles([...event.dataTransfer.files]);
        });
    }
    panel.append(drop, fileInput);
    const files = extendedElement('div', 'hidden provider-upload-section');
    files.id = manager.getElementId('FileListSection');
    const list = extendedElement('div', 'file-list'); list.id = manager.getElementId('FileList');
    const actions = extendedElement('div', 'page-actions');
    const upload = extendedElement('button', 'btn btn-small', 'providers.import_credentials'); upload.type = 'button';
    const clear = extendedElement('button', 'btn btn-secondary btn-small', 'clear'); clear.type = 'button';
    upload.addEventListener('click', () => manager.upload());
    clear.addEventListener('click', () => manager.clearFiles());
    actions.append(upload, clear); files.append(list, actions); panel.append(files);
    const progress = extendedElement('div', 'hidden provider-upload-section');
    progress.id = manager.getElementId('UploadProgressSection'); progress.setAttribute('role', 'status');
    const bar = extendedElement('div', 'progress-bar');
    const fill = extendedElement('div', 'progress-fill'); fill.id = manager.getElementId('ProgressFill');
    const text = extendedElement('p', 'page-description provider-progress-copy'); text.id = manager.getElementId('ProgressText');
    bar.append(fill); progress.append(bar, text); panel.append(progress);
    const result = extendedElement('div', 'save-result upload-result hidden provider-upload-section');
    result.id = manager.getElementId('UploadResult');
    const resultCopy = document.createElement('div');
    for (const [tag, suffix, className] of [['strong', 'UploadResultTitle', ''], ['p', 'UploadResultText', ''], ['div', 'UploadResultDetails', 'upload-result-details']]) {
        const item = extendedElement(tag, className); item.id = manager.getElementId(suffix); resultCopy.append(item);
    }
    result.append(resultCopy); panel.append(result);
    const template = extendedElement('button', 'btn btn-secondary btn-small', 'provider.ext.template'); template.type = 'button';
    template.addEventListener('click', () => {
        // Deliberately illustrative: never copy a typed key or credential into the example.
        const example = {provider, api_key: '<YOUR_API_KEY>'};
        if (provider === 'cloudflare') example.account_id = '<YOUR_CLOUDFLARE_ACCOUNT_ID>';
        if (provider === 'opencode') example.plan = 'zen';
        if (provider === 'kiro') example.region = 'us-east-1';
        const url = URL.createObjectURL(new Blob([JSON.stringify(example, null, 2)], {type: 'application/json'}));
        const link = document.createElement('a'); link.href = url; link.download = `${provider}-example.json`;
        link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    const templateActions = extendedElement('div', 'page-actions'); templateActions.append(template); panel.append(templateActions);
    return panel;
}
