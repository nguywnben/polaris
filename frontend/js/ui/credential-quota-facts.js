// Provider display facts only: absent numbers are unknown, never zero/full quota.
function credentialQuotaNumber(value) {
    if (!['number', 'string'].includes(typeof value)
        || (typeof value === 'string' && !value.trim())) return null;
    const number = Number(value);
    return Number.isFinite(number) && number >= 0 ? number : null;
}

function credentialQuotaWindowLabel(window) {
    const duration = credentialQuotaNumber(window.window_duration_mins);
    if (duration > 0) return t('quota.facts.hours', {count: formatConsoleNumber(duration / 60)});
    let label = String(window.label || t('modal.usage_limit'));
    label = label.replace(/(\d+)-Hour Limit/g, (_, count) => t('quota.facts.hours', {count}))
        .replace(/(\d+)-Day(?: Limit| All Models)?/g, (_, count) => t('quota.facts.days', {count}))
        .replace(/Session Limit/g, t('quota.facts.session')).replace(/Weekly Limit/g, t('quota.facts.weekly'));
    if (window.kind === 'trial' || window.kind === 'bonus') label += ` · ${t(`quota.facts.${window.kind}`)}`;
    return label;
}

function renderCredentialQuotaWindow(window) {
    const remaining = credentialQuotaNumber(window.remaining_percentage);
    const percent = remaining === null ? null : Math.min(100, remaining);
    const used = credentialQuotaNumber(window.used_percentage);
    const level = percent === null ? 'muted' : quotaLevelFromUsedPercentage(100 - percent);
    const detail = window.used !== undefined || window.limit !== undefined
        ? t('modal.credits_used', {used: formatQuotaNumber(window.used), limit: formatQuotaNumber(window.limit)})
        : used === null ? t('modal.unavailable') : t('modal.percent_used', {value: formatConsoleNumber(used)});
    const reset = window.reset_time ? t('quota.resets_at', {time: formatQuotaResetTime(window.reset_time)}) : t('quota.reset_unavailable');
    return `<div class="modal-quota-card ${level}">
        <div class="modal-quota-head"><div class="modal-quota-model">${escapeHtml(credentialQuotaWindowLabel(window))}</div>
            <div class="modal-quota-percent">${escapeHtml(percent === null ? t('modal.unavailable') : t('modal.percent_left', {value: formatConsoleNumber(percent)}))}</div></div>
        ${percent === null ? '' : `<div class="modal-quota-bar"><div class="modal-quota-bar-value" style="width: ${percent}%;"></div></div>`}
        <div class="modal-quota-foot"><span>${escapeHtml(detail)}</span><span>${escapeHtml(reset)}</span></div>
        ${window.status ? `<p class="field-hint">${escapeHtml(t('modal.status'))}: ${escapeHtml(window.status)}</p>` : ''}
        ${window.expires_at ? `<p class="field-hint">${escapeHtml(t('quota.facts.expires'))}: ${escapeHtml(formatQuotaResetTime(window.expires_at))}</p>` : ''}
    </div>`;
}

function credentialQuotaFacts(data, context = {}) {
    const facts = [];
    const add = (label, value) => { if (value !== undefined && value !== null && value !== '') facts.push([label, value]); };
    const number = (key, value, money = false) => {
        const amount = credentialQuotaNumber(value);
        if (amount !== null) add(t(key), money ? formatConsoleCurrency(amount / 100) : formatConsoleNumber(amount));
    };
    const state = (key, value) => { if (typeof value === 'boolean') add(t(key), t(value ? 'credential_state_on' : 'credential_state_off')); };
    add(t('modal.plan'), data.plan || context.subscriptionPlan);
    add(t('tier'), data.subscription_tier);
    number('modal.reset_credits', data.reset_credits?.available_count);
    if (typeof data.limit_reached === 'boolean') add(t('modal.standard_limit'), t(data.limit_reached ? 'modal.reached' : 'modal.available'));
    if (typeof data.review_limit_reached === 'boolean') add(t('modal.code_review_limit'), t(data.review_limit_reached ? 'modal.reached' : 'modal.available'));
    state('quota.facts.overage', data.overage_enabled);
    state('quota.facts.unlimited', data.credits?.unlimited);
    state('quota.facts.has_credits', data.credits?.has_credits);
    number('quota.facts.balance', data.credits?.balance);
    state('quota.facts.extra_usage', data.extra_usage?.is_enabled);
    number('quota.facts.extra_used', data.extra_usage?.used_credits, true);
    number('quota.facts.extra_limit', data.extra_usage?.monthly_limit, true);
    number('quota.facts.extra_percent', data.extra_usage?.utilization);
    number('quota.facts.on_demand_used', data.on_demand_used);
    number('quota.facts.on_demand_cap', data.on_demand_cap);
    number('quota.facts.prepaid', data.prepaid_balance);
    if (data.extra_usage?.reset_time) add(t('quota.next_reset'), formatQuotaResetTime(data.extra_usage.reset_time));
    for (const credit of Array.isArray(data.credit_balances) ? data.credit_balances : []) {
        add(`${t('quota.facts.balance')} · ${credit.type}`, formatQuotaNumber(credit.balance));
        if (credentialQuotaNumber(credit.minimum) !== null) add(`${t('quota.facts.minimum')} · ${credit.type}`, formatQuotaNumber(credit.minimum));
    }
    if (data.observed_at) add(t('quota.facts.observed'), formatQuotaResetTime(typeof data.observed_at === 'number' ? data.observed_at * 1000 : data.observed_at));
    return facts;
}

function renderCredentialQuotaFacts(data, context) {
    const facts = credentialQuotaFacts(data, context);
    return facts.length ? `<dl class="credential-management-facts">${facts.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd></div>`).join('')}</dl>` : '';
}
