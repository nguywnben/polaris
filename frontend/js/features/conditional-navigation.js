function updateTeamAccessNavigation() {
    const teamAccessTab = document.querySelector('[data-conditional-navigation="team-access"]');
    if (!teamAccessTab) return;
    const configuringTeamAccess = window.location.pathname === '/identity';
    teamAccessTab.hidden = AppState.teamAccessEnabled !== true && !configuringTeamAccess;
}

function resetConditionalNavigation() {
    AppState.teamAccessEnabled = null;
    updateTeamAccessNavigation();
}

async function refreshTeamAccessNavigation() {
    if (!AppState.authenticated) {
        resetConditionalNavigation();
        return;
    }
    try {
        const payload = await identityApi('/oidc-policy');
        const policy = identityValidateOidcPolicy(payload);
        AppState.teamAccessEnabled = policy?.enabled === true;
    } catch (_) {
        AppState.teamAccessEnabled = null;
    }
    updateTeamAccessNavigation();
}
