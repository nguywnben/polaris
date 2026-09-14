import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from config import get_routing_policy
from core.credential_pool import upsert_credential_by_email
from core.google_oauth_api import Credentials, merge_refreshed_credential_data
from core.model_blacklist import (
    get_credential_model_blacklist_pairs,
    get_model_blacklist_pairs,
)
from core.provider_registry import (
    ANTHROPIC,
    CLAUDE_CODE,
    CODEX,
    OLLAMA,
    OPENAI,
    XAI,
    get_credential_provider,
    get_credential_provider_variant,
    is_api_key_credential,
)
from core.routing_coordination import RoutingCoordinationAdapter
from core.routing_decision import RouteDecision
from core.smart_routing import SmartCredentialRouter
from core.storage_adapter import get_storage_adapter
from core.usage_stats import retire_credential_usage
from log import log

SUCCESS_HINT_FLUSH_INTERVAL_SECONDS = 5.0


class CredentialManager:
    def __init__(self, *, routing_coordination: Optional[RoutingCoordinationAdapter] = None):

        self._initialized = False
        self._storage_adapter = None
        self._routing = SmartCredentialRouter(coordination=routing_coordination)
        self._success_hint_lock = asyncio.Lock()
        self._success_hint_pending: Dict[Tuple[str, str, str], int] = {}
        self._success_hint_last_flush: Dict[Tuple[str, str, str], float] = {}

    async def _ensure_initialized(self):
        if not self._initialized or self._storage_adapter is None:
            await self.initialize()

    async def initialize(self):
        if self._initialized and self._storage_adapter is not None:
            return

        self._storage_adapter = await get_storage_adapter()
        self._initialized = True

    async def close(self):
        log.debug("Closing credential manager.")
        await self._flush_success_hints()
        await self._routing.reset()
        self._initialized = False
        log.debug("Credential manager closed")

    async def _record_success_hint(
        self,
        credential_name: str,
        *,
        mode: str,
        model_name: Optional[str],
    ) -> None:
        key = (mode, credential_name, str(model_name or ""))
        now = time.monotonic()
        async with self._success_hint_lock:
            pending = self._success_hint_pending.get(key, 0) + 1
            last_flush = self._success_hint_last_flush.get(key)
            if last_flush is not None and now - last_flush < SUCCESS_HINT_FLUSH_INTERVAL_SECONDS:
                self._success_hint_pending[key] = pending
                return
            self._success_hint_pending.pop(key, None)
            self._success_hint_last_flush[key] = now
        await self._storage_adapter._backend.record_success(
            credential_name,
            model_name=model_name,
            mode=mode,
            call_increment=pending,
        )

    async def _flush_success_hints(self) -> None:
        async with self._success_hint_lock:
            pending = tuple(self._success_hint_pending.items())
            self._success_hint_pending.clear()
        if self._storage_adapter is None:
            return
        for (mode, credential_name, model_name), call_increment in pending:
            await self._storage_adapter._backend.record_success(
                credential_name,
                model_name=model_name or None,
                mode=mode,
                call_increment=call_increment,
            )

    async def get_valid_credential(
        self,
        mode: str = "code_assist",
        model_name: Optional[str] = None,
        provider_id: Optional[str] = None,
        excluded_provider_models: Optional[Set[Tuple[str, str]]] = None,
        excluded_credential_models: Optional[Set[Tuple[str, str]]] = None,
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        await self._ensure_initialized()

        max_retries = 3
        for attempt in range(max_retries):
            routing_policy = (
                await get_routing_policy()
                if mode == "primary" and provider_id is None
                else {"strategy": "balanced", "preferred_provider": ""}
            )
            result = await self._routing.acquire(
                self._storage_adapter,
                mode=mode,
                model_name=model_name,
                provider_id=provider_id,
                routing_strategy=routing_policy["strategy"],
                preferred_provider=routing_policy["preferred_provider"],
                excluded_provider_models=excluded_provider_models,
                excluded_credential_models=excluded_credential_models,
            )

            if not result:
                if attempt == 0:
                    log.warning(f"No available credentials (mode={mode}, model_name={model_name})")
                return None

            filename, credential_data = result

            if await self._should_refresh_token(credential_data):
                log.debug(f"Token needs to be refreshed - File: {filename} (mode = {mode})")
                refreshed_data = await self._refresh_token(credential_data, filename, mode=mode)
                if refreshed_data:
                    credential_data = refreshed_data
                    log.debug(f"Token refreshed: {filename} (mode = {mode}).")
                    return filename, credential_data
                else:
                    log.warning(
                        f"Token refresh failed, attempt to get next credentials: {filename} (mode = {mode}, attempt = {attempt + 1}/{max_retries})"
                    )
                    await self._routing.complete(filename, mode=mode, success=False)
                    continue
            else:
                return filename, credential_data

        log.error(
            f"No available credentials after {max_retries} retries (mode={mode}, model_name={model_name})"
        )
        return None

    async def get_valid_model_credential(
        self,
        model_names,
        *,
        mode: str = "primary",
        respect_model_blacklist: bool = False,
        excluded_provider_models: Optional[Set[Tuple[str, str]]] = None,
        excluded_credential_models: Optional[Set[Tuple[str, str]]] = None,
    ) -> Optional[Tuple[str, str, Dict[str, Any]]]:
        """Return the first routable model and credential in priority order."""
        route_exclusions = set(excluded_provider_models or ())
        credential_route_exclusions = set(excluded_credential_models or ())
        if respect_model_blacklist:
            route_exclusions.update(await get_model_blacklist_pairs())
            credential_route_exclusions.update(await get_credential_model_blacklist_pairs())
        seen = set()
        for value in model_names or ():
            model_name = str(value or "").strip()
            if not model_name or model_name in seen:
                continue
            seen.add(model_name)
            credential = await self.get_valid_credential(
                mode=mode,
                model_name=model_name,
                excluded_provider_models=route_exclusions,
                excluded_credential_models=credential_route_exclusions,
            )
            if credential:
                filename, credential_data = credential
                return model_name, filename, credential_data
        return None

    async def get_unified_mode_and_credential(
        self, model_name: Optional[str] = None
    ) -> Optional[Tuple[str, str, Dict[str, Any]]]:
        """
        Get unified credential and its mode ("primary").
        Returns (mode, filename, credential_data)
        """
        await self._ensure_initialized()

        anti_res = await self.get_valid_credential(mode="primary", model_name=model_name)
        if not anti_res:
            log.warning("No active provider credentials found")
            return None

        filename, credential_data = anti_res
        selected_mode = "primary"

        return selected_mode, filename, credential_data

    async def add_credential(self, credential_name: str, credential_data: Dict[str, Any]):
        await self._ensure_initialized()
        result = await upsert_credential_by_email(credential_name, credential_data)
        log.info(f"Credential pool write result: {result.get('action')} ({result.get('filename')})")
        return result

    async def add_primary_credential(self, credential_name: str, credential_data: Dict[str, Any]):
        await self._ensure_initialized()
        result = await upsert_credential_by_email(credential_name, credential_data, mode="primary")
        log.info(
            f"Provider credential pool write result: {result.get('action')} ({result.get('filename')})"
        )
        return result

    async def remove_credential(self, credential_name: str, mode: str = "code_assist") -> bool:
        """Delete a credential and detach its retained usage history."""
        await self._ensure_initialized()
        try:
            credential_data = await self._storage_adapter.get_credential(
                credential_name,
                mode=mode,
            )
            if not credential_data:
                log.warning(
                    f"Credential removal skipped because it no longer exists (mode={mode})."
                )
                return False

            provider_id = get_credential_provider(credential_data)
            deleted = await self._storage_adapter.delete_credential(
                credential_name,
                mode=mode,
            )
            if not deleted:
                log.error(
                    f"Credential storage deletion failed (mode={mode}, provider={provider_id})."
                )
                return False

            await retire_credential_usage(
                credential_name,
                provider_id,
                credential_type=credential_data.get("credential_type", ""),
            )
            log.info(f"Credential removed (mode={mode}, provider={provider_id}).")
            return True
        except Exception as e:
            log.error(f"Credential removal failed (mode={mode}): {e}")
            return False

    async def release_credential(self, credential_name: str, mode: str = "code_assist") -> None:
        """Release a routing reservation for a non-inference operation."""
        await self._routing.release(credential_name, mode=mode)

    async def get_recent_routing_decisions(self, limit: int = 20) -> tuple[RouteDecision, ...]:
        """Return secret-free recent routing decisions for management diagnostics."""
        await self._ensure_initialized()
        return await self._routing.recent_decisions(limit=limit)

    async def set_model_cooldown(
        self,
        credential_name: str,
        model_name: str,
        cooldown_until: float,
        *,
        mode: str = "primary",
    ) -> bool:
        """Temporarily exclude one credential from one model route."""
        await self._ensure_initialized()
        backend = self._storage_adapter._backend
        if not hasattr(backend, "set_model_cooldown"):
            return False
        updated = await backend.set_model_cooldown(
            credential_name,
            model_name,
            cooldown_until,
            mode=mode,
        )
        return bool(updated)

    async def update_credential_state(
        self, credential_name: str, state_updates: Dict[str, Any], mode: str = "code_assist"
    ):
        log.debug(
            f"[CredMgr] update_credential_state Start: credential_name = {credential_name}, state_updates = {state_updates}, mode = {mode}"
        )
        log.debug("[credential-manager] Ensuring storage is initialized.")
        await self._ensure_initialized()
        log.debug("[CredMgr]_ensure_initialized Done")
        try:
            log.debug("[credential-manager] Updating credential state in storage.")
            success = await self._storage_adapter.update_credential_state(
                credential_name, state_updates, mode=mode
            )
            log.debug(f"[CredMgr] storage_adapter.update_credential_state returned: {success}")
            if success:
                log.debug(f"Updated credential state: {credential_name} (mode={mode})")
            else:
                log.warning(f"Failed to update credential state: {credential_name} (mode={mode})")
            return success
        except Exception as e:
            log.error(f"Error updating credential state {credential_name}: {e}")
            return False

    async def set_cred_disabled(
        self, credential_name: str, disabled: bool, mode: str = "code_assist"
    ):
        try:
            log.info(
                f"[CredMgr] set_cred_disabled Start: credential_name = {credential_name}, disabled = {disabled}, mode = {mode}"
            )
            success = await self.update_credential_state(
                credential_name, {"disabled": disabled}, mode=mode
            )
            log.info(f"[CredMgr] update_credential_state returned: success = {success}")
            if success:
                action = "disabled" if disabled else "enabled"
                log.info(f"Credential {action}: {credential_name} (mode={mode})")
            else:
                log.warning(
                    f"[CredMgr] Failed to set disable status: credential_name = {credential_name}, disabled = {disabled}"
                )
            return success
        except Exception as e:
            log.error(f"Error setting credential disabled state {credential_name}: {e}")
            return False

    async def get_creds_status(self) -> Dict[str, Dict[str, Any]]:
        await self._ensure_initialized()
        try:
            return await self._storage_adapter.get_all_credential_states()
        except Exception as e:
            log.error(f"Error getting credential statuses: {e}")
            return {}

    async def get_creds_summary(self) -> List[Dict[str, Any]]:
        await self._ensure_initialized()
        try:
            return await self._storage_adapter._backend.get_credentials_summary()
        except Exception as e:
            log.error(f"Error getting credentials summary: {e}")
            return []

    async def get_or_fetch_user_email(
        self, credential_name: str, mode: str = "code_assist"
    ) -> Optional[str]:
        try:
            await self._ensure_initialized()

            state = await self._storage_adapter.get_credential_state(credential_name, mode=mode)
            cached_email = state.get("user_email") if state else None

            if cached_email:
                return cached_email

            credential_data = await self._storage_adapter.get_credential(credential_name, mode=mode)
            if not credential_data:
                return None

            from .google_oauth_api import Credentials, get_user_email

            credentials = Credentials.from_dict(credential_data)
            if not credentials:
                return None

            token_refreshed = await credentials.refresh_if_needed()

            if token_refreshed:
                log.info(f"Token automatically refreshed: {credential_name} (mode = {mode})")
                updated_data = merge_refreshed_credential_data(credential_data, credentials)
                await self._storage_adapter.store_credential(
                    credential_name, updated_data, mode=mode
                )

            email = await get_user_email(credentials)

            if email:
                await self._storage_adapter.update_credential_state(
                    credential_name, {"user_email": email}, mode=mode
                )
                return email

            return None

        except Exception as e:
            log.error(f"Error fetching user email for {credential_name}: {e}")
            return None

    async def record_api_call_result(
        self,
        credential_name: str,
        success: bool,
        error_code: Optional[int] = None,
        cooldown_until: Optional[float] = None,
        mode: str = "code_assist",
        model_name: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        await self._ensure_initialized()
        try:
            if success:
                # Exact request accounting is committed to the durable usage
                # ledger before the response completes. Credential success fields
                # are routing/UI hints, so coalesce their exact counter increments
                # into a bounded write cadence instead of writing every request.
                await self._record_success_hint(
                    credential_name,
                    mode=mode,
                    model_name=model_name,
                )

            elif error_code:
                error_messages = {}
                if error_message:
                    error_messages[str(error_code)] = error_message

                state_updates = {
                    "error_codes": [error_code],
                    "error_messages": error_messages,
                }

                await self.update_credential_state(credential_name, state_updates, mode=mode)

                if hasattr(self._storage_adapter._backend, "record_failure"):
                    await self._storage_adapter._backend.record_failure(credential_name, mode=mode)

                if cooldown_until is not None and model_name:
                    if hasattr(self._storage_adapter._backend, "set_model_cooldown"):
                        await self._storage_adapter._backend.set_model_cooldown(
                            credential_name, model_name, cooldown_until, mode=mode
                        )
                        log.info(
                            f"Setting model-level cooldown: {credential_name}, model_name={model_name}, "
                            f"cooldown_until: {datetime.fromtimestamp(cooldown_until, timezone.utc).isoformat()}"
                        )

        except Exception as e:
            log.error(f"Error recording API call result for {credential_name}: {e}")
        finally:
            await self._routing.complete(
                credential_name,
                mode=mode,
                success=success,
                cooldown_until=cooldown_until,
                model_name=model_name,
                error_code=error_code,
            )

    async def prepare_credential(
        self,
        filename: str,
        credential_data: Dict[str, Any],
        *,
        mode: str = "primary",
    ) -> Optional[Dict[str, Any]]:
        """Refresh one stored credential when needed without acquiring a routing lease."""
        await self._ensure_initialized()
        if await self._should_refresh_token(credential_data):
            return await self._refresh_token(credential_data, filename, mode=mode)
        return credential_data

    async def _should_refresh_token(self, credential_data: Dict[str, Any]) -> bool:
        try:
            if is_api_key_credential(credential_data):
                return False
            if get_credential_provider(credential_data) == OLLAMA:
                return False

            if not credential_data.get("access_token") and not credential_data.get("token"):
                log.debug("No access_token found, refresh required")
                return True

            expiry_str = credential_data.get("expiry")
            if not expiry_str:
                log.debug("No expiration time found, refresh required")
                return True

            try:
                if isinstance(expiry_str, str):
                    if "+" in expiry_str:
                        file_expiry = datetime.fromisoformat(expiry_str)
                    elif expiry_str.endswith("Z"):
                        file_expiry = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
                    else:
                        file_expiry = datetime.fromisoformat(expiry_str)
                else:
                    log.debug("Invalid expiration time format, refresh required")
                    return True

                if file_expiry.tzinfo is None:
                    file_expiry = file_expiry.replace(tzinfo=timezone.utc)

                now = datetime.now(timezone.utc)
                time_left = (file_expiry - now).total_seconds()

                log.debug(
                    f"Token time check: "
                    f"current UTC time={now.isoformat()}, "
                    f"expiry={file_expiry.isoformat()}, "
                    f"time left={int(time_left / 60)}m {int(time_left % 60)}s"
                )

                if time_left > 300:
                    return False
                else:
                    log.debug(
                        f"Token is about to expire in {int(time_left / 60)} minutes and needs a refresh."
                    )
                    return True

            except Exception as e:
                log.warning(f"Failed to parse expiration time: {e}, refresh required")
                return True

        except Exception as e:
            log.error(f"Error occurred while checking token expiration: {e}")
            return True

    async def _refresh_token(
        self, credential_data: Dict[str, Any], filename: str, mode: str = "code_assist"
    ) -> Optional[Dict[str, Any]]:
        await self._ensure_initialized()
        try:
            provider_id = get_credential_provider(credential_data)
            if provider_id == XAI:
                from core.xai import refresh_xai_oauth_credential

                refreshed_data = await refresh_xai_oauth_credential(credential_data)
                await self._storage_adapter.store_credential(filename, refreshed_data, mode=mode)
                log.info(f"Grok Build token refreshed and saved: {filename} (mode={mode}).")
                return refreshed_data

            if provider_id == OPENAI and get_credential_provider_variant(credential_data) == CODEX:
                from core.codex import refresh_codex_oauth_credential

                refreshed_data = await refresh_codex_oauth_credential(credential_data)
                await self._storage_adapter.store_credential(filename, refreshed_data, mode=mode)
                log.info(f"Codex token refreshed and saved: {filename} (mode={mode}).")
                return refreshed_data

            if (
                provider_id == ANTHROPIC
                and get_credential_provider_variant(credential_data) == CLAUDE_CODE
            ):
                from core.anthropic import refresh_claude_oauth_credential

                refreshed_data = await refresh_claude_oauth_credential(credential_data)
                await self._storage_adapter.store_credential(filename, refreshed_data, mode=mode)
                log.info(f"Claude Code token refreshed and saved: {filename} (mode={mode}).")
                return refreshed_data

            creds = Credentials.from_dict(credential_data)

            if not creds.refresh_token:
                log.error(f"No refresh_token found, unable to refresh: {filename} (mode={mode})")

                try:
                    await self.update_credential_state(filename, {"disabled": True}, mode=mode)
                    log.warning(
                        f"Credential automatically disabled (missing refresh_token): {filename}"
                    )
                except Exception as e:
                    log.error(f"Failed to disable credential {filename}: {e}")
                return None

            log.debug(f"Refreshing token: {filename} (mode={mode})")
            await creds.refresh()

            credential_data = merge_refreshed_credential_data(credential_data, creds)

            await self._storage_adapter.store_credential(filename, credential_data, mode=mode)
            log.info(f"Token refreshed and saved: {filename} (mode = {mode}).")

            return credential_data

        except Exception as e:
            error_msg = str(e)
            log.error(f"Token refresh failed {filename} (mode = {mode}): {error_msg}")

            status_code = None
            if hasattr(e, "status_code"):
                status_code = e.status_code

            is_permanent_failure = self._is_permanent_refresh_failure(error_msg, status_code)

            if is_permanent_failure:
                log.warning(
                    f"Permanent credential failure detected (HTTP {status_code}): {filename}"
                )

                refresh_error_code = status_code or 400
                await self.update_credential_state(
                    filename,
                    {
                        "error_codes": [refresh_error_code],
                        "error_messages": {str(refresh_error_code): error_msg},
                    },
                    mode=mode,
                )
                if hasattr(self._storage_adapter._backend, "record_failure"):
                    await self._storage_adapter._backend.record_failure(filename, mode=mode)

                try:
                    disabled_ok = await self.update_credential_state(
                        filename, {"disabled": True}, mode=mode
                    )
                    if disabled_ok:
                        log.warning(f"Permanently failed credential disabled: {filename}")
                    else:
                        log.warning(
                            "Failed to disable permanently failed credential, handling will be deferred to higher-level logic"
                        )
                except Exception as e2:
                    log.error(
                        f"Error occurred while disabling permanently failed credential {filename}: {e2}"
                    )
            else:
                log.warning(
                    f"Token refresh failed but not a permanent error (http {status_code}), do not ban credentials: {filename}"
                )

            return None

    def _is_permanent_refresh_failure(
        self, error_msg: str, status_code: Optional[int] = None
    ) -> bool:

        if status_code is not None:
            if status_code in [400, 401, 403]:
                log.debug(
                    f"Client error status code {status_code} detected, classifying as a permanent failure"
                )
                return True

            elif status_code in [500, 502, 503, 504]:
                log.debug(
                    f"Server error status code {status_code} detected, should not ban credential"
                )
                return False

            elif status_code == 429:
                log.debug("Rate limit error 429 detected, should not ban credential")
                return False

        permanent_error_patterns = [
            "invalid_grant",
            "refresh_token_expired",
            "invalid_refresh_token",
            "unauthorized_client",
            "access_denied",
        ]

        error_msg_lower = error_msg.lower()
        for pattern in permanent_error_patterns:
            if pattern.lower() in error_msg_lower:
                log.debug(f"Error message matches permanent failure pattern: {pattern}")
                return True

        log.debug("No explicit permanent failure pattern matched; classifying as a transient error")
        return False


class _CredentialManagerSingleton:
    def __init__(self):
        self._instance: Optional[CredentialManager] = None
        self._lock = asyncio.Lock()
        self._routing_coordination: Optional[RoutingCoordinationAdapter] = None

    async def configure_routing_coordination(
        self,
        coordination: Optional[RoutingCoordinationAdapter],
    ) -> None:
        """Bind the lifecycle-owned adapter before the singleton initializes."""

        async with self._lock:
            if self._instance is not None:
                raise RuntimeError("Credential manager is already initialized.")
            self._routing_coordination = coordination

    async def _get_or_create(self) -> CredentialManager:
        if self._instance is None:
            async with self._lock:
                if self._instance is None:
                    manager = (
                        CredentialManager(routing_coordination=self._routing_coordination)
                        if self._routing_coordination is not None
                        else CredentialManager()
                    )
                    await manager.initialize()
                    self._instance = manager
                    log.debug("CredentialManager singleton initialized")

        return self._instance

    async def close(self) -> None:
        """Close and clear the process-local manager instance."""
        async with self._lock:
            if self._instance is not None:
                await self._instance.close()
                self._instance = None
            self._routing_coordination = None

    def __getattr__(self, name):
        async def _async_wrapper(*args, **kwargs):
            manager = await self._get_or_create()
            method = getattr(manager, name)
            return await method(*args, **kwargs)

        return _async_wrapper


credential_manager = _CredentialManagerSingleton()
