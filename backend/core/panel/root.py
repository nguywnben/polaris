"""Root routes for the management console."""

import hashlib
import re
from functools import lru_cache
from html import escape

from core.anthropic import is_claude_oauth_state
from core.auth import accept_oauth_callback
from core.i18n import get_locale, translate
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from log import log
from paths import FRONTEND_DIR

router = APIRouter(tags=["root"])

CONSOLE_FRAGMENT_PATHS = (
    "auth/login.html",
    "auth/setup.html",
    "layout/sidebar.html",
    "layout/mobile-header.html",
    "pages/dashboard.html",
    "pages/ai-quality.html",
    "pages/access.html",
    "pages/identity.html",
    "pages/credentials.html",
    "pages/models.html",
    "pages/playground.html",
    "pages/providers.html",
    "pages/settings.html",
    "pages/activity.html",
    "pages/audit.html",
    "pages/logs.html",
    "pages/about.html",
    "layout/footer.html",
)

CONSOLE_STYLE_ASSETS = (
    "css/foundation.css",
    "css/shell.css",
    "css/providers-and-models.css",
    "css/forms-and-data.css",
    "css/quality-policy.css",
    "css/playground.css",
    "css/access.css",
    "css/backups.css",
    "css/identity.css",
    "css/audit.css",
    "css/observability.css",
    "css/components.css",
    "css/dialogs.css",
    "css/credential-management.css",
    "css/responsive.css",
    "css/oauth-callback.css",
)

CONSOLE_EARLY_SCRIPT_ASSETS = ("js/core/theme.js",)

CONSOLE_SCRIPT_ASSETS = (
    "js/core/locales.js",
    "js/core/page-locales.js",
    "js/core/audit-locales.js",
    "js/core/trace-locales.js",
    "js/core/operational-locales.js",
    "js/core/provider-copy-locales.js",
    "js/core/provider-expansion-locales.js",
    "js/core/provider-auth-locales.js",
    "js/core/number-format.js",
    "js/core/i18n.js",
    "js/core/identity-locales.js",
    "js/core/oidc-entry-locales.js",
    "js/core/backup-locales.js",
    "js/locales/de.js",
    "js/locales/es.js",
    "js/locales/fr.js",
    "js/locales/id.js",
    "js/locales/it.js",
    "js/locales/ja.js",
    "js/locales/ko.js",
    "js/locales/pt.js",
    "js/locales/ru.js",
    "js/locales/th.js",
    "js/locales/tr.js",
    "js/locales/zh-CN.js",
    "js/locales/zh-TW.js",
    "js/core/locale-completion.js",
    "js/core/identity-contract.js",
    "js/core/navigation.js",
    "js/core/credential-manager.js",
    "js/core/upload-manager.js",
    "js/core/state.js",
    "js/ui/notifications.js",
    "js/ui/page-states.js",
    "js/ui/api-integration.js",
    "js/ui/dialog-content.js",
    "js/ui/dialogs.js",
    "js/ui/credential-dialogs.js",
    "js/ui/credential-management.js",
    "js/ui/credential-management-actions.js",
    "js/ui/credential-cards.js",
    "js/features/authentication.js",
    "js/features/usage-pagination.js",
    "js/features/virtual-keys.js",
    "js/features/identity.js",
    "js/features/conditional-navigation.js",
    "js/features/audit.js",
    "js/features/traces.js",
    "js/features/activity.js",
    "js/features/provider-credential-examples.js",
    "js/features/provider-save-results.js",
    "js/features/extended-provider-import.js",
    "js/features/kiro-authentication.js",
    "js/features/kiro-browser-login.js",
    "js/features/muse-authentication.js",
    "js/features/extended-providers.js",
    "js/features/provider-catalog-layout.js",
    "js/features/navigation.js",
    "js/features/model-pool.js",
    "js/features/playground.js",
    "js/features/code-assist-authentication.js",
    "js/features/antigravity-authentication.js",
    "js/features/credentials.js",
    "js/features/credential-diagnostics.js",
    "js/features/credential-batch-actions.js",
    "js/features/logs.js",
    "js/features/environment-credentials.js",
    "js/features/provider-settings-shared.js",
    "js/features/provider-onboarding.js",
    "js/features/google-ai-studio-settings.js",
    "js/features/xai-settings.js",
    "js/features/openai-settings.js",
    "js/features/anthropic-settings.js",
    "js/features/ollama-settings.js",
    "js/features/antigravity-settings.js",
    "js/features/provider-owned-settings.js",
    "js/features/system-settings.js",
    "js/features/backups.js",
    "js/features/quality-policy.js",
    "js/features/dashboard.js",
    "js/features/about.js",
    "js/features/version.js",
    "js/features/mobile-navigation.js",
)


def _console_asset_paths():
    return tuple(
        FRONTEND_DIR / asset
        for asset in (
            *CONSOLE_STYLE_ASSETS,
            *CONSOLE_EARLY_SCRIPT_ASSETS,
            *CONSOLE_SCRIPT_ASSETS,
        )
    )


def _console_asset_version() -> str:
    digest = hashlib.blake2s(digest_size=10)
    for path in _console_asset_paths():
        metadata = path.stat()
        digest.update(f"{path}\0{metadata.st_mtime_ns}\0{metadata.st_size}\0".encode("utf-8"))
    return digest.hexdigest()


@lru_cache(maxsize=4)
def _read_console_bundle(asset_paths: tuple[str, ...], asset_version: str, separator: str) -> str:
    """Read a versioned bundle while keeping source files independently editable."""
    del asset_version
    return (
        separator.join(
            (FRONTEND_DIR / relative_path).read_text(encoding="utf-8").rstrip()
            for relative_path in asset_paths
        )
        + "\n"
    )


def _bundle_cache_headers(request: Request) -> dict[str, str]:
    if request.query_params.get("v"):
        return {"Cache-Control": "public, max-age=31536000, immutable"}
    return {"Cache-Control": "no-cache"}


def _assemble_console_html() -> str:
    """Assemble the console shell from its fixed, repository-owned fragments."""
    html_content = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    fragment_root = FRONTEND_DIR / "fragments"

    for relative_path in CONSOLE_FRAGMENT_PATHS:
        marker = f"<!-- include:fragments/{relative_path} -->"
        fragment = (fragment_root / relative_path).read_text(encoding="utf-8").rstrip()
        if marker not in html_content:
            raise RuntimeError(f"Console shell is missing the fragment marker: {marker}")
        html_content = html_content.replace(marker, fragment, 1)

    if "<!-- include:fragments/" in html_content:
        raise RuntimeError("Console shell contains an unresolved fragment marker.")
    return html_content


@router.get("/frontend/console.css", include_in_schema=False)
def serve_console_styles(request: Request):
    """Serve the ordered console styles as one cacheable response."""
    asset_version = _console_asset_version()
    content = _read_console_bundle(CONSOLE_STYLE_ASSETS, asset_version, "\n")
    return Response(
        content=content,
        media_type="text/css",
        headers=_bundle_cache_headers(request),
    )


@router.get("/frontend/theme.js", include_in_schema=False)
def serve_theme_script(request: Request):
    """Serve the blocking theme bootstrap separately to prevent a wrong-theme flash."""
    asset_version = _console_asset_version()
    content = _read_console_bundle(CONSOLE_EARLY_SCRIPT_ASSETS, asset_version, "\n;\n")
    return Response(
        content=content,
        media_type="text/javascript",
        headers=_bundle_cache_headers(request),
    )


@router.get("/frontend/console.js", include_in_schema=False)
def serve_console_scripts(request: Request):
    """Serve the ordered console modules as one cacheable classic script."""
    asset_version = _console_asset_version()
    content = _read_console_bundle(CONSOLE_SCRIPT_ASSETS, asset_version, "\n;\n")
    return Response(
        content=content,
        media_type="text/javascript",
        headers=_bundle_cache_headers(request),
    )


def _oauth_callback_page(
    success: bool, title: str, message: str, *, manual_callback: bool = False
) -> HTMLResponse:
    safe_title = escape(title)
    safe_message = escape(message)
    version = _console_asset_version()
    action_label = escape(
        translate("oauth.open_providers_new_tab" if manual_callback else "oauth.return_providers")
    )
    navigation = ' target="_blank" rel="noopener noreferrer"' if manual_callback else ""
    status = "success" if success else "failure"
    status_path = '<path d="m8 12 3 3 5-6"/>' if success else '<path d="m9 9 6 6m0-6-6 6"/>'
    html = f"""<!doctype html>
<html lang="{escape(get_locale())}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="referrer" content="no-referrer">
    <title>{safe_title} - Polaris</title>
    <script src="/frontend/theme.js?v={version}"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Google+Sans:ital,opsz,wght@0,17..18,400..700;1,17..18,400..700&amp;display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/frontend/console.css?v={version}">
</head>
<body>
    <main class="login-wrapper oauth-callback-wrapper">
        <section class="login-card signin-card oauth-callback-card" aria-labelledby="callbackTitle">
            <div class="login-brand">
                <span class="app-mark" aria-hidden="true">
                    <img class="app-mark-image" src="/frontend/assets/logo.png" alt="">
                </span>
                <span class="login-brand-title">Polaris</span>
            </div>
            <div class="oauth-callback-heading">
                <svg class="oauth-callback-icon {status}" viewBox="0 0 24 24" width="24" height="24"
                     fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"
                     stroke-linejoin="round" aria-hidden="true" focusable="false">
                    <circle cx="12" cy="12" r="9"/>{status_path}
                </svg>
                <h1 id="callbackTitle" class="login-title">{safe_title}</h1>
            </div>
            <p class="login-copy">{safe_message}</p>
            <a class="btn oauth-callback-return" href="/providers"{navigation}>{action_label}</a>
        </section>
    </main>
</body>
</html>"""
    return HTMLResponse(
        content=html,
        status_code=200 if success else 400,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.get("/callback", response_class=HTMLResponse, include_in_schema=False)
async def serve_oauth_callback(request: Request):
    """Render the OAuth callback result page."""
    if request.query_params.get("kiro") in {"received", "failed"}:
        received = request.query_params["kiro"] == "received"
        return _oauth_callback_page(
            received,
            "Kiro",
            translate("oauth.callback_received")
            if received
            else translate("oauth.retry", provider="Kiro"),
        )
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")
    is_claude_callback = is_claude_oauth_state(state)

    if error:
        provider_name = "Claude Code" if is_claude_callback else "Google"
        return _oauth_callback_page(
            False,
            translate("oauth.failed_title", provider=provider_name),
            translate("oauth.retry", provider=provider_name),
        )

    if is_claude_callback:
        # A public GET must not exchange tokens, consume the flow, or save credentials.
        # Keep the code in this URL for an explicit save in the original console tab.
        if not code or not code.strip():
            return _oauth_callback_page(
                False,
                translate("oauth.failed_title", provider="Claude Code"),
                translate("oauth.retry", provider="Claude Code"),
            )
        return _oauth_callback_page(
            True,
            "Claude Code",
            translate("oauth.copy_authorization_code"),
            manual_callback=True,
        )

    accepted, _message = accept_oauth_callback(code, state)
    if accepted:
        return _oauth_callback_page(
            True,
            translate("oauth.success_title", provider="OAuth"),
            translate("oauth.copy_callback"),
            manual_callback=True,
        )

    return _oauth_callback_page(
        False,
        translate("oauth.failed_title", provider="OAuth"),
        translate("oauth.retry", provider="OAuth"),
    )


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
@router.get("/setup", response_class=HTMLResponse, include_in_schema=False)
@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
@router.get("/ai-quality", response_class=HTMLResponse, include_in_schema=False)
@router.get("/access", response_class=HTMLResponse, include_in_schema=False)
@router.get("/identity", response_class=HTMLResponse, include_in_schema=False)
@router.get("/code_assist", response_class=HTMLResponse, include_in_schema=False)
@router.get("/credentials", response_class=HTMLResponse, include_in_schema=False)
@router.get("/models", response_class=HTMLResponse, include_in_schema=False)
@router.get("/playground", response_class=HTMLResponse, include_in_schema=False)
@router.get("/providers", response_class=HTMLResponse, include_in_schema=False)
@router.get("/provider", response_class=HTMLResponse, include_in_schema=False)
@router.get("/oauth", response_class=HTMLResponse, include_in_schema=False)
@router.get("/upload", response_class=HTMLResponse, include_in_schema=False)
@router.get("/config", response_class=HTMLResponse, include_in_schema=False)
@router.get("/activity", response_class=HTMLResponse, include_in_schema=False)
@router.get("/audit", response_class=HTMLResponse, include_in_schema=False)
@router.get("/logs", response_class=HTMLResponse, include_in_schema=False)
@router.get("/about", response_class=HTMLResponse, include_in_schema=False)
def serve_control_panel():
    """Serve the single responsive console entry point for public app routes."""
    try:
        html_content = _assemble_console_html()
        asset_version = _console_asset_version()
        html_content = re.sub(
            r'href="/frontend/console\.css(?:\?v=[^"]*)?"',
            f'href="/frontend/console.css?v={asset_version}"',
            html_content,
        )
        html_content = re.sub(
            r'src="/frontend/theme\.js(?:\?v=[^"]*)?"',
            f'src="/frontend/theme.js?v={asset_version}"',
            html_content,
        )
        html_content = re.sub(
            r'src="/frontend/console\.js(?:\?v=[^"]*)?"',
            f'src="/frontend/console.js?v={asset_version}"',
            html_content,
        )
        return HTMLResponse(content=html_content)
    except Exception as e:
        log.error(f"Failed to load control panel page: {e}")
        raise HTTPException(status_code=500, detail="Internal server error.")
