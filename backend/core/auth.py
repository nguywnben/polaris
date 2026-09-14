import asyncio
import os
import socket
import threading
import time
import uuid
from datetime import timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from config import (
    get_antigravity_api_url,
    get_antigravity_oauth_client_config,
    get_antigravity_user_agent,
    get_code_assist_oauth_client_config,
    get_config_value,
    get_server_port,
)
from log import log

from .credential_pool import upsert_credential_by_email
from .google_oauth_api import (
    Credentials,
    Flow,
    enable_required_apis,
    fetch_project_id_and_tier,
    get_user_projects,
    select_default_project,
)
from .provider_registry import build_antigravity_credential_filename
from .storage_adapter import get_storage_adapter
from .utils import CALLBACK_HOST, CODE_ASSIST_SCOPES, SCOPES, TOKEN_URL


async def get_callback_port():
    return int(await get_config_value("oauth_callback_port", "11451", "OAUTH_CALLBACK_PORT"))


async def _prepare_credentials_data(
    credentials: Credentials,
    project_id: str,
    mode: str = "code_assist",
    subscription_tier: str = None,
) -> Dict[str, Any]:
    if mode == "primary":
        client_id, client_secret = await get_antigravity_oauth_client_config()
        creds_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "token": credentials.access_token,
            "refresh_token": credentials.refresh_token,
            "scopes": SCOPES,
            "token_uri": TOKEN_URL,
            "project_id": project_id,
        }
    else:
        client_id, client_secret = await get_code_assist_oauth_client_config()
        creds_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "token": credentials.access_token,
            "refresh_token": credentials.refresh_token,
            "scopes": CODE_ASSIST_SCOPES,
            "token_uri": TOKEN_URL,
            "project_id": project_id,
        }
    if credentials.expires_at:
        if credentials.expires_at.tzinfo is None:
            expiry_utc = credentials.expires_at.replace(tzinfo=timezone.utc)
        else:
            expiry_utc = credentials.expires_at
        creds_data["expiry"] = expiry_utc.isoformat()
    return creds_data


def _credential_save_response(save_result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "file_path": save_result["filename"],
        "credential_saved": save_result.get("stored", False),
        "credential_action": save_result.get("action"),
        "credential_message": save_result.get("message"),
        "email": save_result.get("email"),
        "existing_expiry": save_result.get("existing_expiry"),
        "incoming_expiry": save_result.get("incoming_expiry"),
        "deleted_duplicates": save_result.get("deleted_duplicates", []),
    }


def _cleanup_auth_flow_server(state: str):
    if state in auth_flows:
        flow_data_to_clean = auth_flows[state]
        try:
            if flow_data_to_clean.get("server"):
                server = flow_data_to_clean["server"]
                port = flow_data_to_clean.get("callback_port")
                async_shutdown_server(server, port)
        except Exception as e:
            log.debug(f"Failed to shut down an OAuth callback server: {e}")
        del auth_flows[state]


class _OAuthLibPatcher:
    def __init__(self):
        import oauthlib.oauth2.rfc6749.parameters

        self.module = oauthlib.oauth2.rfc6749.parameters
        self.original_validate = None

    def __enter__(self):
        self.original_validate = self.module.validate_token_parameters

        def patched_validate(params):
            try:
                return self.original_validate(params)
            except Warning:
                pass

        self.module.validate_token_parameters = patched_validate
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.original_validate:
            self.module.validate_token_parameters = self.original_validate


auth_flows = {}


def accept_oauth_callback(code: Optional[str], state: Optional[str]) -> tuple[bool, str]:
    """Record an OAuth callback code for an active authorization flow."""
    log.info("Received an OAuth callback.")
    if not code or not state:
        return False, "The OAuth callback is missing a code or state parameter."
    if state not in auth_flows:
        return False, "The OAuth session was not found or has expired."

    auth_flows[state]["code"] = code
    auth_flows[state]["completed"] = True
    log.info("OAuth callback accepted.")
    return True, "OAuth authentication successful."


MAX_AUTH_FLOWS = 20
DEFAULT_PROJECT_ID = "gemini-pro-1751713012-07fc4dfd"
OAUTH_START_FAILURE = (
    "Unable to start OAuth authentication. Check the OAuth configuration and retry."
)
OAUTH_CREDENTIAL_FAILURE = (
    "Unable to retrieve OAuth credentials. Start authentication again and retry."
)


def cleanup_auth_flows_for_memory():
    global auth_flows
    cleanup_expired_flows()
    if len(auth_flows) > 10:
        sorted_flows = sorted(
            auth_flows.items(), key=lambda x: x[1].get("created_at", 0), reverse=True
        )
        new_auth_flows = dict(sorted_flows[:10])
        for state, flow_data in auth_flows.items():
            if state not in new_auth_flows:
                try:
                    if flow_data.get("server"):
                        server = flow_data["server"]
                        port = flow_data.get("callback_port")
                        async_shutdown_server(server, port)
                except Exception:
                    pass
                flow_data.clear()
        auth_flows = new_auth_flows
        log.info(f"Pruned OAuth flow cache to {len(auth_flows)} active entries.")
    return len(auth_flows)


async def find_available_port(start_port: int = None) -> int:
    if start_port is None:
        start_port = await get_callback_port()
    for port in range(start_port, start_port + 100):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("0.0.0.0", port))
                log.info(f"Using OAuth callback port {port}.")
                return port
        except OSError:
            continue
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("0.0.0.0", 0))
            port = s.getsockname()[1]
            log.info(f"Using fallback OAuth callback port {port}.")
            return port
    except OSError as e:
        log.error(f"Unable to allocate an OAuth callback port: {e}")
        raise RuntimeError("Unable to allocate an OAuth callback port.") from e


def create_callback_server(port: int) -> HTTPServer:
    try:
        server = HTTPServer(("0.0.0.0", port), AuthCallbackHandler)
        server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.timeout = 1.0
        log.info(f"OAuth callback server listening on port {port}.")
        return server
    except OSError as e:
        log.error(f"Failed to create OAuth callback server on port {port}: {e}")
        raise


class AuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query_components = parse_qs(urlparse(self.path).query)
        code = query_components.get("code", [None])[0]
        state = query_components.get("state", [None])[0]
        accepted, message = accept_oauth_callback(code, state)
        if accepted:
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<h1>OAuth authentication successful.</h1><p>You can close this window and return to the console.</p>"
            )
        else:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(f"<h1>Authentication failed.</h1><p>{message}</p>".encode("utf-8"))

    def log_message(self, format, *args):
        pass


async def create_auth_url(
    project_id: Optional[str] = None,
    user_session: str = None,
    mode: str = "code_assist",
) -> Dict[str, Any]:
    try:
        if mode == "primary":
            client_id, client_secret = await get_antigravity_oauth_client_config()
            scopes = SCOPES
            missing_config_error = "Google Antigravity OAuth client configuration is unavailable."
        else:
            client_id, client_secret = await get_code_assist_oauth_client_config()
            scopes = CODE_ASSIST_SCOPES
            missing_config_error = "Code Assist OAuth client configuration is unavailable."
        if not client_id or not client_secret:
            return {
                "success": False,
                "error": missing_config_error,
                "error_code": "missing_oauth_client_config",
            }
        callback_server = None
        server_thread = None
        if mode == "primary":
            callback_port = await get_server_port()
            callback_url = f"http://{CALLBACK_HOST}:{callback_port}/callback"
            log.info(f"Provider OAuth callback will return to {callback_url}.")
        else:
            callback_port = await find_available_port()
            callback_url = f"http://{CALLBACK_HOST}:{callback_port}"
            try:
                callback_server = create_callback_server(callback_port)
                server_thread = threading.Thread(
                    target=callback_server.serve_forever,
                    daemon=True,
                    name=f"OAuth-Server-{callback_port}",
                )
                server_thread.start()
                log.info(f"OAuth callback server started on {callback_url}.")
            except Exception as e:
                log.error(
                    "Failed to start OAuth callback server "
                    f"(port={callback_port}, error_type={type(e).__name__})."
                )
                return {
                    "success": False,
                    "error": (
                        "Unable to start the local OAuth callback listener. "
                        "Check port availability and retry."
                    ),
                }
        flow = Flow(
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes,
            redirect_uri=callback_url,
        )
        # The externally visible OAuth state is independent from the internal,
        # non-capability session reference retained for flow ownership checks.
        state = str(uuid.uuid4())
        auth_url = flow.get_auth_url(state=state)
        if len(auth_flows) >= MAX_AUTH_FLOWS:
            oldest_state = min(auth_flows.keys(), key=lambda k: auth_flows[k].get("created_at", 0))
            try:
                old_flow = auth_flows[oldest_state]
                if old_flow.get("server"):
                    server = old_flow["server"]
                    port = old_flow.get("callback_port")
                    async_shutdown_server(server, port)
            except Exception as e:
                log.warning(
                    f"Failed to clean up the oldest OAuth flow (error_type={type(e).__name__})."
                )
            del auth_flows[oldest_state]
            log.debug("Removed the oldest OAuth flow.")
        auth_flows[state] = {
            "flow": flow,
            "project_id": project_id,
            "user_session": user_session,
            "callback_port": callback_port,
            "callback_url": callback_url,
            "server": callback_server,
            "server_thread": server_thread,
            "code": None,
            "completed": False,
            "created_at": time.time(),
            "auto_project_detection": project_id is None,
            "mode": mode,
        }
        cleanup_expired_flows()
        log.info(f"Created an OAuth flow in {mode} mode.")
        log.debug(f"OAuth redirect URI: {callback_url}")
        log.debug(f"OAuth auto project detection: {project_id is None}")
        return {
            "auth_url": auth_url,
            "state": state,
            "callback_port": callback_port,
            "callback_url": callback_url,
            "success": True,
            "auto_project_detection": project_id is None,
            "detected_project_id": project_id,
        }
    except Exception as e:
        log.error(f"Failed to create OAuth authorization URL (error_type={type(e).__name__}).")
        return {"success": False, "error": OAUTH_START_FAILURE}


def wait_for_callback_sync(state: str, timeout: int = 300) -> Optional[str]:
    if state not in auth_flows:
        log.error("The OAuth flow was not found while waiting for a callback.")
        return None
    flow_data = auth_flows[state]
    callback_port = flow_data["callback_port"]
    log.info(f"Waiting for OAuth callback on port {callback_port}.")
    start_time = time.time()
    while time.time() - start_time < timeout:
        if flow_data.get("code"):
            log.info("Received the expected OAuth callback.")
            return flow_data["code"]
        time.sleep(0.5)
        if state in auth_flows:
            flow_data = auth_flows[state]
    log.warning(f"OAuth callback timed out after {timeout} seconds.")
    return None


async def complete_auth_flow(
    project_id: Optional[str] = None, user_session: str = None
) -> Dict[str, Any]:
    try:
        state = None
        flow_data = None
        if project_id:
            for s, data in auth_flows.items():
                if data["project_id"] == project_id:
                    if user_session:
                        if data.get("user_session") != user_session:
                            continue
                        state = s
                        flow_data = data
                        break
                    if not state:
                        state = s
                        flow_data = data
        if not state:
            for s, data in auth_flows.items():
                if data.get("auto_project_detection", False):
                    if user_session and data.get("user_session") == user_session:
                        state = s
                        flow_data = data
                        break
                    elif not state:
                        state = s
                        flow_data = data
        if not state or not flow_data:
            return {
                "success": False,
                "error": "Authentication flow not found. Please click to get an authentication link first.",
            }
        if not project_id:
            project_id = flow_data.get("project_id")
            if not project_id:
                project_id = DEFAULT_PROJECT_ID
                log.warning(
                    f"No project ID found for OAuth flow; using default project ID {DEFAULT_PROJECT_ID}."
                )
        flow = flow_data["flow"]
        if not flow_data.get("code"):
            log.info("Waiting for OAuth callback before exchanging credentials.")
            auth_code = wait_for_callback_sync(state)
            if not auth_code:
                return {
                    "success": False,
                    "error": "Authorization callback not received. Please ensure you completed OAuth authorization in the browser.",
                }
            auth_flows[state]["code"] = auth_code
            auth_flows[state]["completed"] = True
        else:
            auth_code = flow_data["code"]
        with _OAuthLibPatcher():
            try:
                credentials = await flow.exchange_code(auth_code)
                if flow_data.get("auto_project_detection", False) and (not project_id):
                    log.info("Auto-detecting Google Cloud project for OAuth credentials.")
                    user_projects = await get_user_projects(credentials)
                    if user_projects:
                        if len(user_projects) == 1:
                            project_id = user_projects[0].get("projectId")
                            if project_id:
                                flow_data["project_id"] = project_id
                                log.info(f"Auto-detected Google Cloud project ID: {project_id}.")
                        else:
                            project_id = await select_default_project(user_projects)
                            if project_id:
                                flow_data["project_id"] = project_id
                                log.info(f"Selected Google Cloud project ID: {project_id}.")
                            else:
                                return {
                                    "success": False,
                                    "error": "Please select one of the following projects",
                                    "requires_project_selection": True,
                                    "available_projects": [
                                        {
                                            "project_id": p.get("projectId"),
                                            "name": p.get("displayName") or p.get("projectId"),
                                            "projectNumber": p.get("projectNumber"),
                                        }
                                        for p in user_projects
                                    ],
                                }
                    else:
                        project_id = DEFAULT_PROJECT_ID
                        flow_data["project_id"] = project_id
                        log.warning(
                            f"No Google Cloud projects were found; using default project ID {DEFAULT_PROJECT_ID}."
                        )
                if not project_id:
                    project_id = DEFAULT_PROJECT_ID
                    flow_data["project_id"] = project_id
                    log.warning(
                        f"Project ID was still empty; using default project ID {DEFAULT_PROJECT_ID}."
                    )
                save_result = await save_credentials(credentials, project_id)
                creds_data = await _prepare_credentials_data(
                    credentials, project_id, mode="code_assist"
                )
                _cleanup_auth_flow_server(state)
                log.info(
                    f"OAuth credential pool result: {save_result.get('action')} ({save_result.get('filename')})."
                )
                return {
                    "success": True,
                    "credentials": creds_data,
                    "auto_detected_project": flow_data.get("auto_project_detection", False),
                    **_credential_save_response(save_result),
                }
            except Exception as e:
                log.error(f"Failed to retrieve OAuth credential (error_type={type(e).__name__}).")
                return {"success": False, "error": OAUTH_CREDENTIAL_FAILURE}
    except Exception as e:
        log.error(f"Failed to complete OAuth flow (error_type={type(e).__name__}).")
        return {"success": False, "error": OAUTH_CREDENTIAL_FAILURE}


async def asyncio_complete_auth_flow(
    project_id: Optional[str] = None, user_session: str = None, mode: str = "code_assist"
) -> Dict[str, Any]:
    try:
        log.info("Completing OAuth flow asynchronously.")
        state = None
        flow_data = None
        log.debug(f"Requested project ID: {project_id or 'auto'}; mode: {mode}.")
        if project_id:
            log.info(f"Searching OAuth flow by project ID {project_id}.")
            for s, data in auth_flows.items():
                if data["project_id"] == project_id:
                    if user_session:
                        if data.get("user_session") != user_session:
                            continue
                        state = s
                        flow_data = data
                        log.info("Found an OAuth flow for the current session.")
                        break
                    if not state:
                        state = s
                        flow_data = data
                        log.info(f"Found an OAuth flow for project {project_id}.")
        if not state:
            log.info(
                "Searching for the latest OAuth flow that supports automatic project detection."
            )
            completed_flows = []
            for s, data in auth_flows.items():
                if data.get("auto_project_detection", False):
                    if user_session and data.get("user_session") == user_session:
                        if data.get("code"):
                            completed_flows.append((s, data, data.get("created_at", 0)))
            if completed_flows:
                completed_flows.sort(key=lambda x: x[2], reverse=True)
                state, flow_data, _ = completed_flows[0]
                log.info("Using the latest completed OAuth flow.")
            else:
                pending_flows = []
                for s, data in auth_flows.items():
                    if data.get("auto_project_detection", False):
                        if user_session and data.get("user_session") == user_session:
                            pending_flows.append((s, data, data.get("created_at", 0)))
                        elif not user_session:
                            pending_flows.append((s, data, data.get("created_at", 0)))
                if pending_flows:
                    pending_flows.sort(key=lambda x: x[2], reverse=True)
                    state, flow_data, _ = pending_flows[0]
                    log.info("Using the latest pending OAuth flow.")
        if not state or not flow_data:
            log.error("No matching OAuth flow was found.")
            log.debug(f"Available OAuth flow count: {len(auth_flows)}.")
            return {
                "success": False,
                "error": "Authentication flow not found. Please click to get an authentication link first.",
            }
        log.info(f"Using an OAuth flow in {flow_data.get('mode', mode)} mode.")
        log.debug(f"OAuth flow completed: {flow_data.get('completed', False)}")
        log.debug(f"OAuth auto project detection: {flow_data.get('auto_project_detection', False)}")
        if flow_data.get("auto_project_detection", False) and (not project_id):
            log.info("Project ID will be auto-detected after credential exchange.")
        elif not project_id:
            log.info("Resolving Project ID from the OAuth flow state.")
            project_id = flow_data.get("project_id")
            if not project_id:
                project_id = DEFAULT_PROJECT_ID
                flow_data["project_id"] = project_id
                log.warning(f"No project ID found; using default project ID {DEFAULT_PROJECT_ID}.")
        else:
            log.info(f"Using provided project ID {project_id}.")
        log.info("Waiting for OAuth callback code.")
        log.debug(f"OAuth callback port: {flow_data.get('callback_port')}")
        log.debug("OAuth wait timeout: 60 seconds.")
        max_wait_time = 60
        wait_interval = 1
        waited = 0
        while waited < max_wait_time:
            if flow_data.get("code"):
                log.info("OAuth callback code received.")
                break
            if waited % 5 == 0 and waited > 0:
                log.info(f"Waiting for OAuth callback code ({waited}s elapsed).")
                log.debug("The OAuth flow is still pending.")
            await asyncio.sleep(wait_interval)
            waited += wait_interval
            if state in auth_flows:
                flow_data = auth_flows[state]
        if not flow_data.get("code"):
            log.error("OAuth callback code was not received before timeout.")
            return {
                "success": False,
                "error": "OAuth callback timed out. Please ensure you completed authorization in your browser and saw the success page.",
            }
        flow = flow_data["flow"]
        auth_code = flow_data["code"]
        log.info("Exchanging OAuth authorization code for credentials.")
        with _OAuthLibPatcher():
            try:
                log.info("Requesting OAuth access token.")
                credentials = await flow.exchange_code(auth_code)
                log.info("OAuth access token retrieved.")
                log.debug("OAuth token response accepted by the client library.")
                cred_mode = flow_data.get("mode", "code_assist") if flow_data.get("mode") else mode
                if cred_mode == "primary":
                    log.info("Fetching provider project ID and subscription tier.")
                    primary_url = await get_antigravity_api_url()
                    user_agent = await get_antigravity_user_agent()
                    project_id, subscription_tier = await fetch_project_id_and_tier(
                        credentials.access_token, user_agent, primary_url
                    )
                    if project_id:
                        log.info(
                            f"Fetched Project ID from provider API: {project_id}; tier: {subscription_tier}."
                        )
                    else:
                        project_id = DEFAULT_PROJECT_ID
                        log.warning(
                            f"Unable to fetch Project ID from provider API; using default Project ID {project_id}."
                        )
                    save_result = await save_credentials(
                        credentials, project_id, mode="primary", subscription_tier=subscription_tier
                    )
                    creds_data = await _prepare_credentials_data(
                        credentials, project_id, mode="primary", subscription_tier=subscription_tier
                    )
                    _cleanup_auth_flow_server(state)
                    log.info(
                        f"Provider OAuth credential pool result: {save_result.get('action')} ({save_result.get('filename')})."
                    )
                    return {
                        "success": True,
                        "credentials": creds_data,
                        "auto_detected_project": False,
                        "mode": "provider",
                        **_credential_save_response(save_result),
                    }
                if flow_data.get("auto_project_detection", False) and (not project_id):
                    log.info("Standard mode: fetching Project ID from the project list.")
                    user_projects = await get_user_projects(credentials)
                    if user_projects:
                        if len(user_projects) == 1:
                            project_id = user_projects[0].get("projectId")
                            if project_id:
                                flow_data["project_id"] = project_id
                                log.info(f"Auto-detected Google Cloud project ID: {project_id}.")
                                log.info(f"Enabling required APIs for project {project_id}.")
                                await enable_required_apis(credentials, project_id)
                        else:
                            project_id = await select_default_project(user_projects)
                            if project_id:
                                flow_data["project_id"] = project_id
                                log.info(f"Selected Google Cloud project ID: {project_id}.")
                                log.info(f"Enabling required APIs for project {project_id}.")
                                await enable_required_apis(credentials, project_id)
                            else:
                                return {
                                    "success": False,
                                    "error": "Please select one of the following projects",
                                    "requires_project_selection": True,
                                    "available_projects": [
                                        {
                                            "project_id": p.get("projectId"),
                                            "name": p.get("displayName") or p.get("projectId"),
                                            "projectNumber": p.get("projectNumber"),
                                        }
                                        for p in user_projects
                                    ],
                                }
                    else:
                        project_id = DEFAULT_PROJECT_ID
                        flow_data["project_id"] = project_id
                        log.warning(
                            f"No Google Cloud projects were found; using default project ID {DEFAULT_PROJECT_ID}."
                        )
                elif project_id:
                    log.info(f"Using provided project ID {project_id}.")
                    await enable_required_apis(credentials, project_id)
                if not project_id:
                    project_id = DEFAULT_PROJECT_ID
                    flow_data["project_id"] = project_id
                    log.warning(
                        f"Project ID was still empty; using default project ID {DEFAULT_PROJECT_ID}."
                    )
                save_result = await save_credentials(credentials, project_id)
                creds_data = await _prepare_credentials_data(
                    credentials, project_id, mode="code_assist"
                )
                _cleanup_auth_flow_server(state)
                log.info(
                    f"Code Assist OAuth credential pool result: {save_result.get('action')} ({save_result.get('filename')})."
                )
                return {
                    "success": True,
                    "credentials": creds_data,
                    "auto_detected_project": flow_data.get("auto_project_detection", False),
                    **_credential_save_response(save_result),
                }
            except Exception as e:
                log.error(f"Failed to retrieve OAuth credential (error_type={type(e).__name__}).")
                return {"success": False, "error": OAUTH_CREDENTIAL_FAILURE}
    except Exception as e:
        log.error(f"Failed to complete asynchronous OAuth flow (error_type={type(e).__name__}).")
        return {"success": False, "error": OAUTH_CREDENTIAL_FAILURE}


async def complete_auth_flow_from_callback_url(
    callback_url: str,
    project_id: Optional[str] = None,
    mode: str = "code_assist",
    user_session: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        log.info("Starting authentication from an OAuth callback URL.")
        parsed_url = urlparse(callback_url)
        query_params = parse_qs(parsed_url.query)
        if "state" not in query_params or "code" not in query_params:
            return {
                "success": False,
                "error": "The callback URL is missing a required state or code parameter.",
            }
        state = query_params["state"][0]
        code = query_params["code"][0]
        log.info("Parsed the required OAuth callback parameters.")
        if state not in auth_flows:
            return {
                "success": False,
                "error": "The authentication flow was not found. Start authentication again.",
            }
        flow_data = auth_flows[state]
        if user_session and flow_data.get("user_session") != user_session:
            return {
                "success": False,
                "error": "The authentication flow was not found. Start authentication again.",
            }
        flow = flow_data["flow"]
        redirect_uri = flow.redirect_uri
        log.debug(f"Using OAuth redirect URI: {redirect_uri}")
        try:
            credentials = await flow.exchange_code(code)
            log.info("Access token retrieved.")
            cred_mode = flow_data.get("mode", "code_assist") if flow_data.get("mode") else mode
            if cred_mode == "primary":
                log.info("Provider callback URL received; fetching project ID from API.")
                primary_url = await get_antigravity_api_url()
                user_agent = await get_antigravity_user_agent()
                project_id, subscription_tier = await fetch_project_id_and_tier(
                    credentials.access_token, user_agent, primary_url
                )
                if project_id:
                    log.info(
                        f"Fetched Project ID from provider API: {project_id}; tier: {subscription_tier}."
                    )
                else:
                    project_id = DEFAULT_PROJECT_ID
                    log.warning(
                        f"Unable to fetch Project ID from provider API; using default Project ID {project_id}."
                    )
                save_result = await save_credentials(
                    credentials, project_id, mode="primary", subscription_tier=subscription_tier
                )
                creds_data = await _prepare_credentials_data(
                    credentials, project_id, mode="primary", subscription_tier=subscription_tier
                )
                _cleanup_auth_flow_server(state)
                log.info(
                    f"Provider OAuth callback credential pool result: {save_result.get('action')} ({save_result.get('filename')})."
                )
                return {
                    "success": True,
                    "credentials": creds_data,
                    "auto_detected_project": False,
                    "mode": "provider",
                    **_credential_save_response(save_result),
                }
            detected_project_id = None
            auto_detected = False
            subscription_tier = None
            if not project_id:
                try:
                    log.info("Standard mode: fetching Project ID from the project list.")
                    projects = await get_user_projects(credentials)
                    if projects:
                        if len(projects) == 1:
                            detected_project_id = projects[0]["projectId"]
                            auto_detected = True
                            log.info(
                                f"Automatically detected unique Project ID: {detected_project_id}."
                            )
                        else:
                            detected_project_id = projects[0]["projectId"]
                            auto_detected = True
                            log.info(
                                f"Detected {len(projects)} projects; selected the first project automatically: {detected_project_id}."
                            )
                            log.debug(
                                f"Other available projects: {[p['projectId'] for p in projects[1:]]}"
                            )
                    else:
                        detected_project_id = DEFAULT_PROJECT_ID
                        auto_detected = False
                        log.warning(
                            f"No accessible projects detected; using default Project ID {detected_project_id}."
                        )
                except Exception as e:
                    log.warning(
                        "Failed to retrieve project list; using the default Project ID "
                        f"(error_type={type(e).__name__})."
                    )
                    detected_project_id = DEFAULT_PROJECT_ID
                    auto_detected = False
            else:
                detected_project_id = project_id
            if detected_project_id:
                try:
                    log.info(f"Enabling required API services for project {detected_project_id}.")
                    await enable_required_apis(credentials, detected_project_id)
                except Exception as e:
                    log.warning(f"Failed to enable API services (error_type={type(e).__name__}).")
            save_result = await save_credentials(
                credentials, detected_project_id, subscription_tier=subscription_tier
            )
            creds_data = await _prepare_credentials_data(
                credentials,
                detected_project_id,
                mode="code_assist",
                subscription_tier=subscription_tier,
            )
            _cleanup_auth_flow_server(state)
            log.info(
                f"Code Assist callback credential pool result: {save_result.get('action')} ({save_result.get('filename')})."
            )
            return {
                "success": True,
                "credentials": creds_data,
                "auto_detected_project": auto_detected,
                **_credential_save_response(save_result),
            }
        except Exception as e:
            log.error(
                "Failed to retrieve OAuth credential from callback URL "
                f"(error_type={type(e).__name__})."
            )
            return {"success": False, "error": OAUTH_CREDENTIAL_FAILURE}
    except Exception as e:
        log.error(
            f"Failed to complete OAuth flow from callback URL (error_type={type(e).__name__})."
        )
        return {"success": False, "error": OAUTH_CREDENTIAL_FAILURE}


async def save_credentials(
    creds: Credentials, project_id: str, mode: str = "code_assist", subscription_tier: str = None
) -> Dict[str, Any]:
    timestamp = int(time.time())
    creds_data = await _prepare_credentials_data(creds, project_id, mode, subscription_tier)
    if mode == "primary":
        filename = build_antigravity_credential_filename(creds_data)
    else:
        filename = f"{project_id}-{timestamp}.json"
    save_result = await upsert_credential_by_email(filename, creds_data, mode=mode)
    if save_result.get("stored"):
        try:
            storage_adapter = await get_storage_adapter()
            stored_filename = save_result["filename"]
            default_state = {
                "error_codes": [],
                "disabled": False,
                "last_success": time.time(),
                "user_email": save_result.get("email"),
                "tier": subscription_tier,
            }
            await storage_adapter.update_credential_state(stored_filename, default_state, mode=mode)
            log.info(f"Initialized credential state for {stored_filename}.")
        except Exception as e:
            log.warning(
                f"Failed to initialize credential state for {save_result.get('filename')}: {e}"
            )
    return save_result


def async_shutdown_server(server, port):

    def shutdown_server_async():
        try:
            shutdown_completed = threading.Event()

            def do_shutdown():
                try:
                    server.shutdown()
                    server.server_close()
                    shutdown_completed.set()
                    log.info(f"OAuth callback server on port {port} shut down.")
                except Exception as e:
                    shutdown_completed.set()
                    log.debug(
                        f"Error while shutting down OAuth callback server on port {port}: {e}"
                    )

            shutdown_worker = threading.Thread(target=do_shutdown, daemon=True)
            shutdown_worker.start()
            if shutdown_completed.wait(timeout=5):
                log.debug(f"OAuth callback server shutdown completed on port {port}.")
            else:
                log.warning(
                    f"OAuth callback server on port {port} did not shut down within timeout."
                )
        except Exception as e:
            log.debug(f"Failed to schedule OAuth callback server shutdown on port {port}: {e}")

    shutdown_thread = threading.Thread(target=shutdown_server_async, daemon=True)
    shutdown_thread.start()
    log.debug(f"Scheduled OAuth callback server shutdown on port {port}.")


def cleanup_expired_flows():
    current_time = time.time()
    EXPIRY_TIME = 600
    states_to_remove = [
        state
        for state, flow_data in auth_flows.items()
        if current_time - flow_data["created_at"] > EXPIRY_TIME
    ]
    cleaned_count = 0
    for state in states_to_remove:
        flow_data = auth_flows.get(state)
        if flow_data:
            try:
                if flow_data.get("server"):
                    server = flow_data["server"]
                    port = flow_data.get("callback_port")
                    async_shutdown_server(server, port)
            except Exception as e:
                log.debug(f"Failed to clean up an expired OAuth flow: {e}")
            flow_data.clear()
            del auth_flows[state]
            cleaned_count += 1
    if cleaned_count > 0:
        log.info(f"Cleaned up {cleaned_count} expired OAuth flow(s).")
    if len(auth_flows) > 20:
        import gc

        gc.collect()
        log.debug("Triggered garbage collection for OAuth flow cache.")


def get_auth_status(project_id: str, user_session: Optional[str] = None) -> Dict[str, Any]:
    for state, flow_data in auth_flows.items():
        if flow_data["project_id"] == project_id:
            if user_session and flow_data.get("user_session") != user_session:
                continue
            return {
                "status": "completed" if flow_data["completed"] else "pending",
                "state": state,
                "created_at": flow_data["created_at"],
            }
    return {"status": "not_found"}


def get_auth_status_by_state(state: str, user_session: Optional[str] = None) -> Dict[str, Any]:
    """Return OAuth flow status for the current browser session without blocking."""
    flow_data = auth_flows.get(state)
    if not flow_data:
        return {"status": "not_found"}
    if user_session and flow_data.get("user_session") != user_session:
        return {"status": "not_found"}
    return {
        "status": "completed" if flow_data.get("completed") or flow_data.get("code") else "pending",
        "state": state,
        "created_at": flow_data.get("created_at"),
        "mode": "provider"
        if flow_data.get("mode") == "primary"
        else flow_data.get("mode", "code_assist"),
    }


auth_tokens = {}
TOKEN_EXPIRY = 3600


async def verify_password(password: str) -> bool:
    import config
    from core.passwords import hash_password, is_password_hash, verify_password_value

    if not await config.has_password_configured():
        return False
    correct_password = await config.get_panel_password()
    if not correct_password:
        return False
    is_valid = verify_password_value(password, correct_password)
    if is_valid and not is_password_hash(correct_password) and not os.getenv("PANEL_PASSWORD"):
        try:
            storage_adapter = await get_storage_adapter()
            await storage_adapter.set_config("panel_password", hash_password(password))
            await config.reload_config()
            log.info("Migrated the control-panel password to scrypt storage.")
        except Exception as exc:
            log.warning(f"Failed to migrate the control-panel password hash: {exc}")
    return is_valid
