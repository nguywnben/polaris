import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx
import jwt
from config import (
    get_googleapis_proxy_url,
    get_oauth_proxy_url,
    get_proxy_config,
    get_resource_manager_api_url,
    get_service_usage_api_url,
)
from core.google_endpoint_validation import (
    normalize_google_api_base_url,
    normalize_google_oauth_base_url,
)
from core.httpx_client import get_async, post_async
from log import log


class TokenError(Exception):
    pass


async def _format_oauth_request_error(action: str, token_url: str, error: Exception) -> str:
    """Keep actionable transport hints without proxy credentials or raw exception text."""
    try:
        proxy_url = await get_proxy_config()
    except Exception:
        proxy_url = None

    proxy_hint = (
        "An outbound proxy is configured." if proxy_url else "No outbound proxy is configured."
    )
    return (
        f"{action}: Unable to reach OAuth token endpoint {token_url}. "
        "Check the OAuth API endpoint and configure an outbound proxy if this environment cannot access Google directly. "
        f"{proxy_hint} Transport error type: {type(error).__name__}."
    )


class Credentials:
    def __init__(
        self,
        access_token: str,
        refresh_token: str = None,
        client_id: str = None,
        client_secret: str = None,
        expires_at: datetime = None,
        project_id: str = None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.expires_at = expires_at
        self.project_id = project_id
        self.oauth_base_url = None
        self.token_endpoint = None

    def is_expired(self) -> bool:
        if not self.expires_at:
            return True
        buffer = timedelta(minutes=3)
        return self.expires_at - buffer <= datetime.now(timezone.utc)

    async def refresh_if_needed(self) -> bool:
        if not self.is_expired():
            return False
        if not self.refresh_token:
            raise TokenError("Refresh token is required but not provided")
        await self.refresh()
        return True

    async def refresh(self):
        if not self.refresh_token:
            raise TokenError("No refresh token available")
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }
        try:
            oauth_base_url = normalize_google_oauth_base_url(
                await get_oauth_proxy_url(), setting_name="oauth_url"
            )
            token_url = f"{oauth_base_url.rstrip('/')}/token"
            response = await post_async(
                token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                follow_redirects=False,
            )
            response.raise_for_status()
            token_data = response.json()
            self.access_token = token_data["access_token"]
            if "expires_in" in token_data:
                expires_in = int(token_data["expires_in"])
                current_utc = datetime.now(timezone.utc)
                self.expires_at = current_utc + timedelta(seconds=expires_in)
                log.debug(
                    f"Token refresh: current UTC time={current_utc.isoformat()}, expires_in={expires_in}s, expiry={self.expires_at.isoformat()}"
                )
            if "refresh_token" in token_data:
                self.refresh_token = token_data["refresh_token"]
            log.debug(f"Token refreshed. Expires at {self.expires_at}.")
        except httpx.RequestError as e:
            error_msg = await _format_oauth_request_error("Token refresh failed", token_url, e)
            log.error(error_msg)
            token_error = TokenError(error_msg)
            token_error.status_code = None
            raise token_error
        except Exception as e:
            error_msg = str(e)
            status_code = None
            if hasattr(e, "response") and hasattr(e.response, "status_code"):
                status_code = e.response.status_code
                error_msg = f"Token refresh failed (HTTP {status_code}): {error_msg}"
            else:
                error_msg = f"Token refresh failed: {error_msg}"
            log.error(error_msg)
            token_error = TokenError(error_msg)
            token_error.status_code = status_code
            raise token_error

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Credentials":
        expires_at = None
        if "expiry" in data and data["expiry"]:
            try:
                expiry_str = data["expiry"]
                if isinstance(expiry_str, str):
                    if expiry_str.endswith("Z"):
                        expires_at = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
                    elif "+" in expiry_str:
                        expires_at = datetime.fromisoformat(expiry_str)
                    else:
                        expires_at = datetime.fromisoformat(expiry_str).replace(tzinfo=timezone.utc)
            except ValueError:
                log.warning(f"Unable to parse expiration time: {expiry_str}")
        return cls(
            access_token=data.get("token") or data.get("access_token", ""),
            refresh_token=data.get("refresh_token"),
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
            expires_at=expires_at,
            project_id=data.get("project_id"),
        )

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "project_id": self.project_id,
        }
        if self.expires_at:
            result["expiry"] = self.expires_at.isoformat()
        return result


def merge_refreshed_credential_data(
    credential_data: Dict[str, Any], credentials: Credentials
) -> Dict[str, Any]:
    """Update token fields without discarding provider metadata or model catalogs."""
    merged = dict(credential_data)
    for key, value in credentials.to_dict().items():
        if value is not None:
            merged[key] = value
    if credentials.access_token:
        # Keep both spellings because imported credentials and legacy adapters use both.
        merged["access_token"] = credentials.access_token
        merged["token"] = credentials.access_token
    return merged


class Flow:
    def __init__(
        self, client_id: str, client_secret: str, scopes: List[str], redirect_uri: str = None
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.scopes = scopes
        self.redirect_uri = redirect_uri
        self.oauth_base_url = None
        self.token_endpoint = None
        self.auth_endpoint = "https://accounts.google.com/o/oauth2/auth"
        self.credentials: Optional[Credentials] = None

    def get_auth_url(self, state: str = None, **kwargs) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.scopes),
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
        if state:
            params["state"] = state
        params.update(kwargs)
        return f"{self.auth_endpoint}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> Credentials:
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "code": code,
            "grant_type": "authorization_code",
        }
        try:
            oauth_base_url = normalize_google_oauth_base_url(
                await get_oauth_proxy_url(), setting_name="oauth_url"
            )
            token_url = f"{oauth_base_url.rstrip('/')}/token"
            response = await post_async(
                token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                follow_redirects=False,
            )
            response.raise_for_status()
            token_data = response.json()
            expires_at = None
            if "expires_in" in token_data:
                expires_in = int(token_data["expires_in"])
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            self.credentials = Credentials(
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                client_id=self.client_id,
                client_secret=self.client_secret,
                expires_at=expires_at,
            )
            return self.credentials
        except httpx.RequestError as e:
            error_msg = await _format_oauth_request_error("Failed to retrieve token", token_url, e)
            log.error(error_msg)
            raise TokenError(error_msg)
        except Exception as e:
            error_msg = f"Failed to retrieve token: {str(e)}"
            log.error(error_msg)
            raise TokenError(error_msg)


class ServiceAccount:
    def __init__(
        self, email: str, private_key: str, project_id: str = None, scopes: List[str] = None
    ):
        self.email = email
        self.private_key = private_key
        self.project_id = project_id
        self.scopes = scopes or []
        self.oauth_base_url = None
        self.token_endpoint = None
        self.access_token: Optional[str] = None
        self.expires_at: Optional[datetime] = None

    def is_expired(self) -> bool:
        if not self.expires_at:
            return True
        buffer = timedelta(minutes=3)
        return self.expires_at - buffer <= datetime.now(timezone.utc)

    def create_jwt(self) -> str:
        now = int(time.time())
        payload = {
            "iss": self.email,
            "scope": " ".join(self.scopes) if self.scopes else "",
            "aud": self.token_endpoint,
            "exp": now + 3600,
            "iat": now,
        }
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    async def get_access_token(self) -> str:
        if not self.is_expired() and self.access_token:
            return self.access_token
        assertion = self.create_jwt()
        data = {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}
        try:
            oauth_base_url = normalize_google_oauth_base_url(
                await get_oauth_proxy_url(), setting_name="oauth_url"
            )
            token_url = f"{oauth_base_url.rstrip('/')}/token"
            response = await post_async(
                token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                follow_redirects=False,
            )
            response.raise_for_status()
            token_data = response.json()
            self.access_token = token_data["access_token"]
            if "expires_in" in token_data:
                expires_in = int(token_data["expires_in"])
                self.expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            return self.access_token
        except httpx.RequestError as e:
            error_msg = await _format_oauth_request_error(
                "Service Account failed to retrieve token", token_url, e
            )
            log.error(error_msg)
            raise TokenError(error_msg)
        except Exception as e:
            error_msg = f"Service Account failed to retrieve token: {str(e)}"
            log.error(error_msg)
            raise TokenError(error_msg)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], scopes: List[str] = None) -> "ServiceAccount":
        return cls(
            email=data["client_email"],
            private_key=data["private_key"],
            project_id=data.get("project_id"),
            scopes=scopes,
        )


async def get_user_info(credentials: Credentials) -> Optional[Dict[str, Any]]:
    await credentials.refresh_if_needed()
    try:
        googleapis_base_url = normalize_google_oauth_base_url(
            await get_googleapis_proxy_url(), setting_name="google_apis_url"
        )
        userinfo_url = f"{googleapis_base_url.rstrip('/')}/oauth2/v2/userinfo"
        response = await get_async(
            userinfo_url,
            headers={"Authorization": f"Bearer {credentials.access_token}"},
            follow_redirects=False,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        log.error(f"Failed to retrieve user information: {e}")
        return None


async def get_user_email(credentials: Credentials) -> Optional[str]:
    try:
        await credentials.refresh_if_needed()
        user_info = await get_user_info(credentials)
        if user_info:
            email = user_info.get("email")
            if email:
                log.info(f"Retrieved email address: {email}.")
                return email
            else:
                log.warning(f"No email information found in userinfo response: {user_info}")
                return None
        else:
            log.warning("Failed to retrieve user information")
            return None
    except Exception as e:
        log.error(f"Failed to retrieve user email: {e}")
        return None


async def fetch_user_email_from_file(cred_data: Dict[str, Any]) -> Optional[str]:
    try:
        credentials = Credentials.from_dict(cred_data)
        if not credentials or not credentials.access_token:
            log.warning(
                "Unable to create credential object or retrieve access token from credential data"
            )
            return None
        return await get_user_email(credentials)
    except Exception as e:
        log.error(f"Failed to get user email from credential data: {e}")
        return None


async def validate_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        oauth_base_url = normalize_google_oauth_base_url(
            await get_oauth_proxy_url(), setting_name="oauth_url"
        )
        tokeninfo_url = f"{oauth_base_url.rstrip('/')}/tokeninfo?access_token={token}"
        response = await get_async(tokeninfo_url, follow_redirects=False)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        log.error(f"Token verification failed: {e}")
        return None


async def enable_required_apis(credentials: Credentials, project_id: str) -> bool:
    try:
        if credentials.is_expired() and credentials.refresh_token:
            await credentials.refresh()
        headers = {
            "Authorization": f"Bearer {credentials.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "code_assist-oauth/1.0",
        }
        required_services = ["geminicloudassist.googleapis.com", "cloudaicompanion.googleapis.com"]
        for service in required_services:
            log.info(f"Checking API service: {service}")
            service_usage_base_url = normalize_google_api_base_url(
                await get_service_usage_api_url(), setting_name="service_usage_url"
            )
            check_url = (
                f"{service_usage_base_url.rstrip('/')}/v1/projects/{project_id}/services/{service}"
            )
            try:
                check_response = await get_async(check_url, headers=headers, follow_redirects=False)
                if check_response.status_code == 200:
                    service_data = check_response.json()
                    if service_data.get("state") == "ENABLED":
                        log.info(f"Service {service} is already enabled.")
                        continue
            except Exception as e:
                log.debug(f"Failed to check service status. Attempting to enable it now: {e}")
            enable_url = f"{service_usage_base_url.rstrip('/')}/v1/projects/{project_id}/services/{service}:enable"
            try:
                enable_response = await post_async(
                    enable_url, headers=headers, json={}, follow_redirects=False
                )
                if enable_response.status_code in [200, 201]:
                    log.info(f"Service {service} enabled.")
                elif enable_response.status_code == 400:
                    error_data = enable_response.json()
                    if "already enabled" in error_data.get("error", {}).get("message", "").lower():
                        log.info(f"Service {service} is already enabled.")
                    else:
                        log.warning(f"Failed to enable service {service}: {error_data}")
                else:
                    log.warning(
                        f"Failed to enable service {service}: HTTP {enable_response.status_code}"
                    )
            except Exception as e:
                log.warning(f"Failed to enable service {service}: {e}")
        return True
    except Exception as e:
        log.error(f"Error while enabling API services: {e}")
        return False


async def get_user_projects(credentials: Credentials) -> List[Dict[str, Any]]:
    try:
        if credentials.is_expired() and credentials.refresh_token:
            await credentials.refresh()
        headers = {
            "Authorization": f"Bearer {credentials.access_token}",
            "User-Agent": "code_assist-oauth/1.0",
        }
        resource_manager_base_url = normalize_google_api_base_url(
            await get_resource_manager_api_url(), setting_name="resource_manager_url"
        )
        url = f"{resource_manager_base_url.rstrip('/')}/v1/projects"
        log.info(f"Calling API: {url}")
        response = await get_async(url, headers=headers, follow_redirects=False)
        log.info(f"API response status code: {response.status_code}")
        if response.status_code != 200:
            log.error(f"API response content: {response.text}")
        if response.status_code == 200:
            data = response.json()
            projects = data.get("projects", [])
            active_projects = [
                project for project in projects if project.get("lifecycleState") == "ACTIVE"
            ]
            log.info(f"Retrieved {len(active_projects)} active projects.")
            return active_projects
        else:
            log.warning(
                f"Failed to retrieve project list: {response.status_code} - {response.text}"
            )
            return []
    except Exception as e:
        log.error(f"Failed to retrieve user project list: {e}")
        return []


async def select_default_project(projects: List[Dict[str, Any]]) -> Optional[str]:
    if not projects:
        return None
    for project in projects:
        display_name = project.get("displayName", "").lower()
        project_id = project.get("projectId", "")
        if "default" in display_name or "default" in project_id.lower():
            log.info(
                f"Selecting default project: {project_id} ({project.get('displayName', project_id)})"
            )
            return project_id
    first_project = projects[0]
    project_id = first_project.get("projectId", "")
    log.info(
        f"Selecting first project as default: {project_id} ({first_project.get('displayName', project_id)})"
    )
    return project_id


async def fetch_project_id_and_tier(
    access_token: str, user_agent: str, api_base_url: str, include_credits: bool = False
) -> Tuple[Optional[str], Optional[str]] | Tuple[Optional[str], Optional[str], Optional[int]]:
    headers = {
        "User-Agent": user_agent,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept-Encoding": "gzip",
    }

    def _map_raw_tier(raw_tier: Optional[str]) -> Optional[str]:
        if not raw_tier:
            return None
        tier_mapping = {
            "g1-ultra-tier": "ultra",
            "ws-ai-ultra-business-tier": "ultra",
            "g1-pro-tier": "pro",
            "helium-tier": "pro",
            "standard-tier": "pro",
            "free-tier": "free",
        }
        return tier_mapping.get(raw_tier.lower(), "pro")

    subscription_tier = None
    credit_amount: Optional[int] = None
    try:
        project_id, raw_tier, raw_credit_amount = await _try_load_code_assist(api_base_url, headers)
        subscription_tier = _map_raw_tier(raw_tier)
        if raw_credit_amount is not None:
            try:
                credit_amount = int(raw_credit_amount)
                log.info(f"[fetch_project_id_and_tier] Found credit_amount: {credit_amount}")
            except (TypeError, ValueError):
                log.warning(
                    f"[fetch_project_id_and_tier] Invalid credit_amount: {raw_credit_amount}"
                )
        if raw_tier:
            log.info(
                f"[fetch_project_id_and_tier] Raw tier '{raw_tier}' mapped to '{subscription_tier}'"
            )
        if project_id:
            if include_credits:
                return (project_id, subscription_tier, credit_amount)
            return (project_id, subscription_tier)
        log.warning(
            "[fetch_project_id_and_tier] loadCodeAssist did not return a Project ID; falling back to onboardUser."
        )
    except Exception as e:
        log.warning(f"[fetch_project_id_and_tier] loadCodeAssist failed: {type(e).__name__}: {e}")
        log.warning("[fetch_project_id_and_tier] Falling back to onboardUser")
    try:
        project_id = await _try_onboard_user(api_base_url, headers)
        if project_id:
            if include_credits:
                return (project_id, subscription_tier, credit_amount)
            return (project_id, subscription_tier)
        log.error(
            "[fetch_project_id_and_tier] Failed to get a Project ID from both loadCodeAssist and onboardUser."
        )
        if include_credits:
            return (None, subscription_tier, credit_amount)
        return (None, subscription_tier)
    except Exception as e:
        log.error(f"[fetch_project_id_and_tier] onboardUser failed: {type(e).__name__}: {e}")
        import traceback

        log.debug(f"[fetch_project_id_and_tier] Traceback: {traceback.format_exc()}")
        if include_credits:
            return (None, subscription_tier, credit_amount)
        return (None, subscription_tier)


async def _try_load_code_assist(
    api_base_url: str, headers: dict
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    request_url = f"{api_base_url.rstrip('/')}/v1internal:loadCodeAssist"
    request_body = {"metadata": {"ideType": "ANTIGRAVITY"}}
    log.debug(f"[loadCodeAssist] Fetching Project ID from: {request_url}")
    log.debug(f"[loadCodeAssist] Request body: {request_body}")
    response = await post_async(request_url, json=request_body, headers=headers, timeout=30.0)
    log.debug(f"[loadCodeAssist] Response status: {response.status_code}")
    if response.status_code == 200:
        response_text = response.text
        log.debug(f"[loadCodeAssist] Response body: {response_text}")
        data = response.json()
        log.debug(f"[loadCodeAssist] Response JSON keys: {list(data.keys())}")
        paid_tier = data.get("paidTier", {})
        current_tier = data.get("currentTier", {})
        available_credits = (
            paid_tier.get("availableCredits", []) if isinstance(paid_tier, dict) else []
        )
        subscription_tier = None
        if isinstance(paid_tier, dict) and paid_tier.get("id"):
            subscription_tier = paid_tier.get("id")
            log.info(f"[loadCodeAssist] Found paidTier: {subscription_tier}")
        elif isinstance(current_tier, dict) and current_tier.get("id"):
            subscription_tier = current_tier.get("id")
            log.info(f"[loadCodeAssist] Found currentTier: {subscription_tier}")
        credit_amount = None
        if isinstance(available_credits, list) and available_credits:
            first_credit = available_credits[0]
            if isinstance(first_credit, dict):
                credit_amount = first_credit.get("creditAmount")
                if credit_amount is not None:
                    log.info(f"[loadCodeAssist] Found creditAmount: {credit_amount}")
        if current_tier:
            log.info("[loadCodeAssist] User is already activated")
            project_id = data.get("cloudaicompanionProject")
            if project_id:
                log.info(
                    f"[loadCodeAssist] Fetched Project ID: {project_id}; tier: {subscription_tier}."
                )
                return (project_id, subscription_tier, credit_amount)
            log.warning("[loadCodeAssist] No Project ID found in response.")
            return (None, subscription_tier, credit_amount)
        else:
            log.info("[loadCodeAssist] User not activated yet (no currentTier)")
            return (None, None, credit_amount)
    else:
        log.warning(f"[loadCodeAssist] Failed: HTTP {response.status_code}")
        log.warning(f"[loadCodeAssist] Response body: {response.text[:500]}")
        raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")


async def _try_onboard_user(api_base_url: str, headers: dict) -> Optional[str]:
    request_url = f"{api_base_url.rstrip('/')}/v1internal:onboardUser"
    tier_id = await _get_onboard_tier(api_base_url, headers)
    if not tier_id:
        log.error("[onboardUser] Failed to determine user tier")
        return None
    log.info(f"[onboardUser] User tier: {tier_id}")
    request_body = {
        "tierId": tier_id,
        "metadata": {
            "ideType": "ANTIGRAVITY",
            "platform": "PLATFORM_UNSPECIFIED",
            "pluginType": "GEMINI",
        },
    }
    log.debug(f"[onboardUser] Request URL: {request_url}")
    log.debug(f"[onboardUser] Request body: {request_body}")
    max_attempts = 5
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        log.debug(f"[onboardUser] Polling attempt {attempt}/{max_attempts}")
        response = await post_async(request_url, json=request_body, headers=headers, timeout=30.0)
        log.debug(f"[onboardUser] Response status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            log.debug(f"[onboardUser] Response data: {data}")
            if data.get("done"):
                log.info("[onboardUser] Operation completed")
                response_data = data.get("response", {})
                project_obj = response_data.get("cloudaicompanionProject", {})
                if isinstance(project_obj, dict):
                    project_id = project_obj.get("id")
                elif isinstance(project_obj, str):
                    project_id = project_obj
                else:
                    project_id = None
                if project_id:
                    log.info(f"[onboardUser] Fetched Project ID: {project_id}.")
                    return project_id
                else:
                    log.warning(
                        "[onboardUser] Operation completed, but no Project ID was returned."
                    )
                    return None
            else:
                log.debug("[onboardUser] Operation still in progress, waiting 2 seconds...")
                await asyncio.sleep(2)
        else:
            log.warning(f"[onboardUser] Failed: HTTP {response.status_code}")
            log.warning(f"[onboardUser] Response body: {response.text[:500]}")
            raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
    log.error("[onboardUser] Timeout: Operation did not complete within 10 seconds")
    return None


async def _get_onboard_tier(api_base_url: str, headers: dict) -> Optional[str]:
    request_url = f"{api_base_url.rstrip('/')}/v1internal:loadCodeAssist"
    request_body = {
        "metadata": {
            "ideType": "ANTIGRAVITY",
            "platform": "PLATFORM_UNSPECIFIED",
            "pluginType": "GEMINI",
        }
    }
    log.debug(f"[_get_onboard_tier] Fetching tier info from: {request_url}")
    response = await post_async(request_url, json=request_body, headers=headers, timeout=30.0)
    if response.status_code == 200:
        data = response.json()
        log.debug(f"[_get_onboard_tier] Response data: {data}")
        allowed_tiers = data.get("allowedTiers", [])
        for tier in allowed_tiers:
            if tier.get("isDefault"):
                tier_id = tier.get("id")
                log.info(f"[_get_onboard_tier] Found default tier: {tier_id}")
                return tier_id
        log.warning("[_get_onboard_tier] No default tier found, using LEGACY")
        return "LEGACY"
    else:
        log.error(f"[_get_onboard_tier] Failed to fetch tier info: HTTP {response.status_code}")
        return None
