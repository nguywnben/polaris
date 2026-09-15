(function initializePolarisTheme() {
    'use strict';

    const STORAGE_KEY = 'polaris_theme';
    const SUPPORTED_PREFERENCES = new Set(['system', 'light', 'dark']);
    const systemThemeQuery = window.matchMedia('(prefers-color-scheme: dark)');
    let transitionFrame = null;

    function normalizePreference(value) {
        return SUPPORTED_PREFERENCES.has(value) ? value : 'system';
    }

    function readPreference() {
        try {
            return normalizePreference(window.localStorage.getItem(STORAGE_KEY));
        } catch (_error) {
            return 'system';
        }
    }

    function resolveTheme(preference) {
        if (preference === 'system') {
            return systemThemeQuery.matches ? 'dark' : 'light';
        }
        return preference;
    }

    function applyTheme(preference) {
        const normalizedPreference = normalizePreference(preference);
        const resolvedTheme = resolveTheme(normalizedPreference);
        const root = document.documentElement;
        if (root.dataset.theme && root.dataset.theme !== resolvedTheme) {
            // Hover/focus transitions must not stagger a whole-page palette change.
            root.classList.add('theme-switching');
            if (transitionFrame !== null) window.cancelAnimationFrame(transitionFrame);
            transitionFrame = window.requestAnimationFrame(() => {
                // Keep the guard for the first paint of the new palette.
                transitionFrame = window.requestAnimationFrame(() => {
                    root.classList.remove('theme-switching');
                    transitionFrame = null;
                });
            });
        }
        document.documentElement.dataset.themePreference = normalizedPreference;
        document.documentElement.dataset.theme = resolvedTheme;
        return { preference: normalizedPreference, resolvedTheme };
    }

    function syncControl(preference) {
        const control = document.getElementById('themePreference');
        if (control && control.value !== preference) {
            control.value = preference;
        }
    }

    function setPreference(preference) {
        const result = applyTheme(preference);
        try {
            window.localStorage.setItem(STORAGE_KEY, result.preference);
        } catch (_error) {
            // Theme selection still applies for this page when browser storage is unavailable.
        }
        syncControl(result.preference);
        document.dispatchEvent(new CustomEvent('polaris:theme-changed', { detail: result }));
        return result;
    }

    function initializeControl() {
        const preference = readPreference();
        syncControl(preference);
        document.getElementById('themePreference')?.addEventListener('change', (event) => {
            setPreference(event.currentTarget.value);
        });
    }

    systemThemeQuery.addEventListener('change', () => {
        if (readPreference() === 'system') {
            const result = applyTheme('system');
            document.dispatchEvent(new CustomEvent('polaris:theme-changed', { detail: result }));
        }
    });

    applyTheme(readPreference());
    window.PolarisTheme = Object.freeze({ readPreference, setPreference });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeControl, { once: true });
    } else {
        initializeControl();
    }
})();
