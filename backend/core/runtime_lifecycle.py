"""Single ownership boundary for process-local runtime coordination."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from core.coordination_service import CoordinationService
from core.credential_batch_coordination import (
    CredentialBatchCoordinationService,
    configure_credential_batch_coordination_service,
)
from core.credential_manager import credential_manager
from core.device_authorization_coordination import (
    DeviceAuthorizationService,
    configure_device_authorization_service,
)
from core.governance_coordination import configure_governance_coordination
from core.identity import configure_oidc_transaction_coordination
from core.panel.auth_support import (
    AuthenticationAttemptService,
    configure_authentication_attempt_service,
    reset_authentication_attempt_service,
)
from core.primary_session_coordination import (
    PrimarySessionCoordinator,
    configure_primary_session_coordinator,
)
from core.provider_authorization_coordination import (
    ProviderAuthorizationService,
    configure_provider_authorization_service,
)
from core.response_cache import reset_response_cache_coordination, response_cache_coordinator
from core.routing_coordination import RoutingCoordinationAdapter
from core.runtime_policy import RuntimePolicy
from core.state_store import InMemoryStateStore
from core.virtual_keys import virtual_key_manager

_ROUTING_KEY_DOMAIN = b"polaris:runtime-routing-identifiers:v1\0"
_ATTEMPT_KEY_DOMAIN = b"polaris:runtime-auth-attempt-identifiers:v1\0"
_PRIMARY_SESSION_KEY_DOMAIN = b"polaris:runtime-primary-session-identifiers:v1\0"
_PROVIDER_AUTHORIZATION_KEY_DOMAIN = b"polaris:runtime-provider-authorization-identifiers:v1\0"
_DEVICE_AUTHORIZATION_KEY_DOMAIN = b"polaris:runtime-device-authorization-identifiers:v1\0"
_CREDENTIAL_BATCH_KEY_DOMAIN = b"polaris:runtime-credential-batch-identifiers:v1\0"


class RuntimeState(StrEnum):
    STARTING = "starting"
    READY = "ready"
    UNAVAILABLE = "unavailable"
    CLOSED = "closed"


def _new_runtime_store() -> InMemoryStateStore:
    """Expose Unix-based timestamps without making TTLs follow wall-clock jumps.

    The store is process-local, so one epoch anchor covers its entire lifetime.
    Subsequent NTP/manual corrections do not revive or prematurely expire sessions.
    """
    monotonic_anchor = time.monotonic()
    epoch_anchor = time.time()
    return InMemoryStateStore(clock=lambda: epoch_anchor + (time.monotonic() - monotonic_anchor))


class RuntimeLifecycle:
    """Construct and inject one in-memory coordination service before request traffic."""

    def __init__(
        self,
        *,
        policy: RuntimePolicy | None = None,
        store_factory: Callable[[], Any] = _new_runtime_store,
    ) -> None:
        self.policy = policy or RuntimePolicy.from_environment()
        self.state = RuntimeState.STARTING
        self._store_factory = store_factory
        self._coordination_service: CoordinationService | None = None
        self._routing_coordination: RoutingCoordinationAdapter | None = None
        self._credential_manager_owner: Any | None = None
        self._failure_code = ""

    @property
    def coordination_service(self) -> CoordinationService | None:
        return self._coordination_service

    @property
    def session_initialization_kwargs(self) -> dict[str, object]:
        if self._coordination_service is None:
            raise RuntimeError("Runtime lifecycle is not initialized.")
        return {"coordination": self._coordination_service, "fencing_epoch": 1}

    @property
    def admission_available(self) -> bool:
        return self.state is RuntimeState.READY

    def health_snapshot(self) -> dict[str, object]:
        service = self._coordination_service
        return {
            "mode": self.policy.mode.value,
            "state": self.state.value,
            "ready": self.admission_available,
            "failure_code": self._failure_code,
            "coordination_available": bool(
                service is not None and service.health_snapshot()["available"]
            ),
        }

    async def start(self) -> None:
        if self._coordination_service is not None or self.state is not RuntimeState.STARTING:
            raise RuntimeError("Runtime lifecycle has already started.")
        raw_store: Any | None = None
        service: CoordinationService | None = None
        try:
            raw_store = self._store_factory()
            service = CoordinationService(raw_store)
            identifier_root = secrets.token_bytes(32)
            routing = RoutingCoordinationAdapter(
                service,
                identifier_key=hmac.digest(identifier_root, _ROUTING_KEY_DOMAIN, hashlib.sha256),
                fencing_epoch=1,
            )

            await credential_manager.configure_routing_coordination(routing)
            self._credential_manager_owner = credential_manager
            configure_governance_coordination(routing)
            configure_authentication_attempt_service(
                AuthenticationAttemptService(
                    service,
                    hmac_key=hmac.digest(identifier_root, _ATTEMPT_KEY_DOMAIN, hashlib.sha256),
                    fencing_epoch=1,
                )
            )
            configure_oidc_transaction_coordination(service, fencing_epoch=1)
            configure_provider_authorization_service(
                ProviderAuthorizationService(
                    service,
                    key=hmac.digest(
                        identifier_root,
                        _PROVIDER_AUTHORIZATION_KEY_DOMAIN,
                        hashlib.sha256,
                    ),
                    fencing_epoch=1,
                )
            )
            configure_device_authorization_service(
                DeviceAuthorizationService(
                    service,
                    key=hmac.digest(
                        identifier_root,
                        _DEVICE_AUTHORIZATION_KEY_DOMAIN,
                        hashlib.sha256,
                    ),
                    fencing_epoch=1,
                )
            )
            configure_credential_batch_coordination_service(
                CredentialBatchCoordinationService(
                    service,
                    key=hmac.digest(
                        identifier_root,
                        _CREDENTIAL_BATCH_KEY_DOMAIN,
                        hashlib.sha256,
                    ),
                    fencing_epoch=1,
                )
            )
            virtual_key_manager.configure_coordination(service, fencing_epoch=1)
            response_cache_coordinator.configure_coordination(routing)
            configure_primary_session_coordinator(
                PrimarySessionCoordinator(
                    service,
                    identifier_key=hmac.digest(
                        identifier_root,
                        _PRIMARY_SESSION_KEY_DOMAIN,
                        hashlib.sha256,
                    ),
                    fencing_epoch=1,
                )
            )

            self._coordination_service = service
            self._routing_coordination = routing
            self.state = RuntimeState.READY
        except Exception:
            self._failure_code = "initialization_failed"
            self.state = RuntimeState.UNAVAILABLE
            if self._credential_manager_owner is not None:
                await self._credential_manager_owner.configure_routing_coordination(None)
                self._credential_manager_owner = None
            configure_governance_coordination(None)
            reset_authentication_attempt_service()
            configure_oidc_transaction_coordination(None)
            configure_primary_session_coordinator(None)
            configure_provider_authorization_service(None)
            configure_device_authorization_service(None)
            configure_credential_batch_coordination_service(None)
            virtual_key_manager.reset_coordination()
            if service is not None:
                await service.close()
            elif raw_store is not None:
                await raw_store.close()
            reset_response_cache_coordination()
            raise

    async def check_ready(self) -> bool:
        if self.state in {RuntimeState.STARTING, RuntimeState.CLOSED}:
            return False
        service = self._coordination_service
        if service is None:
            return False
        try:
            await service.read_coordination_time(epoch=1)
        except Exception:
            self._failure_code = "dependency_unavailable"
            self.state = RuntimeState.UNAVAILABLE
            return False
        self._failure_code = ""
        self.state = RuntimeState.READY
        return True

    async def close(self) -> None:
        service = self._coordination_service
        if self._credential_manager_owner is not None:
            await self._credential_manager_owner.configure_routing_coordination(None)
            self._credential_manager_owner = None
        configure_governance_coordination(None)
        reset_authentication_attempt_service()
        configure_oidc_transaction_coordination(None)
        configure_primary_session_coordinator(None)
        configure_provider_authorization_service(None)
        configure_device_authorization_service(None)
        configure_credential_batch_coordination_service(None)
        virtual_key_manager.reset_coordination()
        self._coordination_service = None
        self._routing_coordination = None
        if service is not None:
            await service.close()
        reset_response_cache_coordination()
        self.state = RuntimeState.CLOSED


_runtime_lifecycle: RuntimeLifecycle | None = None


def get_runtime_lifecycle() -> RuntimeLifecycle | None:
    return _runtime_lifecycle


def set_runtime_lifecycle(lifecycle: RuntimeLifecycle | None) -> None:
    global _runtime_lifecycle
    _runtime_lifecycle = lifecycle


async def initialize_runtime() -> RuntimeLifecycle:
    global _runtime_lifecycle
    if _runtime_lifecycle is not None:
        return _runtime_lifecycle
    lifecycle = RuntimeLifecycle()
    await lifecycle.start()
    _runtime_lifecycle = lifecycle
    return lifecycle


def get_runtime_session_kwargs() -> dict[str, object]:
    lifecycle = _runtime_lifecycle
    if lifecycle is None:
        raise RuntimeError("Runtime lifecycle is not initialized.")
    return lifecycle.session_initialization_kwargs


async def close_runtime() -> None:
    global _runtime_lifecycle
    lifecycle = _runtime_lifecycle
    _runtime_lifecycle = None
    if lifecycle is not None:
        await lifecycle.close()


def render_runtime_metrics() -> str:
    lifecycle = _runtime_lifecycle
    snapshot = (
        lifecycle.health_snapshot()
        if lifecycle is not None
        else {
            "mode": "standalone",
            "state": RuntimeState.STARTING.value,
            "ready": False,
            "coordination_available": False,
        }
    )
    return (
        "# HELP polaris_runtime_ready Whether the process-local runtime lifecycle is ready.\n"
        "# TYPE polaris_runtime_ready gauge\n"
        f"polaris_runtime_ready {int(bool(snapshot['ready']))}\n"
        "# HELP polaris_runtime_coordination_available Whether process-local coordination is available.\n"
        "# TYPE polaris_runtime_coordination_available gauge\n"
        f"polaris_runtime_coordination_available {int(bool(snapshot['coordination_available']))}\n"
        "# HELP polaris_runtime_info Fixed runtime topology and lifecycle state.\n"
        "# TYPE polaris_runtime_info gauge\n"
        "polaris_runtime_info"
        f'{{mode="{snapshot["mode"]}",state="{snapshot["state"]}"}} 1\n'
    )
