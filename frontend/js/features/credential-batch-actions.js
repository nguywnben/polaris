function formatBatchVerificationResult(result) {

    if (!result.success) return `${result.filename}: ${result.error || t('verification_failed')}`;

    const details = [];

    if (result.projectId) details.push(`Project ID ${result.projectId}`);

    if (Number.isFinite(Number(result.modelCount))) {

        const modelCount = Number(result.modelCount);

        details.push(`${modelCount} available model${modelCount === 1 ? '' : 's'}`);

    }

    if (result.creditAmount !== undefined && result.creditAmount !== null) {

        details.push(`${t('credits_label')}: ${result.creditAmount}`);

    }

    if (details.length === 0) details.push(result.message || t('credentials.verified'));

    return `${result.filename}: ${details.join(', ')}`;

}

async function batchVerifyCredentials() {

    const selectedFiles = Array.from(AppState.creds.selectedFiles);

    if (selectedFiles.length === 0) {

        showStatus(t('please_select_the_credentials_to_ve'), 'error');

        showMessageModal(t('tip'), t('please_select_the_credentials_to_ve_dup'), 'error');

        return;

    }

    if (!(await showConfirmModal(

        t('are_you_sure_you_want_to_batch_veri_dup', {
            credentials: formatCountLabel(selectedFiles.length, 'credential')
        }),

        {title: t('confirm_verify_credentials_title'), confirmLabel: t('btn_verify_credentials')}

    ))) {

        return;

    }

    showStatus(t('parallel_verifying_selectedfileslen', {
        credentials: formatCountLabel(selectedFiles.length, 'credential')
    }), 'info');

    const promises = selectedFiles.map(async (filename) => {

        try {

            const response = await fetch(`./api/credentials/verify/${encodeURIComponent(filename)}`, {

                method: 'POST',

                headers: getAuthHeaders()

            });

            const data = await response.json();

            if (response.ok && data.success) {

                return {

                    success: true,

                    filename,

                    projectId: data.project_id,

                    creditAmount: data.credit_amount,

                    modelCount: data.model_count,

                    message: data.message

                };

            } else {

                return { success: false, filename, error: data.message || t('failed') };

            }

        } catch (error) {

            return { success: false, filename, error: error.message };

        }

    });

    const results = await Promise.all(promises);

    let successCount = 0;

    let failCount = 0;

    const resultMessages = [];

    results.forEach(result => {

        if (result.success) {

            successCount++;

            resultMessages.push(formatBatchVerificationResult(result));

        } else {

            failCount++;

            resultMessages.push(formatBatchVerificationResult(result));

        }

    });

    await AppState.creds.refresh();

    const summary = t('batch_verification_completennsucces', {successCount: successCount, failCount: failCount, selectedFiles_length: selectedFiles.length, resultMessages_join___n: resultMessages.join('\n')});

    if (failCount === 0) {

        showStatus(t('all_verifications_successful_succes', {
            credentials: `${successCount}/${selectedFiles.length} ${t('credential')}`
        }), 'success');

        showMessageModal(t('batch_verification_title'), summary, 'success');

    } else if (successCount === 0) {

        showStatus(t('all_verifications_failed_failed_fai', {
            credentials: `${selectedFiles.length} ${t('credential')}`
        }), 'error');

        showMessageModal(t('batch_verification_title'), summary, 'error');

    } else {

        showStatus(t('batch_verification_completed_succes', {successCount: successCount, selectedFiles_length: selectedFiles.length, failCount: failCount}), 'info');

        showMessageModal(t('batch_verification_title'), summary, 'info');

    }

}

async function batchVerifyProviderCredentials() {

    const selectedFiles = Array.from(AppState.primaryCreds.selectedFiles);

    if (selectedFiles.length === 0) {

        showStatus(t('please_select_the_primary_crede_dup'), 'error');

        showMessageModal(t('tip'), t('please_select_the_primary_crede'), 'error');

        return;

    }

    if (!(await showConfirmModal(

        t('are_you_sure_you_want_to_batch_veri', {
            credentials: `${selectedFiles.length} ${t('provider')} ${t('credential')}`
        }),

        {title: t('confirm_verify_credentials_title'), confirmLabel: t('btn_verify_credentials')}

    ))) {

        return;

    }

    showStatus(t('parallel_testing_selectedfileslengt', {
        credentials: `${selectedFiles.length} ${t('provider')} ${t('credential')}`
    }), 'info');

    const promises = selectedFiles.map(async (filename) => {

        try {

            const response = await fetch(`./api/credentials/verify/${encodeURIComponent(filename)}?mode=provider`, {

                method: 'POST',

                headers: getAuthHeaders()

            });

            const data = await response.json();

            if (response.ok && data.success) {

                return {

                    success: true,

                    filename,

                    projectId: data.project_id,

                    creditAmount: data.credit_amount,

                    modelCount: data.model_count,

                    message: data.message

                };

            } else {

                return { success: false, filename, error: data.message || t('failed') };

            }

        } catch (error) {

            return { success: false, filename, error: error.message };

        }

    });

    const results = await Promise.all(promises);

    let successCount = 0;

    let failCount = 0;

    const resultMessages = [];

    results.forEach(result => {

        if (result.success) {

            successCount++;

            resultMessages.push(formatBatchVerificationResult(result));

        } else {

            failCount++;

            resultMessages.push(formatBatchVerificationResult(result));

        }

    });

    await AppState.primaryCreds.refresh();

    const summary = t('primary_batch_verification_comp_dup', {successCount: successCount, failCount: failCount, selectedFiles_length: selectedFiles.length, resultMessages_join___n: resultMessages.join('\n')});

    if (failCount === 0) {

        showStatus(t('all_verifications_successful_verifi', {
            credentials: `${successCount}/${selectedFiles.length} ${t('provider')} ${t('credential')}`
        }), 'success');

        showMessageModal(t('provider_batch_verification_title'), summary, 'success');

    } else if (successCount === 0) {

        showStatus(t('verification_failed_for_all_failed', {
            credentials: `${selectedFiles.length} ${t('provider')} ${t('credential')}`
        }), 'error');

        showMessageModal(t('provider_batch_verification_title'), summary, 'error');

    } else {

        showStatus(t('batch_verification_completed_succes', {successCount: successCount, selectedFiles_length: selectedFiles.length, failCount: failCount}), 'info');

        showMessageModal(t('provider_batch_verification_title'), summary, 'info');

    }

}

async function batchConfigurePreview() {

    const selectedFiles = Array.from(AppState.creds.selectedFiles);

    if (selectedFiles.length === 0) {

        showStatus(t('please_select_the_credential_to_con'), 'error');

        showMessageModal(t('tip'), t('please_select_the_credentials_to_co'), 'error');

        return;

    }

    if (!(await showConfirmModal(

        t('are_you_sure_you_want_to_batch_set', {
            credentials: formatCountLabel(selectedFiles.length, 'credential')
        }),

        {title: t('confirm_configure_preview_title'), confirmLabel: t('btn_configure')}

    ))) {

        return;

    }

    showStatus(t('configuring_preview_channel_for_sel', {
        credentials: formatCountLabel(selectedFiles.length, 'credential')
    }), 'info');

    const promises = selectedFiles.map(async (filename) => {

        try {

            const response = await fetch(`./api/credentials/configure-preview/${encodeURIComponent(filename)}`, {

                method: 'POST',

                headers: getAuthHeaders()

            });

            const data = await response.json();

            if (response.ok && data.success) {

                return {

                    success: true,

                    filename,

                    message: data.message,

                    setting_id: data.setting_id,

                    binding_id: data.binding_id

                };

            } else {

                return {

                    success: false,

                    filename,

                    error: data.message || t('configuration_failed'),

                    step: data.step,

                    errorDetail: data.error

                };

            }

        } catch (error) {

            return { success: false, filename, error: error.message };

        }

    });

    const results = await Promise.all(promises);

    let successCount = 0;

    let failCount = 0;

    const resultMessages = [];

    results.forEach(result => {

        if (result.success) {

            successCount++;

            resultMessages.push(t('resultfilename_resultmessage_config', {result_filename: result.filename, result_message: result.message || t('configuration_successful')}));

        } else {

            failCount++;

            const errorMsg = result.step ? t('resulterror_step_resultstep', {result_error: result.error, result_step: result.step}) : result.error;

            resultMessages.push(` ${result.filename}: ${errorMsg}`);

        }

    });

    await AppState.creds.refresh();

    const summary = t('batch_preview_channel_configuration', {successCount: successCount, failCount: failCount, selectedFiles_length: selectedFiles.length, resultMessages_join___n: resultMessages.join('\n')});

    if (failCount === 0) {

        showStatus(t('all_configured_successfully_preview', {
            successCount: successCount,
            selectedFiles_length: selectedFiles.length,
            credential_noun: t('credential')
        }), 'success');

        showMessageModal(t('bulk_preview_channel_configuration'), summary, 'success');

    } else if (successCount === 0) {

        showStatus(t('configuration_failed_for_all_failed', {
            failCount: failCount,
            selectedFiles_length: selectedFiles.length,
            credential_noun: t('credential')
        }), 'error');

        showMessageModal(t('bulk_preview_channel_configuration'), summary, 'error');

    } else {

        showStatus(t('batch_configuration_complete_succes', {successCount: successCount, selectedFiles_length: selectedFiles.length, failCount: failCount}), 'info');

        showMessageModal(t('bulk_preview_channel_configuration'), summary, 'info');

    }

}

async function refreshAllEmails() {

    if (!(await showConfirmModal(t('are_you_sure_you_want_to_refresh_us'), {

        title: t('confirm_refresh_emails_title'),

        confirmLabel: t('btn_refresh')

    }))) return;

    try {

        showStatus(t('refreshing_all_user_emails'), 'info');

        const response = await fetch('./api/credentials/refresh-all-emails', {

            method: 'POST',

            headers: getAuthHeaders()

        });

        const data = await response.json();

        if (response.ok) {

            showStatus(t('email_refresh_complete_successfully', {
                data_success_count: data.success_count,
                data_total_count: data.total_count,
                address_noun: t('modal.email')
            }), 'success');

            await AppState.creds.refresh();

        } else {

            showStatus(data.message || t('failed_to_refresh_emails'), 'error');

        }

    } catch (error) {

        showStatus(t('email_refresh_network_error_errorme', {error_message: error.message}), 'error');

    }

}

async function deduplicateByEmail() {

    if (!(await showConfirmModal(t('are_you_sure_you_want_to_perform_on'), {

        title: t('confirm_deduplicate_title'),

        confirmLabel: t('btn_deduplicate')

    }))) return;

    try {

        showStatus(t('oneclick_credential_deduplication_i'), 'info');

        const response = await fetch('./api/credentials/deduplicate-by-email', {

            method: 'POST',

            headers: getAuthHeaders()

        });

        const data = await response.json();

        if (response.ok) {

            const msg = t('deduplication_complete_deleted_data', {
                deleted: formatCountLabel(data.deleted_count, 'duplicate credential'),
                kept: formatCountLabel(data.kept_count, 'credential'),
                emails: formatCountLabel(data.unique_emails_count, 'unique email address')
            });

            showStatus(msg, 'success');

            await AppState.creds.refresh();

            if (data.duplicate_groups && data.duplicate_groups.length > 0) {

                let details = t('deduplication_detailsnn');

                data.duplicate_groups.forEach(group => {

                    details += t('email_groupemailnkeep_groupkept_fil', {group_email: group.email, group_kept_file: group.kept_file, group_deleted_files_join: group.deleted_files.join(', ')});

                });

                showMessageModal(t('deduplication_details_title'), details, 'info');

            }

        } else {

            showStatus(data.message || t('deduplication_failed'), 'error');

        }

    } catch (error) {

        showStatus(t('deduplication_network_error_errorme', {error_message: error.message}), 'error');

    }

}

// =====================================================================

// =====================================================================
