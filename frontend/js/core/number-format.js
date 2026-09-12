// Locale-aware number presentation for the management console.

const CONSOLE_COMPACT_NUMBER_THRESHOLD = 10_000;

function getConsoleNumberLocale() {
    return typeof getActiveLocale === 'function' ? getActiveLocale() : 'en-US';
}

function consoleFiniteNumber(value, {minimum = Number.NEGATIVE_INFINITY} = {}) {
    const number = Number(value ?? 0);
    return Number.isFinite(number) && number >= minimum ? number : 0;
}

function formatConsoleNumber(value, options = {}) {
    const number = consoleFiniteNumber(value);
    const decimals = options.decimals;
    const compact = Boolean(options.compact)
        && Math.abs(number) >= (options.compactThreshold ?? CONSOLE_COMPACT_NUMBER_THRESHOLD);
    return new Intl.NumberFormat(getConsoleNumberLocale(), {
        ...(compact ? {notation: 'compact', compactDisplay: 'short'} : {}),
        minimumFractionDigits: options.minimumFractionDigits ?? decimals ?? 0,
        maximumFractionDigits: options.maximumFractionDigits ?? decimals ?? (compact ? 2 : 3),
    }).format(number);
}

function formatConsoleCurrency(value, options = {}) {
    const amount = consoleFiniteNumber(value, {minimum: 0});
    const compact = Boolean(options.compact)
        && amount >= (options.compactThreshold ?? CONSOLE_COMPACT_NUMBER_THRESHOLD);
    const smallAmount = amount > 0 && amount < 0.01;
    return new Intl.NumberFormat(getConsoleNumberLocale(), {
        style: 'currency',
        currency: options.currency || 'USD',
        ...(compact ? {notation: 'compact', compactDisplay: 'short'} : {}),
        minimumFractionDigits: options.minimumFractionDigits ?? (compact ? 0 : (smallAmount ? 2 : 2)),
        maximumFractionDigits: options.maximumFractionDigits ?? (compact ? 2 : (smallAmount ? 4 : 2)),
    }).format(amount);
}

function getCompactMetricPresentation(value, options = {}) {
    const formatter = options.currency ? formatConsoleCurrency : formatConsoleNumber;
    const display = formatter(value, {...options, compact: true});
    const exact = formatter(value, {...options, compact: false});
    return {display, exact, compacted: display !== exact};
}

function setCompactMetricValue(element, value, options = {}) {
    if (!element) return;
    const {display, exact, compacted} = getCompactMetricPresentation(value, options);
    element.textContent = display;
    if (compacted) {
        element.title = exact;
        element.setAttribute('aria-label', exact);
        return;
    }
    element.title = '';
    element.removeAttribute('aria-label');
}
