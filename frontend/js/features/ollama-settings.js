async function addOllamaCredential(event) {
    event?.preventDefault();
    const endpointField = document.getElementById('ollamaBaseUrl');
    const apiKeyField = document.getElementById('ollamaApiKey');
    const button = document.getElementById('addOllamaBtn');
    const baseUrl = endpointField?.value.trim() || '';
    const apiKey = apiKeyField?.value.trim() || '';

    if (!validateProviderFormScope('ollama.credential')) return;

    button.disabled = true;
    button.textContent = t('runtime.connecting');
    document.getElementById('ollamaSaveResult')?.classList.add('hidden');

    try {
        const response = await fetch('./api/providers/ollama/credentials', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ base_url: baseUrl, api_key: apiKey })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw createProviderRequestError(response, data);

        const title = document.getElementById('ollamaSaveResultTitle');
        const text = document.getElementById('ollamaSaveResultText');
        if (title) {
            title.textContent = t(data.credential_action === 'updated'
                ? 'runtime.credential_updated_title'
                : 'runtime.credential_added_title');
        }
        if (text) {
            const count = Number(data.model_count) || 0;
            text.textContent = `${data.message} ${t('runtime.models_available', {count: formatConsoleNumber(count)})}`;
        }
        document.getElementById('ollamaSaveResult')?.classList.remove('hidden');
        resetProviderTransientSecrets('ollama.credential');
        showStatus(data.message, 'success');
        await AppState.primaryCreds.refresh();
        await loadModelCatalog(true);
        await refreshUsageStats();
    } catch (error) {
        showStatus(t('provider.connection_add_failed', {
            provider: 'Ollama', error: formatProviderRequestError(error)
        }), 'error');
    } finally {
        button.disabled = false;
        button.textContent = t('runtime.validate_add');
    }
}

function handleOllamaFileSelect(event) {
    AppState.ollamaUploadFiles.handleFileSelect(event);
}

function handleOllamaFileDrop(event) {
    event.preventDefault();
    event.currentTarget.classList.remove('dragover');
    AppState.ollamaUploadFiles.addFiles(Array.from(event.dataTransfer.files));
}

function clearOllamaFiles() {
    AppState.ollamaUploadFiles.clearFiles();
}

function uploadOllamaFiles() {
    AppState.ollamaUploadFiles.upload();
}
