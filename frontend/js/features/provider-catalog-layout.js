// Measure the whole catalog so pagination and search cannot change card size.
document.addEventListener('DOMContentLoaded', () => {
    const catalog = document.getElementById('providerCatalog');
    if (!catalog) return;
    const properties = ['--provider-card-height', '--provider-card-heading-height', '--provider-card-footer-height'];
    let frame = 0;
    let previousWidth = 0;
    const measure = () => {
        frame = 0;
        properties.forEach(property => catalog.style.removeProperty(property));
        if (!catalog.clientWidth || !window.matchMedia('(min-width: 601px)').matches) return;
        const cards = [...catalog.querySelectorAll('.provider-selector-button')];
        if (!cards.length) return;
        // The temporary class is added and removed synchronously, before paint.
        // Hidden cards keep their selection, tabindex and accessibility state.
        catalog.classList.add('provider-catalog-measuring');
        try {
            const height = (card, selector) => card.querySelector(selector)?.getBoundingClientRect().height || 0;
            const heading = Math.ceil(Math.max(...cards.map(card => Math.max(
                height(card, '.provider-name'), height(card, '.provider-logo-frame')
            ))));
            const description = Math.ceil(Math.max(...cards.map(card => height(card, '.provider-summary p'))));
            const footer = Math.ceil(Math.max(...cards.map(card => height(card, '.provider-capabilities'))));
            const style = getComputedStyle(cards[0]);
            const spacing = ['paddingTop', 'paddingBottom', 'borderTopWidth', 'borderBottomWidth']
                .reduce((sum, key) => sum + parseFloat(style[key]), 0) + 2 * parseFloat(style.rowGap);
            catalog.style.setProperty(properties[0], `${Math.ceil(heading + description + footer + spacing)}px`);
            catalog.style.setProperty(properties[1], `${heading}px`);
            catalog.style.setProperty(properties[2], `${footer}px`);
        } finally {
            catalog.classList.remove('provider-catalog-measuring');
        }
    };
    const schedule = () => {
        if (!frame) frame = requestAnimationFrame(measure);
    };
    new ResizeObserver(entries => {
        const width = entries[0].contentRect.width;
        if (width !== previousWidth) {
            previousWidth = width;
            schedule();
        }
    }).observe(catalog);
    new MutationObserver(schedule).observe(catalog, {childList: true, subtree: true, characterData: true});
    document.fonts.ready.then(schedule);
    schedule();
});
