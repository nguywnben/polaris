function updateTeamAccessNavigation() {
    const teamAccessTab = document.querySelector('[data-tab="identity"]');
    if (!teamAccessTab) return;
    // Navigation is always available; OIDC activation and API authorization remain separate.
    teamAccessTab.hidden = false;
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
