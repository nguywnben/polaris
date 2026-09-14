// =====================================================================

// =====================================================================

const ROUTE_MAP = {

    '/dashboard': 'dashboard',

    '/ai-quality': 'quality',

    '/access': 'access',

    '/identity': 'identity',

    '/pool': 'pool',

    '/models': 'models',

    '/playground': 'playground',

    '/provider': 'pool',

    '/providers': 'providers',

    '/oauth': 'providers',

    '/upload': 'providers',

    '/config': 'config',

    '/activity': 'activity',

    '/audit': 'audit',

    '/logs': 'logs',

    '/about': 'about'

};

const TAB_MAP = {
    dashboard: '/dashboard',
    quality: '/ai-quality',
    access: '/access',
    identity: '/identity',
    pool: '/pool',
    models: '/models',
    playground: '/playground',
    providers: '/providers',
    config: '/config',
    activity: '/activity',
    audit: '/audit',
    logs: '/logs',
    about: '/about'
};

const TAB_DATA_CACHE_MS = 30000;

function navigate(path, pushState = true) {

    let targetPath = path || '/dashboard';

    if (targetPath === '/' || targetPath === '') {

        targetPath = '/dashboard';

    }

    const setupEl = document.getElementById('setupSection');

    const loginEl = document.getElementById('loginSection');

    const mainEl = document.getElementById('mainSection');

    if (AppState.setupRequired) {

        targetPath = '/setup';

        if (window.location.pathname !== '/setup') {

            history.replaceState(null, '', '/setup');

        }

        if (setupEl) setupEl.style.setProperty('display', 'flex', 'important');

        if (loginEl) loginEl.style.setProperty('display', 'none', 'important');

        if (mainEl) mainEl.style.setProperty('display', 'none', 'important');

        resetConsoleScroll();

        return;

    }

    const isAuthenticated = AppState.authenticated;

    if (!isAuthenticated) {

        targetPath = '/login';

        if (window.location.pathname !== '/login') {

            history.replaceState(null, '', '/login');

        }

        if (setupEl) setupEl.style.setProperty('display', 'none', 'important');

        if (loginEl) loginEl.style.setProperty('display', 'flex', 'important');

        if (mainEl) mainEl.style.setProperty('display', 'none', 'important');

        resetConsoleScroll();

        return;

    } else {

        if (targetPath === '/login') {

            targetPath = '/dashboard';

        }

        if (targetPath === '/setup') {

            targetPath = '/dashboard';

        }

        if (setupEl) setupEl.style.setProperty('display', 'none', 'important');

        if (loginEl) loginEl.style.setProperty('display', 'none', 'important');

        if (mainEl) mainEl.style.setProperty('display', 'flex', 'important');

    }

    const routeTabName = ROUTE_MAP[targetPath] || 'dashboard';
    const tabName = ['audit', 'logs'].includes(routeTabName) ? 'activity' : routeTabName;
    if (typeof updateTeamAccessNavigation === 'function') updateTeamAccessNavigation();
    const compatibilityActivityPath = ['/audit', '/logs'].includes(targetPath);
    const canonicalPath = compatibilityActivityPath ? targetPath : TAB_MAP[tabName] || '/dashboard';

    targetPath = canonicalPath;

    if (window.location.pathname !== targetPath) {

        if (pushState) {

            history.pushState(null, '', targetPath);

        } else {

            history.replaceState(null, '', targetPath);

        }

    }

    setMobileMenuState(false);

    if (tabName === 'activity') {

        setActivityView(activityViewFromLocation(targetPath, window.location.search), {load: false});

    }

    const currentContent = document.querySelector('.tab-content.active');

    const targetContent = document.getElementById(tabName + 'Tab');

    const shouldResetScroll = !currentContent || currentContent !== targetContent;

    if (!shouldResetScroll) {

        void triggerTabDataLoad(tabName);

        return;

    }

    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active');
        tab.removeAttribute('aria-current');
    });

    const targetTabButton = document.querySelector(`.tab[data-tab="${tabName}"]`);

    if (targetTabButton) {

        targetTabButton.classList.add('active');
        targetTabButton.setAttribute('aria-current', 'page');

        const navigationGroup = targetTabButton.closest('details');
        if (navigationGroup) navigationGroup.open = true;

    }

    // Toggle panels instantly

    if (currentContent) {

        currentContent.classList.remove('active');

    }

    if (targetContent) {

        targetContent.classList.add('active');

        void triggerTabDataLoad(tabName);

        if (shouldResetScroll) {

            resetConsoleScroll(targetContent);

            if (pushState) focusActivePage(targetContent);

        }

    }

}

function focusActivePage(activeContent) {
    const heading = activeContent?.querySelector('h1');
    if (!heading) return;
    heading.setAttribute('tabindex', '-1');
    heading.focus({preventScroll: true});
}

function getTabDataLoader(tabName) {

    const loaders = {

        dashboard: () => refreshUsageStats(),

        quality: () => loadQualityPolicy(),

        access: () => loadAccessPage(),

        identity: () => loadIdentityConsole(),

        pool: () => AppState.primaryCreds.refresh(),

        models: () => loadModelCatalog(),

        playground: () => initializePlayground(),

        providers: () => loadProviderOnboarding(),

        config: () => loadConfig(),

        activity: () => loadActivityConsole(),

        audit: () => loadAuditConsole(),

        traces: () => loadTraceConsole(),

        runtime_logs: () => connectWebSocket(),

        about: () => loadAboutPage()

    };

    return loaders[tabName];

}

async function triggerTabDataLoad(tabName, options = {}) {

    const loader = getTabDataLoader(tabName);

    if (!loader) return;

    const force = options.force === true;

    const loadedAt = Number(AppState.tabLoadTimes[tabName] || 0);

    const isFresh = Date.now() - loadedAt < TAB_DATA_CACHE_MS;

    if (!force && isFresh) return;

    if (AppState.tabLoadPromises[tabName]) {

        return AppState.tabLoadPromises[tabName];

    }

    const loadPromise = Promise.resolve()

        .then(loader)

        .then(() => {

            AppState.tabLoadTimes[tabName] = Date.now();

        })

        .finally(() => {

            delete AppState.tabLoadPromises[tabName];

        });

    AppState.tabLoadPromises[tabName] = loadPromise;

    return loadPromise;

}

function resetConsoleScroll(activeContent = null) {

    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });

    document.documentElement.scrollTop = 0;

    document.documentElement.scrollLeft = 0;

    document.body.scrollTop = 0;

    document.body.scrollLeft = 0;

    const scrollTargets = [

        document.getElementById('mainSection'),

        document.querySelector('.dashboard-main'),

        document.querySelector('.dashboard-wrapper'),

        activeContent

    ];

    scrollTargets.forEach(target => {

        if (!target) return;

        target.scrollTop = 0;

        target.scrollLeft = 0;

    });

}
