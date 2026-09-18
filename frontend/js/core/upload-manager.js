function createUploadManager(type, options = {}) {
    options = {preserveFailedFiles: true, ...options};

    const modeParam = type === 'primary' ? 'mode=provider' : 'mode=code_assist';

    const endpoint = options.endpoint || `./api/credentials/upload?${modeParam}`;

    const elementPrefix = options.elementPrefix || (type === 'primary' ? 'primary' : '');

    return {

        type: type,

        selectedFiles: [],
        uploading: false,

        getElementId: (suffix) => {

            if (elementPrefix) {

                return elementPrefix + suffix.charAt(0).toUpperCase() + suffix.slice(1);

            }

            return suffix.charAt(0).toLowerCase() + suffix.slice(1);

        },

        hideUploadResult() {

            const panel = document.getElementById(this.getElementId('UploadResult'));

            if (panel) panel.classList.add('hidden');

        },

        renderUploadResult(data, fallbackVariant = 'success') {

            const panel = document.getElementById(this.getElementId('UploadResult'));
            const title = document.getElementById(this.getElementId('UploadResultTitle'));
            const text = document.getElementById(this.getElementId('UploadResultText'));
            const details = document.getElementById(this.getElementId('UploadResultDetails'));

            if (!panel || !title || !text || !details) return;

            const results = Array.isArray(data.results) ? data.results : [];
            const savedCount = Number(data.uploaded_count || data.loaded_count || 0);
            const skippedCount = Number(data.skipped_count || 0);
            const errorCount = results.filter(item => item.status === 'error').length;
            const hasUnverifiedImport = results.some(item => item.status === 'success' && item.validation_status === 'unverified');

            let variant = 'success';
            if (fallbackVariant === 'error' || (errorCount > 0 && savedCount === 0 && skippedCount === 0)) {
                variant = 'error';
            } else if (skippedCount > 0 && savedCount === 0 && errorCount === 0) {
                variant = 'info';
            } else if (skippedCount > 0 || errorCount > 0 || hasUnverifiedImport) {
                variant = 'warning';
            }

            const titleText = variant === 'error'
                ? t('upload_result_error_title')
                : variant === 'info'
                    ? t('upload_result_skipped_title')
                    : variant === 'warning'
                        ? t('upload_result_mixed_title')
                        : t('upload_result_success_title');

            panel.classList.remove('hidden', 'info', 'warning', 'error');
            if (variant !== 'success') panel.classList.add(variant);

            title.textContent = titleText;
            const savedLabel = t('runtime.credentials_imported', {count: savedCount});
            if (hasUnverifiedImport) text.setAttribute('data-i18n', 'provider.ownership.import_unverified');
            else text.removeAttribute('data-i18n');
            text.textContent = ensureTerminalPunctuation(
                hasUnverifiedImport
                    ? t('provider.ownership.import_unverified')
                    : options.preserveFailedFiles && variant === 'error'
                        ? titleText
                        : data.message || t('status_upload_success', {credentials: savedLabel})
            );
            details.replaceChildren();

            const visibleResults = results.slice(0, 6);
            visibleResults.forEach(item => {
                const detailItem = document.createElement('div');
                detailItem.className = 'upload-result-item';

                const fileLine = document.createElement('div');
                fileLine.className = 'upload-result-file';

                const actionLabel = item.status === 'skipped'
                    ? t('import.action_skipped')
                    : item.status === 'error'
                        ? t('failed')
                        : item.action === 'replaced'
                            ? t('import.action_renewed')
                            : item.action === 'updated'
                                ? t('import.action_updated')
                                : t('import.action_added');
                fileLine.textContent = `${actionLabel}: ${item.filename || item.source_filename || t('credential')}`;

                const messageLine = document.createElement('div');
                messageLine.className = 'upload-result-message';
                if (item.status === 'success' && item.validation_status === 'unverified') {
                    messageLine.setAttribute('data-i18n', 'provider.ownership.import_unverified');
                }
                messageLine.textContent = ensureTerminalPunctuation(
                    item.status === 'success' && item.validation_status === 'unverified'
                        ? t('provider.ownership.import_unverified')
                        : item.message || data.message || ''
                );

                detailItem.append(fileLine, messageLine);
                details.appendChild(detailItem);
            });

            if (results.length > visibleResults.length) {
                const moreItem = document.createElement('div');
                moreItem.className = 'upload-result-message';
                const hiddenCount = results.length - visibleResults.length;
                moreItem.textContent = t('upload.more_results', {count: formatConsoleNumber(hiddenCount)});
                details.appendChild(moreItem);
            }

        },

        handleFileSelect(event) {

            this.addFiles(Array.from(event.target.files));

        },

        addFiles(files) {
            if (this.uploading) return;

            this.hideUploadResult();

            files.forEach(file => {

                const lowerName = file.name.toLowerCase();

                const isValid = file.type === 'application/json' || lowerName.endsWith('.json') ||

                    file.type === 'application/zip' || lowerName.endsWith('.zip');

                if (isValid) {

                    if (!this.selectedFiles.find(f => f.name === file.name && f.size === file.size)) {

                        this.selectedFiles.push(file);

                    }

                } else {

                    showStatus(t('status_invalid_file_format', {name: file.name}), 'error');

                }

            });

            this.updateFileList();

        },

        updateFileList() {

            const list = document.getElementById(this.getElementId('FileList'));

            const section = document.getElementById(this.getElementId('FileListSection'));

            if (!list || !section) {

                console.warn('File list elements not found:', this.getElementId('FileList'));

                return;

            }

            if (this.selectedFiles.length === 0) {

                section.classList.add('hidden');

                return;

            }

            section.classList.remove('hidden');

            list.innerHTML = '';

            this.selectedFiles.forEach((file, index) => {

                const isZip = file.name.toLowerCase().endsWith('.zip');

                const fileIcon = isZip ? '' : '';

                const fileType = isZip ? t('label_zip_pack') : t('label_json_file');

                const fileItem = document.createElement('div');

                fileItem.className = 'file-item';

                const fileDetails = document.createElement('div');
                const fileName = document.createElement('span');
                fileName.className = 'file-name';
                fileName.textContent = `${fileIcon} ${file.name}`.trim();
                const fileSize = document.createElement('span');
                fileSize.className = 'file-size';
                fileSize.textContent = `(${formatFileSize(file.size)} ${fileType})`;
                fileDetails.append(fileName, fileSize);

                const removeButton = document.createElement('button');
                removeButton.type = 'button';
                removeButton.className = 'remove-btn';
                removeButton.textContent = t('action_delete');
                removeButton.addEventListener('click', () => this.removeFile(index));

                fileItem.append(fileDetails, removeButton);

                list.appendChild(fileItem);

            });

        },

        removeFile(index) {
            if (this.uploading) return;

            this.selectedFiles.splice(index, 1);

            this.updateFileList();

        },

        clearFiles(hideResult = true) {
            if (this.uploading && hideResult) return;

            this.selectedFiles = [];

            const fileInput = document.getElementById(this.getElementId('FileInput'));

            if (fileInput) fileInput.value = '';

            this.updateFileList();

            if (hideResult) this.hideUploadResult();

        },

        async upload() {
            if (this.uploading) return;

            if (this.selectedFiles.length === 0) {

                showStatus(t('status_select_upload_first'), 'error');

                return;

            }

            const progressSection = document.getElementById(this.getElementId('UploadProgressSection'));

            const progressFill = document.getElementById(this.getElementId('ProgressFill'));

            const progressText = document.getElementById(this.getElementId('ProgressText'));

            progressSection.classList.remove('hidden');
            progressFill.style.width = '0%';
            progressText.textContent = '0%';
            this.uploading = true;
            options.onBusyChange?.(true);
            const finish = () => {
                this.uploading = false;
                progressSection.classList.add('hidden');
                options.onBusyChange?.(false);
            };

            const formData = new FormData();

            this.selectedFiles.forEach(file => formData.append('files', file));

            if (this.selectedFiles.some(f => f.name.toLowerCase().endsWith('.zip'))) {

                showStatus(t('status_uploading_zip'), 'info');

            }

            try {

                const xhr = new XMLHttpRequest();

                xhr.timeout = options.timeoutMs || 300000;
                xhr.onloadend = finish;

                xhr.upload.onprogress = (event) => {

                    if (event.lengthComputable) {

                        const percent = (event.loaded / event.total) * 100;

                        progressFill.style.width = percent + '%';

                        progressText.textContent = Math.round(percent) + '%';

                    }

                };

                xhr.onload = () => {

                    if (xhr.status >= 200 && xhr.status < 300) {

                        try {

                            const data = JSON.parse(xhr.responseText);

                            const savedCount = Number(data.uploaded_count || 0);
                            const savedLabel = t('runtime.credentials_imported', {count: savedCount});
                            const message = options.preserveFailedFiles
                                ? data.error_count > 0
                                    ? t(data.uploaded_count > 0 ? 'upload_result_mixed_title' : 'upload_result_error_title')
                                    : data.skipped_count > 0 && !data.uploaded_count
                                        ? t('upload_result_skipped_title')
                                        : t('status_upload_success', {credentials: savedLabel})
                                : data.message || t('status_upload_success', {credentials: savedLabel});
                            const uploadStatus = data.uploaded_count > 0
                                ? (data.error_count > 0 ? 'warning' : 'success')
                                : (data.error_count > 0 ? 'error' : 'info');
                            showStatus(message, uploadStatus);
                            this.renderUploadResult(data);

                            if (!options.preserveFailedFiles || !data.error_count) this.clearFiles(false);

                            if (options.onComplete) Promise.resolve(options.onComplete(data));

                            progressSection.classList.add('hidden');

                        } catch (e) {

                            showStatus(t('status_upload_invalid_response'), 'error');

                        }

                    } else {

                        try {

                            const error = JSON.parse(xhr.responseText);
                            const errorMessage = error.detail || error.error || t('unknown_error');

                            showStatus(t('status_upload_failed_details', {error: errorMessage}), 'error');
                            this.renderUploadResult({message: errorMessage, results: []}, 'error');

                        } catch (e) {

                            showStatus(t('status_upload_failed_http', {status: xhr.status}), 'error');
                            this.renderUploadResult({message: t('status_upload_failed_http', {status: xhr.status}), results: []}, 'error');

                        }

                    }

                };

                xhr.onerror = () => {

                    const fileCount = this.selectedFiles.length;
                    const fileLabel = `${fileCount} file${fileCount === 1 ? '' : 's'}`;
                    showStatus(t('status_upload_aborted', {files: fileLabel}), 'error');
                    this.renderUploadResult({message: t('status_upload_aborted', {files: fileLabel}), results: []}, 'error');

                    progressSection.classList.add('hidden');

                };

                xhr.ontimeout = () => {

                    showStatus(t('status_upload_timeout'), 'error');
                    this.renderUploadResult({message: t('status_upload_timeout'), results: []}, 'error');

                    progressSection.classList.add('hidden');

                };

                xhr.open('POST', endpoint);

                xhr.send(formData);

            } catch (error) {
                finish();

                showStatus(t('status_upload_failed_details', {error: error.message}), 'error');
                this.renderUploadResult({message: error.message, results: []}, 'error');

            }

        }

    };

}

// =====================================================================

// Shared frontend utility functions

// =====================================================================
