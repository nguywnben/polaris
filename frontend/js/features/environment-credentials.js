async function checkEnvCredsStatus() {

    const loading = document.getElementById('envStatusLoading');

    const content = document.getElementById('envStatusContent');

    try {

        loading.style.display = 'block';

        content.classList.add('hidden');

        const response = await fetch('./api/auth/env-creds-status', { headers: getAuthHeaders() });

        const data = await response.json();

        if (response.ok) {

            const envVarsList = document.getElementById('envVarsList');

            envVarsList.textContent = Object.keys(data.available_env_vars).length > 0

                ? Object.keys(data.available_env_vars).join(', ')

                : t('code_assist_creds__environment_variable_no');

            const autoLoadStatus = document.getElementById('autoLoadStatus');

            autoLoadStatus.textContent = data.auto_load_enabled ? t('enabled') : t('not_enabled');

            autoLoadStatus.style.color = data.auto_load_enabled ? '#28a745' : '#dc3545';

            document.getElementById('envFilesCount').textContent = t(
                'dataexisting_env_files_count_files',
                {files: formatCountLabel(data.existing_env_files_count, 'file')}
            );

            const envFilesList = document.getElementById('envFilesList');

            envFilesList.textContent = data.existing_env_files.length > 0

                ? data.existing_env_files.join(', ')

                : t('none');

            content.classList.remove('hidden');

            // showStatus(t('environment_variable_status_check_c'), 'success');

        } else {

            showStatus(t('failed_to_retrieve_environment_vari', {data_detail____data_error: data.detail || data.error || t('unknown_error')}), 'error');

        }

    } catch (error) {

        showStatus(t('status_net_error', {error: error.message}), 'error');

    } finally {

        loading.style.display = 'none';

    }

}

async function loadEnvCredentials() {

    try {

        showStatus(t('importing_credentials_from_environm'), 'info');

        const response = await fetch('./api/auth/load-env-creds', {

            method: 'POST',

            headers: getAuthHeaders()

        });

        const data = await response.json();

        if (response.ok) {

            if (data.loaded_count > 0) {

                showStatus(t('successfully_imported_dataloaded_co', {
                    data_loaded_count: data.loaded_count,
                    data_total_count: data.total_count,
                    credential_noun: t('credential')
                }), 'success');

                setTimeout(() => checkEnvCredsStatus(), 1000);

            } else {

                showStatus(data.message, 'info');

            }

        } else {

            showStatus(t('import_failed_datadetail_dataerror', {data_detail____data_error: data.detail || data.error || t('unknown_error')}), 'error');

        }

    } catch (error) {

        showStatus(t('status_net_error', {error: error.message}), 'error');

    }

}

async function clearEnvCredentials() {

    if (!(await showConfirmModal(t('are_you_sure_you_want_to_clear_all'), {

        title: t('confirm_clear_imported_credentials_title'),

        confirmLabel: t('btn_clear_credentials')

    }))) {

        return;

    }

    try {

        showStatus(t('clearing_environment_variable_crede'), 'info');

        const response = await fetch('./api/auth/env-creds', {

            method: 'DELETE',

            headers: getAuthHeaders()

        });

        const data = await response.json();

        if (response.ok) {

            showStatus(t('successfully_deleted_datadeleted_co', {
                files: formatCountLabel(data.deleted_count, 'environment-variable credential file')
            }), 'success');

            setTimeout(() => checkEnvCredsStatus(), 1000);

        } else {

            showStatus(t('clear_failed_datadetail_dataerror_u', {data_detail____data_error: data.detail || data.error || t('unknown_error')}), 'error');

        }

    } catch (error) {

        showStatus(t('status_net_error', {error: error.message}), 'error');

    }

}

// =====================================================================

// =====================================================================
