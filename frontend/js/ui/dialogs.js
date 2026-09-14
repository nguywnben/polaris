function showConfirmModal(message, options = {}) {

    if (!options.title || !options.confirmLabel) {

        throw new Error('Confirmation modals require a contextual title and confirmation label.');

    }

    return new Promise((resolve) => {

        const modal = document.createElement('div');

        modal.className = 'message-modal-overlay';

        const title = options.title;

        const confirmLabel = options.confirmLabel;

        const cancelLabel = options.cancelLabel || t('btn_cancel');

        modal.innerHTML = `

            <div class="message-modal confirm" role="dialog" aria-modal="true" aria-label="${escapeAttribute(title)}">

                <div class="message-modal-header">

                    <h3>${escapeHtml(title)}</h3>

                </div>

                <div class="message-modal-body">

                    ${renderDialogMessage(message, { compact: true })}

                </div>

                <div class="message-modal-footer">

                    <button type="button" class="message-modal-btn" data-dialog-cancel>${escapeHtml(cancelLabel)}</button>

                    <button type="button" class="message-modal-btn message-modal-btn-primary" data-dialog-confirm>${escapeHtml(confirmLabel)}</button>

                </div>

            </div>

        `;

        let settled = false;

        const close = (value) => {

            if (settled) return;

            settled = true;

            document.removeEventListener('keydown', escHandler);

            void unmountModal(modal).then(() => resolve(value));

        };

        const escHandler = (event) => {

            if (event.key === 'Escape') close(false);

        };

        modal.addEventListener('click', (event) => {

            if (event.target === modal || event.target.closest('[data-dialog-cancel]')) close(false);

            if (event.target.closest('[data-dialog-confirm]')) close(true);

        });

        document.addEventListener('keydown', escHandler);

        void mountModal(modal);

        modal.querySelector('[data-dialog-confirm]')?.focus();

    });

}

function showPromptModal(message, options = {}) {

    return new Promise((resolve) => {

        const modal = document.createElement('div');

        modal.className = 'message-modal-overlay';

        const title = options.title || t('input_required_title');

        const confirmLabel = options.confirmLabel || t('btn_continue');

        const cancelLabel = options.cancelLabel || t('btn_cancel');

        const initialValue = options.value || '';

        const placeholder = options.placeholder || '';

        modal.innerHTML = `

            <div class="message-modal prompt" role="dialog" aria-modal="true" aria-label="${escapeAttribute(title)}">

                <div class="message-modal-header">

                    <h3>${escapeHtml(title)}</h3>

                </div>

                <div class="message-modal-body">

                    <div class="message-modal-prompt-copy">${renderDialogMessage(message)}</div>

                    <input type="text" class="message-modal-input">

                </div>

                <div class="message-modal-footer">

                    <button type="button" class="message-modal-btn" data-dialog-cancel>${escapeHtml(cancelLabel)}</button>

                    <button type="button" class="message-modal-btn message-modal-btn-primary" data-dialog-confirm>${escapeHtml(confirmLabel)}</button>

                </div>

            </div>

        `;

        let settled = false;

        const input = () => modal.querySelector('.message-modal-input');

        const close = (value) => {

            if (settled) return;

            settled = true;

            document.removeEventListener('keydown', escHandler);

            void unmountModal(modal).then(() => resolve(value));

        };

        const escHandler = (event) => {

            if (event.key === 'Escape') close(null);

        };

        modal.addEventListener('click', (event) => {

            if (event.target === modal || event.target.closest('[data-dialog-cancel]')) close(null);

            if (event.target.closest('[data-dialog-confirm]')) close(input()?.value || '');

        });

        modal.addEventListener('keydown', (event) => {

            if (event.key === 'Enter' && event.target === input()) close(input()?.value || '');

        });

        document.addEventListener('keydown', escHandler);

        void mountModal(modal);

        const inputEl = input();

        if (inputEl) {

            inputEl.value = initialValue;

            inputEl.placeholder = placeholder;

            inputEl.focus();

        }

    });

}

function showModelTestModal(message, options = {}) {

    return new Promise((resolve) => {

        const modal = document.createElement('div');
        modal.className = 'message-modal-overlay';

        const title = options.title || t('modal.model_test_title');
        const confirmLabel = options.confirmLabel || t('modal.test');
        const cancelLabel = options.cancelLabel || t('btn_cancel');
        const label = options.label || t('modal.model');
        const placeholder = options.placeholder || t('modal.select_model');
        const choices = Array.isArray(options.options) ? options.options : [];
        const optionHtml = choices.map((choice) => `
            <option value="${escapeAttribute(choice.value)}">${escapeHtml(choice.label)}</option>
        `).join('');
        const selectionHtml = `
            <div class="message-modal-prompt-copy">${renderDialogMessage(message)}</div>
            <label class="message-modal-field">
                <span class="message-modal-field-label">${escapeHtml(label)}</span>
                <select class="message-modal-input" data-dialog-select>
                    <option value="" selected disabled>${escapeHtml(placeholder)}</option>
                    ${optionHtml}
                </select>
            </label>
            <div class="model-test-progress hidden" data-model-test-progress role="status" aria-live="polite"></div>
        `;

        modal.innerHTML = `
            <div class="message-modal prompt model-test-modal" role="dialog" aria-modal="true" aria-label="${escapeAttribute(title)}">
                <div class="message-modal-header">
                    <h3>${escapeHtml(title)}</h3>
                </div>
                <div class="message-modal-body"></div>
                <div class="message-modal-footer"></div>
            </div>
        `;

        const dialog = modal.querySelector('.message-modal');
        const body = modal.querySelector('.message-modal-body');
        const footer = modal.querySelector('.message-modal-footer');
        let settled = false;
        let running = false;
        let activeController = null;

        const close = () => {
            if (settled) return;
            settled = true;
            activeController?.abort();
            activeController = null;
            document.removeEventListener('keydown', escHandler);
            void unmountModal(modal).then(() => resolve());
        };

        const renderSelection = () => {
            running = false;
            dialog.className = 'message-modal prompt model-test-modal';
            body.removeAttribute('aria-busy');
            body.removeAttribute('aria-live');
            body.removeAttribute('role');
            body.innerHTML = selectionHtml;
            footer.innerHTML = `
                <button type="button" class="message-modal-btn" data-dialog-cancel>${escapeHtml(cancelLabel)}</button>
                <button type="button" class="message-modal-btn message-modal-btn-primary" data-dialog-confirm disabled>${escapeHtml(confirmLabel)}</button>
            `;

            const select = body.querySelector('[data-dialog-select]');
            const confirm = footer.querySelector('[data-dialog-confirm]');
            select?.addEventListener('change', () => {
                if (confirm) confirm.disabled = !select.value;
            });
            select?.focus();
        };

        const renderResult = (result) => {
            const safeType = String(result?.type || 'info').replace(/[^\w-]/g, '') || 'info';
            running = false;
            activeController = null;
            dialog.className = `message-modal informational model-test-modal ${safeType}`;
            body.removeAttribute('aria-busy');
            body.setAttribute('role', safeType === 'error' ? 'alert' : 'status');
            body.setAttribute('aria-live', safeType === 'error' ? 'assertive' : 'polite');
            body.innerHTML = String(result?.html || '');
            footer.innerHTML = `
                <button type="button" class="message-modal-btn" data-dialog-close>${escapeHtml(t('btn_close'))}</button>
                <button type="button" class="message-modal-btn message-modal-btn-primary" data-dialog-retry>${escapeHtml(t('btn_test_another_model'))}</button>
            `;
            footer.querySelector('[data-dialog-close]')?.focus();
        };

        const runTest = async () => {
            if (running) return;

            const select = body.querySelector('[data-dialog-select]');
            const confirm = footer.querySelector('[data-dialog-confirm]');
            const progress = body.querySelector('[data-model-test-progress]');
            const model = select?.value || '';
            if (!model || typeof options.onTest !== 'function') return;

            running = true;
            const controller = new AbortController();
            activeController = controller;
            body.setAttribute('aria-busy', 'true');
            select.disabled = true;
            if (confirm) {
                confirm.disabled = true;
                confirm.textContent = t('testing_short');
            }
            if (progress) {
                progress.textContent = t('testing_selected_model', {model});
                progress.classList.remove('hidden');
            }

            try {
                const result = await options.onTest(model, activeController.signal);
                if (!settled) renderResult(result);
            } catch (error) {
                if (settled) return;
                if (controller.signal.aborted) {
                    renderResult({
                        type: 'info',
                        html: buildApiResultHtml({
                            intro: t('credential_test_cancelled'),
                            rows: [
                                [t('status'), t('credential_test_cancelled')],
                                [t('modal.model'), model],
                            ],
                            summaryLabel: t('modal.model_test_title'),
                        }),
                    });
                    return;
                }
                const errorMessage = error?.message || t('verification_failed');
                renderResult({
                    type: 'error',
                    html: buildApiResultHtml({
                        intro: t('verification_failed'),
                        rows: [
                            [t('status'), t('failed')],
                            [t('modal.model'), model],
                        ],
                        summaryLabel: t('modal.error_summary'),
                        note: errorMessage,
                    }),
                });
            }
        };

        const escHandler = (event) => {
            if (event.key === 'Escape') close();
        };

        modal.addEventListener('click', (event) => {
            if (event.target === modal || event.target.closest('[data-dialog-cancel], [data-dialog-close]')) {
                close();
                return;
            }
            if (event.target.closest('[data-dialog-retry]')) {
                renderSelection();
                return;
            }
            if (event.target.closest('[data-dialog-confirm]')) runTest();
        });

        document.addEventListener('keydown', escHandler);
        void mountModal(modal);
        renderSelection();

    });

}
