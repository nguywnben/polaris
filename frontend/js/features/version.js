async function fetchAndDisplayVersion() {

    const versionText = document.getElementById('versionText');

    try {

        const response = await fetch('./api/version/info');

        const data = await response.json();

        if (data.success) {

            versionText.textContent = `v${data.version}`;

            versionText.title = t('full_version_datafull_hashncommit_m', {data_full_hash: data.full_hash, data_message: data.message, data_date: data.date});

            versionText.style.cursor = 'help';

        } else {

            versionText.textContent = t('unknown_version');

            versionText.title = data.error || t('unable_to_retrieve_version_informat');

        }

    } catch (error) {

        console.error(t('failed_to_retrieve_version_informat'), error);

        if (versionText) {

            versionText.textContent = t('failed_to_fetch_version_information');

        }

    } finally {

        if (versionText) {

            versionText.classList.remove('skeleton', 'skeleton-inline');

            versionText.setAttribute('aria-busy', 'false');

            versionText.removeAttribute('aria-label');

        }

    }

}

async function checkForUpdates() {

    const checkBtn = document.getElementById('checkUpdateBtn');

    if (!checkBtn) return;

    if (!checkBtn.dataset.defaultText) {

        checkBtn.dataset.defaultText = checkBtn.textContent.trim() || t('check_for_updates');

    }

    const originalText = checkBtn.dataset.defaultText;

    const hadUpdateAvailable = checkBtn.classList.contains('update-available');

    if (checkBtn._resetTimer) {

        clearTimeout(checkBtn._resetTimer);

        checkBtn._resetTimer = null;

    }

    checkBtn.classList.remove('update-available', 'update-current');

    const restoreIdleState = () => {

        if (hadUpdateAvailable) {

            checkBtn.textContent = t('new_version_available');

            checkBtn.classList.add('update-available');

            return;

        }

        checkBtn.textContent = originalText;

    };

    try {

        checkBtn.textContent = t('checking');

        checkBtn.disabled = true;

        const response = await fetch('./api/version/info?check_update=true');

        const data = await response.json();

        if (data.success) {

            if (data.check_update === false) {

                showStatus(t('check_for_updates_failed_dataupdate', {data_update_error: data.update_error || t('unknown_error')}), 'error');

            } else if (data.has_update === true) {

                const updateMsg = t('new_version_foundncurrent_vdatavers', {data_version: data.version, data_latest_version: data.latest_version, data_latest_message: data.latest_message || t('none')});

                showStatus(updateMsg.replace(/\n/g, ' '), 'warning');

                checkBtn.textContent = t('new_version_available');

                checkBtn.classList.add('update-available');

            } else if (data.has_update === false) {

                showStatus(t('already_up_to_date'), 'success');

                checkBtn.textContent = t('already_up_to_date_dup');

                checkBtn.classList.add('update-current');

                checkBtn._resetTimer = setTimeout(() => {

                    checkBtn.classList.remove('update-current');

                    checkBtn.textContent = originalText;

                    checkBtn._resetTimer = null;

                }, 3000);

            } else {

                showStatus(t('unable_to_determine_if_updates_are'), 'info');

            }

        } else {

            showStatus(t('failed_to_check_for_updates_dataerr', {data_error: data.error}), 'error');

        }

    } catch (error) {

        console.error(t('failed_to_check_for_updates'), error);

        showStatus(t('failed_to_check_for_updates_errorme', {error_message: error.message}), 'error');

    } finally {

        checkBtn.disabled = false;

        if (checkBtn.textContent === t('checking')) {

            restoreIdleState();

        }

    }

}

// =====================================================================

// =====================================================================

async function initializeConsole() {

    updatePrimaryCallbackUrlPlaceholder();

    // popstate listener

    window.addEventListener('popstate', () => {

        navigate(window.location.pathname, false);

    });

    const setupRequired = await refreshSetupStatus();

    if (setupRequired) {

        navigate('/setup', false);

        return;

    }

    const autoLoginSuccess = await autoLogin();

    if (autoLoginSuccess) {

        await fetchAndDisplayVersion();

    }

    startCooldownTimer();

    const primaryAuthBtn = document.getElementById('getPrimaryAuthBtn');

    if (primaryAuthBtn) {

        primaryAuthBtn.addEventListener('click', startPrimaryAuth);

    }

}

if (document.readyState === 'loading') {

    document.addEventListener('DOMContentLoaded', initializeConsole, { once: true });

} else {

    void initializeConsole();

}

document.addEventListener('DOMContentLoaded', function () {

    const uploadArea = document.getElementById('uploadArea');

    if (uploadArea) {

        uploadArea.addEventListener('dragover', (event) => {

            event.preventDefault();

            uploadArea.classList.add('dragover');

        });

        uploadArea.addEventListener('dragleave', (event) => {

            event.preventDefault();

            uploadArea.classList.remove('dragover');

        });

        uploadArea.addEventListener('drop', (event) => {

            event.preventDefault();

            uploadArea.classList.remove('dragover');

            AppState.uploadFiles.addFiles(Array.from(event.dataTransfer.files));

        });

    }

});
