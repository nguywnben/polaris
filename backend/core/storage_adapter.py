import asyncio
import json
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol

from core.credential_pool_mutation import CredentialPoolMutation, CredentialPoolPlanner
from log import log

if TYPE_CHECKING:
    from core.audit import AuditRepository
    from core.durable_migration_runner import MigrationCheckpointRepository
    from core.identity.repository import IdentityRepository
    from core.request_trace import RequestTraceRepository
    from core.usage_ledger import UsageLedgerRepository


class StorageBackend(Protocol):
    async def initialize(self) -> None: ...

    async def close(self) -> None: ...

    async def store_credential(
        self, filename: str, credential_data: Dict[str, Any], mode: str = "code_assist"
    ) -> bool: ...

    async def get_credential(
        self, filename: str, mode: str = "code_assist"
    ) -> Optional[Dict[str, Any]]: ...

    async def list_credentials(self, mode: str = "code_assist") -> List[str]: ...

    async def get_all_credentials(self, mode: str = "code_assist") -> Dict[str, Dict[str, Any]]: ...

    async def delete_credential(self, filename: str, mode: str = "code_assist") -> bool: ...

    async def update_credential_state(
        self, filename: str, state_updates: Dict[str, Any], mode: str = "code_assist"
    ) -> bool: ...

    async def get_credential_state(
        self, filename: str, mode: str = "code_assist"
    ) -> Dict[str, Any]: ...

    async def get_all_credential_states(
        self, mode: str = "code_assist"
    ) -> Dict[str, Dict[str, Any]]: ...

    async def mutate_credential_pool(
        self, mode: str, planner: CredentialPoolPlanner
    ) -> CredentialPoolMutation: ...

    async def record_success(
        self,
        filename: str,
        model_name: Optional[str] = None,
        mode: str = "code_assist",
        call_increment: int = 1,
    ) -> None:
        """Record a completed provider attempt."""
        ...

    async def record_failure(self, filename: str, mode: str = "code_assist") -> None:
        """Record a failed provider attempt for fair routing."""
        ...

    async def set_config(self, key: str, value: Any) -> bool: ...

    async def get_config(self, key: str, default: Any = None) -> Any: ...

    async def get_all_config(self) -> Dict[str, Any]: ...

    async def reload_config_cache(self) -> None: ...

    async def delete_config(self, key: str) -> bool: ...

    async def create_audit_repository(self, *, cursor_signing_key: bytes) -> "AuditRepository": ...

    async def create_identity_repository(self) -> "IdentityRepository": ...

    async def create_migration_checkpoint_repository(
        self,
    ) -> "MigrationCheckpointRepository": ...

    async def create_request_trace_repository(
        self, *, cursor_signing_key: bytes
    ) -> "RequestTraceRepository": ...

    async def create_usage_ledger_repository(self) -> "UsageLedgerRepository": ...


class StorageAdapter:
    def __init__(self):
        self._backend: Optional["StorageBackend"] = None
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._lock:
            if self._initialized:
                return

            postgresql_uri = os.getenv("POSTGRESQL_URI", "").strip()
            mongodb_uri = os.getenv("MONGODB_URI", "").strip()

            if postgresql_uri and mongodb_uri:
                raise RuntimeError(
                    "Configure only one external storage backend: POSTGRESQL_URI or MONGODB_URI."
                )

            if postgresql_uri:
                try:
                    from .storage.postgresql_manager import PostgreSQLManager

                    self._backend = PostgreSQLManager()
                    await self._backend.initialize()
                    log.info("Using the PostgreSQL storage backend.")
                except Exception as e:
                    log.error(f"PostgreSQL backend initialization failed ({type(e).__name__}).")
                    if self._backend:
                        try:
                            await self._backend.close()
                        except Exception:
                            log.warning(
                                "Failed to clean up the PostgreSQL backend after startup failure."
                            )
                    self._backend = None
                    raise RuntimeError(
                        "The configured PostgreSQL storage backend is unavailable. Verify "
                        "POSTGRESQL_URI and install the dependencies from requirements.lock."
                    ) from e
            elif not mongodb_uri:
                try:
                    from .storage.sqlite_manager import SQLiteManager

                    self._backend = SQLiteManager()
                    await self._backend.initialize()
                    log.info("Using the SQLite storage backend.")
                except Exception as e:
                    log.error(f"SQLite backend initialization failed ({type(e).__name__}).")
                    raise RuntimeError("No storage backend is available.") from e
            else:
                try:
                    from .storage.mongodb_manager import MongoDBManager

                    self._backend = MongoDBManager()
                    await self._backend.initialize()
                    log.info("Using the MongoDB storage backend.")
                except Exception as e:
                    log.error(f"MongoDB backend initialization failed ({type(e).__name__}).")
                    if self._backend:
                        try:
                            await self._backend.close()
                        except Exception:
                            log.warning(
                                "Failed to clean up the MongoDB backend after startup failure."
                            )
                    self._backend = None
                    raise RuntimeError(
                        "The configured MongoDB storage backend is unavailable. Verify "
                        "MONGODB_URI and install the dependencies from requirements.lock."
                    ) from e

            self._initialized = True

    async def close(self) -> None:
        if self._backend:
            await self._backend.close()
            self._backend = None
            self._initialized = False

    def _ensure_initialized(self):
        if not self._initialized or not self._backend:
            raise RuntimeError("The storage adapter is not initialized.")

    async def store_credential(
        self, filename: str, credential_data: Dict[str, Any], mode: str = "code_assist"
    ) -> bool:
        self._ensure_initialized()
        stored = await self._backend.store_credential(filename, credential_data, mode)
        if stored:
            await self._publish_credential_invalidations()
        return stored

    async def get_credential(
        self, filename: str, mode: str = "code_assist"
    ) -> Optional[Dict[str, Any]]:
        self._ensure_initialized()
        return await self._backend.get_credential(filename, mode)

    async def list_credentials(self, mode: str = "code_assist") -> List[str]:
        self._ensure_initialized()
        return await self._backend.list_credentials(mode)

    async def get_all_credentials(self, mode: str = "code_assist") -> Dict[str, Dict[str, Any]]:
        self._ensure_initialized()
        return await self._backend.get_all_credentials(mode)

    async def delete_credential(self, filename: str, mode: str = "code_assist") -> bool:
        self._ensure_initialized()
        deleted = await self._backend.delete_credential(filename, mode)
        if deleted:
            await self._publish_credential_invalidations()
        return deleted

    async def update_credential_state(
        self, filename: str, state_updates: Dict[str, Any], mode: str = "code_assist"
    ) -> bool:
        self._ensure_initialized()
        updated = await self._backend.update_credential_state(filename, state_updates, mode)
        if updated:
            await self._publish_credential_invalidations()
        return updated

    async def get_credential_state(
        self, filename: str, mode: str = "code_assist"
    ) -> Dict[str, Any]:
        self._ensure_initialized()
        return await self._backend.get_credential_state(filename, mode)

    async def get_all_credential_states(
        self, mode: str = "code_assist"
    ) -> Dict[str, Dict[str, Any]]:
        self._ensure_initialized()
        return await self._backend.get_all_credential_states(mode)

    async def mutate_credential_pool(
        self, mode: str, planner: CredentialPoolPlanner
    ) -> Dict[str, Any]:
        """Apply one validated pool plan under the durable backend's write gate."""
        self._ensure_initialized()
        mutation = await self._backend.mutate_credential_pool(mode, planner)
        await self._publish_credential_invalidations()
        return dict(mutation.result)

    async def set_config(self, key: str, value: Any) -> bool:
        self._ensure_initialized()
        stored = await self._backend.set_config(key, value)
        if stored:
            from core.governance_coordination import (
                config_invalidation_scope,
                publish_governance_invalidation,
            )

            await publish_governance_invalidation(config_invalidation_scope(key))
        return stored

    async def get_config(self, key: str, default: Any = None) -> Any:
        self._ensure_initialized()
        return await self._backend.get_config(key, default)

    async def get_all_config(self) -> Dict[str, Any]:
        self._ensure_initialized()
        return await self._backend.get_all_config()

    async def reload_config_cache(self) -> None:
        """Refresh the selected backend's process-local durable config view."""

        self._ensure_initialized()
        await self._backend.reload_config_cache()

    async def delete_config(self, key: str) -> bool:
        self._ensure_initialized()
        deleted = await self._backend.delete_config(key)
        if deleted:
            from core.governance_coordination import (
                config_invalidation_scope,
                publish_governance_invalidation,
            )

            await publish_governance_invalidation(config_invalidation_scope(key))
        return deleted

    @staticmethod
    async def _publish_credential_invalidations() -> None:
        from core.governance_coordination import (
            credential_invalidation_scopes,
            publish_governance_invalidation,
        )

        for scope in credential_invalidation_scopes():
            await publish_governance_invalidation(scope)

    async def create_audit_repository(self, *, cursor_signing_key: bytes) -> "AuditRepository":
        """Create the audit repository owned by the selected storage backend."""

        self._ensure_initialized()
        return await self._backend.create_audit_repository(cursor_signing_key=cursor_signing_key)

    async def create_identity_repository(self) -> "IdentityRepository":
        """Create the identity repository owned by the selected storage backend."""

        self._ensure_initialized()
        return await self._backend.create_identity_repository()

    async def create_migration_checkpoint_repository(
        self,
    ) -> "MigrationCheckpointRepository":
        """Create the migration checkpoint repository owned by the selected backend."""

        self._ensure_initialized()
        return await self._backend.create_migration_checkpoint_repository()

    async def create_request_trace_repository(
        self, *, cursor_signing_key: bytes
    ) -> "RequestTraceRepository":
        """Create the request trace repository owned by the selected storage backend."""

        self._ensure_initialized()
        return await self._backend.create_request_trace_repository(
            cursor_signing_key=cursor_signing_key
        )

    async def create_usage_ledger_repository(self) -> "UsageLedgerRepository":
        """Create the usage ledger owned by the selected storage backend."""

        self._ensure_initialized()
        return await self._backend.create_usage_ledger_repository()

    async def export_credential_to_json(self, filename: str, output_path: str = None) -> bool:
        self._ensure_initialized()
        if hasattr(self._backend, "export_credential_to_json"):
            return await self._backend.export_credential_to_json(filename, output_path)

        credential_data = await self.get_credential(filename)
        if credential_data is None:
            return False

        if output_path is None:
            output_path = f"{filename}.json"

        import aiofiles

        try:
            async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(credential_data, indent=2, ensure_ascii=False))
            return True
        except Exception as exc:
            log.warning(f"Credential export failed ({type(exc).__name__}).")
            return False

    async def import_credential_from_json(self, json_path: str, filename: str = None) -> bool:
        self._ensure_initialized()
        if hasattr(self._backend, "import_credential_from_json"):
            return await self._backend.import_credential_from_json(json_path, filename)

        try:
            import aiofiles

            async with aiofiles.open(json_path, "r", encoding="utf-8") as f:
                content = await f.read()

            credential_data = json.loads(content)

            if filename is None:
                filename = os.path.basename(json_path)

            return await self.store_credential(filename, credential_data)
        except Exception as exc:
            log.warning(f"Credential import failed ({type(exc).__name__}).")
            return False

    def get_backend_type(self) -> str:
        if not self._backend:
            return "none"

        backend_class_name = self._backend.__class__.__name__.lower()
        if "sqlite" in backend_class_name:
            return "sqlite"
        elif "mongodb" in backend_class_name or "mongo" in backend_class_name:
            return "mongodb"
        elif (
            "postgresql" in backend_class_name
            or "postgres" in backend_class_name
            or "psql" in backend_class_name
        ):
            return "postgresql"
        else:
            return "unknown"

    async def get_backend_info(self) -> Dict[str, Any]:
        self._ensure_initialized()

        backend_type = self.get_backend_type()
        info = {"backend_type": backend_type, "initialized": self._initialized}

        if backend_type == "sqlite":
            info.update(
                {
                    "database_path": getattr(self._backend, "_db_path", None),
                    "credentials_dir": getattr(self._backend, "_credentials_dir", None),
                }
            )
        elif backend_type == "mongodb":
            info.update(
                {
                    "database_name": getattr(self._backend, "_db", {}).name
                    if hasattr(self._backend, "_db")
                    else None,
                }
            )

        return info


_storage_adapter: Optional[StorageAdapter] = None
_storage_adapter_lock = asyncio.Lock()


async def get_storage_adapter() -> StorageAdapter:
    global _storage_adapter

    if _storage_adapter is None:
        async with _storage_adapter_lock:
            if _storage_adapter is None:
                adapter = StorageAdapter()
                await adapter.initialize()
                _storage_adapter = adapter

    return _storage_adapter


async def close_storage_adapter():
    global _storage_adapter

    async with _storage_adapter_lock:
        if _storage_adapter:
            await _storage_adapter.close()
            _storage_adapter = None
