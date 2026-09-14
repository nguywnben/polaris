import asyncio
import json
import os
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import asyncpg
from core.credential_pool_mutation import (
    CredentialPoolMutation,
    CredentialPoolMutationError,
    CredentialPoolPlanner,
    CredentialPoolRecord,
    normalize_pool_mode,
    validate_credential_pool_mutation,
)
from log import log

if TYPE_CHECKING:
    from core.audit import AuditRepository
    from core.durable_migration_runner import MigrationCheckpointRepository
    from core.identity.repository import IdentityRepository


class PostgreSQLManager:
    STATE_FIELDS = {
        "error_codes",
        "error_messages",
        "disabled",
        "last_success",
        "user_email",
        "model_cooldowns",
        "preview",
        "tier",
        "enable_credit",
    }

    def __init__(self):
        self._dsn: Optional[str] = None
        self._pool: Optional[asyncpg.Pool] = None
        self._initialized = False
        self._lock = asyncio.Lock()

        self._config_cache: Dict[str, Any] = {}
        self._config_loaded = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            try:
                self._dsn = os.getenv("POSTGRESQL_URI", "")
                if not self._dsn:
                    raise RuntimeError("POSTGRESQL_URI environment variable is not set")

                self._pool = await asyncpg.create_pool(self._dsn, min_size=2, max_size=10)

                async with self._pool.acquire() as conn:
                    await self._create_tables(conn)
                    await self._ensure_schema_compatibility(conn)

                await self._load_config_cache()

                self._initialized = True
                log.info("PostgreSQL storage initialized")

            except Exception as e:
                log.error(f"PostgreSQL initialization failed ({type(e).__name__}).")
                if self._pool:
                    await self._pool.close()
                    self._pool = None
                raise

    async def _create_tables(self, conn: asyncpg.Connection) -> None:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                id SERIAL PRIMARY KEY,
                filename TEXT UNIQUE NOT NULL,
                credential_data TEXT NOT NULL,

                disabled INTEGER DEFAULT 0,
                error_codes TEXT DEFAULT '[]',
                error_messages TEXT DEFAULT '[]',
                last_success DOUBLE PRECISION,
                user_email TEXT,

                model_cooldowns TEXT DEFAULT '{}',
                preview INTEGER DEFAULT 1,
                tier TEXT DEFAULT 'pro',

                rotation_order INTEGER DEFAULT 0,
                call_count INTEGER DEFAULT 0,

                created_at DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW()),
                updated_at DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW())
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS primary_credentials (
                id SERIAL PRIMARY KEY,
                filename TEXT UNIQUE NOT NULL,
                credential_data TEXT NOT NULL,

                disabled INTEGER DEFAULT 0,
                error_codes TEXT DEFAULT '[]',
                error_messages TEXT DEFAULT '[]',
                last_success DOUBLE PRECISION,
                user_email TEXT,

                model_cooldowns TEXT DEFAULT '{}',
                tier TEXT DEFAULT 'pro',
                enable_credit INTEGER DEFAULT 0,

                rotation_order INTEGER DEFAULT 0,
                call_count INTEGER DEFAULT 0,

                created_at DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW()),
                updated_at DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW())
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW())
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_disabled ON credentials(disabled)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rotation_order ON credentials(rotation_order)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_primary_disabled ON primary_credentials(disabled)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_primary_rotation_order ON primary_credentials(rotation_order)
        """)

        log.debug("PostgreSQL tables and indexes created")

    async def _ensure_schema_compatibility(self, conn: asyncpg.Connection) -> None:
        required_columns = {
            "credentials": [
                ("disabled", "INTEGER DEFAULT 0"),
                ("error_codes", "TEXT DEFAULT '[]'"),
                ("error_messages", "TEXT DEFAULT '[]'"),
                ("last_success", "DOUBLE PRECISION"),
                ("user_email", "TEXT"),
                ("model_cooldowns", "TEXT DEFAULT '{}'"),
                ("preview", "INTEGER DEFAULT 1"),
                ("tier", "TEXT DEFAULT 'pro'"),
                ("rotation_order", "INTEGER DEFAULT 0"),
                ("call_count", "INTEGER DEFAULT 0"),
                ("created_at", "DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW())"),
                ("updated_at", "DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW())"),
            ],
            "primary_credentials": [
                ("disabled", "INTEGER DEFAULT 0"),
                ("error_codes", "TEXT DEFAULT '[]'"),
                ("error_messages", "TEXT DEFAULT '[]'"),
                ("last_success", "DOUBLE PRECISION"),
                ("user_email", "TEXT"),
                ("model_cooldowns", "TEXT DEFAULT '{}'"),
                ("tier", "TEXT DEFAULT 'pro'"),
                ("enable_credit", "INTEGER DEFAULT 0"),
                ("rotation_order", "INTEGER DEFAULT 0"),
                ("call_count", "INTEGER DEFAULT 0"),
                ("created_at", "DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW())"),
                ("updated_at", "DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW())"),
            ],
        }

        try:
            for table_name, columns in required_columns.items():
                rows = await conn.fetch(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = $1
                """,
                    table_name,
                )
                existing = {r["column_name"] for r in rows}

                for col_name, col_def in columns:
                    if col_name not in existing:
                        try:
                            await conn.execute(
                                f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"
                            )
                            log.info(f"Added missing column {table_name}.{col_name}")
                        except Exception as e:
                            log.error(f"Failed to add column {table_name}.{col_name}: {e}")
        except Exception as e:
            log.error(f"Error ensuring schema compatibility: {e}")

    async def _load_config_cache(self) -> None:
        if self._config_loaded:
            return

        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("SELECT key, value FROM config")

            for row in rows:
                try:
                    self._config_cache[row["key"]] = json.loads(row["value"])
                except json.JSONDecodeError:
                    self._config_cache[row["key"]] = row["value"]

            self._config_loaded = True
            log.debug(f"Loaded {len(self._config_cache)} config items into cache")

        except Exception as e:
            log.error(f"Error loading config cache: {e}")
            self._config_cache = {}

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
        self._initialized = False
        log.debug("PostgreSQL storage closed")

    def _ensure_initialized(self) -> None:
        if not self._initialized or not self._pool:
            raise RuntimeError("PostgreSQL manager not initialized")

    async def create_audit_repository(self, *, cursor_signing_key: bytes) -> "AuditRepository":
        self._ensure_initialized()
        from .audit_postgresql import PostgreSQLAuditRepository

        repository = PostgreSQLAuditRepository(
            self._pool,
            cursor_signing_key=cursor_signing_key,
        )
        await repository.initialize()
        return repository

    async def create_identity_repository(self) -> "IdentityRepository":
        self._ensure_initialized()
        from .identity_postgresql import PostgreSQLIdentityRepository

        repository = PostgreSQLIdentityRepository(self._pool)
        await repository.initialize()
        return repository

    async def create_migration_checkpoint_repository(
        self,
    ) -> "MigrationCheckpointRepository":
        self._ensure_initialized()
        from .migration_postgresql import PostgreSQLMigrationCheckpointRepository

        repository = PostgreSQLMigrationCheckpointRepository(self._pool)
        await repository.initialize()
        return repository

    async def create_request_trace_repository(self, *, cursor_signing_key: bytes):
        self._ensure_initialized()
        from .request_trace_postgresql import PostgreSQLRequestTraceRepository

        repository = PostgreSQLRequestTraceRepository(
            self._pool,
            cursor_signing_key=cursor_signing_key,
        )
        await repository.initialize()
        return repository

    async def create_usage_ledger_repository(self):
        self._ensure_initialized()
        from paths import DEFAULT_CREDENTIALS_DIR

        from .usage_ledger_postgresql import PostgreSQLUsageLedgerRepository
        from .usage_legacy_gate import require_external_usage_migration_ready

        credentials_dir = os.getenv("CREDENTIALS_DIR", str(DEFAULT_CREDENTIALS_DIR))
        await require_external_usage_migration_ready(
            os.path.join(credentials_dir, "usage_stats.db")
        )
        repository = PostgreSQLUsageLedgerRepository(self._pool)
        await repository.initialize()
        return repository

    def _get_table_name(self, mode: str) -> str:
        if mode == "primary":
            return "primary_credentials"
        elif mode == "code_assist":
            return "credentials"
        else:
            raise ValueError(f"Invalid mode: {mode}. Must be 'code_assist' or 'primary'")

    async def get_next_available_credential(
        self, mode: str = "code_assist", model_name: Optional[str] = None
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        self._ensure_initialized()

        try:
            table_name = self._get_table_name(mode)
            current_time = time.time()

            async with self._pool.acquire() as conn:
                if mode == "code_assist":
                    rows = await conn.fetch(f"""
                        SELECT filename, credential_data, model_cooldowns, preview
                        FROM {table_name}
                        WHERE disabled = 0
                        ORDER BY call_count ASC NULLS FIRST,
                                 last_success ASC NULLS FIRST,
                                 rotation_order ASC,
                                 filename ASC
                    """)

                    if not model_name:
                        if rows:
                            return rows[0]["filename"], json.loads(rows[0]["credential_data"])
                        return None

                    is_preview_model = "preview" in model_name.lower()
                    non_preview_creds = []
                    preview_creds = []

                    for row in rows:
                        model_cooldowns = json.loads(row["model_cooldowns"] or "{}")
                        cd = model_cooldowns.get(model_name)
                        if cd is None or current_time >= cd:
                            if row["preview"]:
                                preview_creds.append((row["filename"], row["credential_data"]))
                            else:
                                non_preview_creds.append((row["filename"], row["credential_data"]))

                    if is_preview_model:
                        if preview_creds:
                            return preview_creds[0][0], json.loads(preview_creds[0][1])
                    else:
                        if non_preview_creds:
                            return non_preview_creds[0][0], json.loads(non_preview_creds[0][1])
                        elif preview_creds:
                            return preview_creds[0][0], json.loads(preview_creds[0][1])

                    return None
                else:
                    rows = await conn.fetch(f"""
                        SELECT filename, credential_data, model_cooldowns, enable_credit
                        FROM {table_name}
                        WHERE disabled = 0
                        ORDER BY call_count ASC NULLS FIRST,
                                 last_success ASC NULLS FIRST,
                                 rotation_order ASC,
                                 filename ASC
                    """)

                    if not model_name:
                        if rows:
                            credential_data = json.loads(rows[0]["credential_data"])
                            credential_data["enable_credit"] = bool(rows[0]["enable_credit"])
                            return rows[0]["filename"], credential_data
                        return None

                    for row in rows:
                        model_cooldowns = json.loads(row["model_cooldowns"] or "{}")
                        cd = model_cooldowns.get(model_name)
                        if cd is None or current_time >= cd:
                            credential_data = json.loads(row["credential_data"])
                            credential_data["enable_credit"] = bool(row["enable_credit"])
                            return row["filename"], credential_data

                    return None

        except Exception as e:
            log.error(
                f"Error getting next available credential (mode={mode}, model_name={model_name}): {e}"
            )
            return None

    async def get_available_credentials_list(self) -> List[str]:
        self._ensure_initialized()

        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT filename FROM credentials
                    WHERE disabled = 0
                    ORDER BY rotation_order ASC
                """)
                return [r["filename"] for r in rows]
        except Exception as e:
            log.error(f"Error getting available credentials list: {e}")
            return []

    async def store_credential(
        self, filename: str, credential_data: Dict[str, Any], mode: str = "code_assist"
    ) -> bool:
        self._ensure_initialized()
        filename = os.path.basename(filename)

        try:
            table_name = self._get_table_name(mode)
            async with self._pool.acquire() as conn:
                existing = await conn.fetchrow(
                    f"SELECT rotation_order FROM {table_name} WHERE filename = $1", filename
                )

                if existing:
                    await conn.execute(
                        f"""
                        UPDATE {table_name}
                        SET credential_data = $1,
                            updated_at = EXTRACT(EPOCH FROM NOW())
                        WHERE filename = $2
                        """,
                        json.dumps(credential_data),
                        filename,
                    )
                else:
                    row = await conn.fetchrow(
                        f"SELECT COALESCE(MAX(rotation_order), -1) + 1 AS next_order FROM {table_name}"
                    )
                    next_order = row["next_order"]
                    await conn.execute(
                        f"""
                        INSERT INTO {table_name}
                        (filename, credential_data, rotation_order, last_success)
                        VALUES ($1, $2, $3, $4)
                        """,
                        filename,
                        json.dumps(credential_data),
                        next_order,
                        time.time(),
                    )

            log.debug(f"Stored credential: {filename} (mode={mode})")
            return True

        except Exception as e:
            log.error(f"Error storing credential {filename}: {e}")
            return False

    async def mutate_credential_pool(
        self, mode: str, planner: CredentialPoolPlanner
    ) -> CredentialPoolMutation:
        """Apply one pool plan under a transaction-scoped table write gate."""
        self._ensure_initialized()
        mode = normalize_pool_mode(mode)
        table_name = self._get_table_name(mode)
        if not callable(planner):
            raise CredentialPoolMutationError("Credential pool planner is invalid.")
        try:
            async with self._pool.acquire() as connection:
                async with connection.transaction():
                    await connection.execute(f"LOCK TABLE {table_name} IN SHARE ROW EXCLUSIVE MODE")
                    rows = await connection.fetch(
                        f"""SELECT filename, credential_data, user_email, rotation_order
                            FROM {table_name} ORDER BY rotation_order, filename"""
                    )
                    records = []
                    for row in rows:
                        credential_data = json.loads(row["credential_data"])
                        if type(credential_data) is not dict:
                            raise CredentialPoolMutationError(
                                "Stored credential payload is invalid."
                            )
                        records.append(
                            CredentialPoolRecord(
                                filename=row["filename"],
                                credential_data=credential_data,
                                user_email=row["user_email"],
                                rotation_order=row["rotation_order"],
                            )
                        )
                    mutation = validate_credential_pool_mutation(planner(tuple(records)))
                    for filename in mutation.deletes:
                        await connection.execute(
                            f"DELETE FROM {table_name} WHERE filename = $1", filename
                        )
                    next_order = max((record.rotation_order for record in records), default=-1) + 1
                    existing_names = {record.filename for record in records}
                    for write in mutation.writes:
                        if write.filename in existing_names:
                            await connection.execute(
                                f"""UPDATE {table_name}
                                    SET credential_data = $1, user_email = $2,
                                        updated_at = EXTRACT(EPOCH FROM NOW())
                                    WHERE filename = $3""",
                                json.dumps(write.credential_data),
                                write.user_email,
                                write.filename,
                            )
                        else:
                            await connection.execute(
                                f"""INSERT INTO {table_name}
                                    (filename, credential_data, user_email, rotation_order, last_success)
                                    VALUES ($1, $2, $3, $4, $5)""",
                                write.filename,
                                json.dumps(write.credential_data),
                                write.user_email,
                                next_order,
                                time.time(),
                            )
                            next_order += 1
                    return mutation
        except CredentialPoolMutationError:
            raise
        except Exception:
            raise CredentialPoolMutationError("Credential pool mutation failed.") from None

    async def get_credential(
        self, filename: str, mode: str = "code_assist"
    ) -> Optional[Dict[str, Any]]:
        self._ensure_initialized()
        filename = os.path.basename(filename)

        try:
            table_name = self._get_table_name(mode)
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"SELECT credential_data FROM {table_name} WHERE filename = $1", filename
                )
                if row:
                    return json.loads(row["credential_data"])
                return None
        except Exception as e:
            log.error(f"Error getting credential {filename}: {e}")
            return None

    async def list_credentials(self, mode: str = "code_assist") -> List[str]:
        self._ensure_initialized()

        try:
            table_name = self._get_table_name(mode)
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    f"SELECT filename FROM {table_name} ORDER BY rotation_order"
                )
                return [r["filename"] for r in rows]
        except Exception as e:
            log.error(f"Error listing credentials: {e}")
            return []

    async def get_all_credentials(self, mode: str = "code_assist") -> Dict[str, Dict[str, Any]]:
        self._ensure_initialized()
        try:
            table_name = self._get_table_name(mode)
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    f"SELECT filename, credential_data FROM {table_name} ORDER BY rotation_order"
                )
            credentials = {}
            for row in rows:
                try:
                    credentials[row["filename"]] = json.loads(row["credential_data"])
                except (TypeError, json.JSONDecodeError):
                    log.warning(f"Ignoring invalid credential data for {row['filename']}.")
            return credentials
        except Exception as e:
            log.error(f"Error loading credentials: {e}")
            return {}

    async def delete_credential(self, filename: str, mode: str = "code_assist") -> bool:
        self._ensure_initialized()
        filename = os.path.basename(filename)

        try:
            table_name = self._get_table_name(mode)
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    f"DELETE FROM {table_name} WHERE filename = $1", filename
                )
                # asyncpg returns "DELETE N"
                deleted_count = int(result.split()[-1])

            if deleted_count > 0:
                log.debug(f"Deleted credential: {filename} (mode={mode})")
                return True
            else:
                log.warning(f"No credential found to delete: {filename} (mode={mode})")
                return False

        except Exception as e:
            log.error(f"Error deleting credential {filename}: {e}")
            return False

    async def update_credential_state(
        self, filename: str, state_updates: Dict[str, Any], mode: str = "code_assist"
    ) -> bool:
        self._ensure_initialized()
        filename = os.path.basename(filename)

        try:
            table_name = self._get_table_name(mode)
            log.debug(
                f"[DB] update_credential_state: filename={filename}, updates={state_updates}, mode={mode}"
            )

            set_clauses = []
            values = []
            idx = 1

            for key, value in state_updates.items():
                if key in self.STATE_FIELDS:
                    if key == "enable_credit" and mode != "primary":
                        continue
                    if key in ("error_codes", "error_messages", "model_cooldowns"):
                        set_clauses.append(f"{key} = ${idx}")
                        values.append(json.dumps(value))
                    else:
                        set_clauses.append(f"{key} = ${idx}")
                        values.append(value)
                    idx += 1

            if not set_clauses:
                return True

            set_clauses.append("updated_at = EXTRACT(EPOCH FROM NOW())")
            values.append(filename)

            sql = f"""
                UPDATE {table_name}
                SET {", ".join(set_clauses)}
                WHERE filename = ${idx}
            """

            async with self._pool.acquire() as conn:
                result = await conn.execute(sql, *values)
                updated_count = int(result.split()[-1])

            return updated_count > 0

        except Exception as e:
            log.error(f"[DB] Error updating credential state {filename}: {e}")
            return False

    async def get_credential_state(
        self, filename: str, mode: str = "code_assist"
    ) -> Dict[str, Any]:
        self._ensure_initialized()
        filename = os.path.basename(filename)

        try:
            table_name = self._get_table_name(mode)
            async with self._pool.acquire() as conn:
                if mode == "code_assist":
                    row = await conn.fetchrow(
                        f"""
                        SELECT disabled, error_codes, last_success, user_email, model_cooldowns,
                               preview, tier, call_count, rotation_order
                        FROM {table_name} WHERE filename = $1
                    """,
                        filename,
                    )

                    if row:
                        return {
                            "disabled": bool(row["disabled"]),
                            "error_codes": json.loads(row["error_codes"] or "[]"),
                            "last_success": row["last_success"] or time.time(),
                            "user_email": row["user_email"],
                            "model_cooldowns": json.loads(row["model_cooldowns"] or "{}"),
                            "preview": bool(row["preview"]) if row["preview"] is not None else True,
                            "tier": row["tier"] if row["tier"] is not None else "pro",
                            "call_count": row["call_count"] or 0,
                            "rotation_order": row["rotation_order"] or 0,
                        }

                    return {
                        "disabled": False,
                        "error_codes": [],
                        "last_success": time.time(),
                        "user_email": None,
                        "model_cooldowns": {},
                        "preview": True,
                        "tier": "pro",
                        "call_count": 0,
                        "rotation_order": 0,
                    }
                else:
                    row = await conn.fetchrow(
                        f"""
                        SELECT disabled, error_codes, last_success, user_email, model_cooldowns,
                               tier, enable_credit, call_count, rotation_order
                        FROM {table_name} WHERE filename = $1
                    """,
                        filename,
                    )

                    if row:
                        return {
                            "disabled": bool(row["disabled"]),
                            "error_codes": json.loads(row["error_codes"] or "[]"),
                            "last_success": row["last_success"] or time.time(),
                            "user_email": row["user_email"],
                            "model_cooldowns": json.loads(row["model_cooldowns"] or "{}"),
                            "tier": row["tier"] if row["tier"] is not None else "pro",
                            "enable_credit": bool(row["enable_credit"])
                            if row["enable_credit"] is not None
                            else False,
                            "call_count": row["call_count"] or 0,
                            "rotation_order": row["rotation_order"] or 0,
                        }

                    return {
                        "disabled": False,
                        "error_codes": [],
                        "last_success": time.time(),
                        "user_email": None,
                        "model_cooldowns": {},
                        "tier": "pro",
                        "enable_credit": False,
                        "call_count": 0,
                        "rotation_order": 0,
                    }

        except Exception as e:
            log.error(f"Error getting credential state {filename}: {e}")
            return {}

    async def get_all_credential_states(
        self, mode: str = "code_assist"
    ) -> Dict[str, Dict[str, Any]]:
        self._ensure_initialized()

        try:
            table_name = self._get_table_name(mode)
            current_time = time.time()

            async with self._pool.acquire() as conn:
                if mode == "code_assist":
                    rows = await conn.fetch(f"""
                        SELECT filename, disabled, error_codes, last_success,
                               user_email, model_cooldowns, preview, tier,
                               call_count, rotation_order
                        FROM {table_name}
                    """)

                    states = {}
                    for row in rows:
                        model_cooldowns = json.loads(row["model_cooldowns"] or "{}")
                        if model_cooldowns:
                            model_cooldowns = {
                                k: v for k, v in model_cooldowns.items() if v > current_time
                            }

                        states[row["filename"]] = {
                            "disabled": bool(row["disabled"]),
                            "error_codes": json.loads(row["error_codes"] or "[]"),
                            "last_success": row["last_success"] or current_time,
                            "user_email": row["user_email"],
                            "model_cooldowns": model_cooldowns,
                            "preview": bool(row["preview"]) if row["preview"] is not None else True,
                            "tier": row["tier"] if row["tier"] is not None else "pro",
                            "call_count": row["call_count"] or 0,
                            "rotation_order": row["rotation_order"] or 0,
                        }
                    return states
                else:
                    rows = await conn.fetch(f"""
                        SELECT filename, disabled, error_codes, last_success,
                               user_email, model_cooldowns, tier, enable_credit,
                               call_count, rotation_order
                        FROM {table_name}
                    """)

                    states = {}
                    for row in rows:
                        model_cooldowns = json.loads(row["model_cooldowns"] or "{}")
                        if model_cooldowns:
                            model_cooldowns = {
                                k: v for k, v in model_cooldowns.items() if v > current_time
                            }

                        states[row["filename"]] = {
                            "disabled": bool(row["disabled"]),
                            "error_codes": json.loads(row["error_codes"] or "[]"),
                            "last_success": row["last_success"] or current_time,
                            "user_email": row["user_email"],
                            "model_cooldowns": model_cooldowns,
                            "tier": row["tier"] if row["tier"] is not None else "pro",
                            "enable_credit": bool(row["enable_credit"])
                            if row["enable_credit"] is not None
                            else False,
                            "call_count": row["call_count"] or 0,
                            "rotation_order": row["rotation_order"] or 0,
                        }
                    return states

        except Exception as e:
            log.error(f"Error getting all credential states: {e}")
            return {}

    async def get_credentials_summary(
        self,
        offset: int = 0,
        limit: Optional[int] = None,
        status_filter: str = "all",
        mode: str = "code_assist",
        error_code_filter: Optional[str] = None,
        cooldown_filter: Optional[str] = None,
        preview_filter: Optional[str] = None,
        tier_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_initialized()

        try:
            table_name = self._get_table_name(mode)
            current_time = time.time()

            async with self._pool.acquire() as conn:
                stats_rows = await conn.fetch(
                    f"SELECT disabled, COUNT(*) AS cnt FROM {table_name} GROUP BY disabled"
                )
                global_stats = {"total": 0, "normal": 0, "disabled": 0}
                for r in stats_rows:
                    global_stats["total"] += r["cnt"]
                    if r["disabled"]:
                        global_stats["disabled"] = r["cnt"]
                    else:
                        global_stats["normal"] = r["cnt"]

                where_clauses = []
                if status_filter == "enabled":
                    where_clauses.append("disabled = 0")
                elif status_filter == "disabled":
                    where_clauses.append("disabled = 1")

                where_clause = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

                if mode == "code_assist":
                    all_rows = await conn.fetch(f"""
                        SELECT filename, disabled, error_codes, last_success,
                               user_email, rotation_order, model_cooldowns, preview, tier
                        FROM {table_name}
                        {where_clause}
                        ORDER BY rotation_order
                    """)
                else:
                    all_rows = await conn.fetch(f"""
                        SELECT filename, disabled, error_codes, last_success,
                               user_email, rotation_order, model_cooldowns, tier, enable_credit
                        FROM {table_name}
                        {where_clause}
                        ORDER BY rotation_order
                    """)

                filter_value = None
                filter_int = None
                filter_none = False
                if error_code_filter and str(error_code_filter).strip().lower() != "all":
                    if str(error_code_filter).strip().lower() == "none":
                        filter_none = True
                    else:
                        filter_value = str(error_code_filter).strip()
                        try:
                            filter_int = int(filter_value)
                        except ValueError:
                            filter_int = None

                all_summaries = []
                for row in all_rows:
                    error_codes_json = row["error_codes"] or "[]"
                    model_cooldowns = json.loads(row["model_cooldowns"] or "{}")
                    active_cooldowns = {
                        k: v for k, v in model_cooldowns.items() if v > current_time
                    }
                    error_codes = json.loads(error_codes_json)

                    if filter_none:
                        if error_codes:
                            continue

                    if filter_value:
                        match = False
                        for code in error_codes:
                            if code == filter_value or code == filter_int:
                                match = True
                                break
                            if isinstance(code, str) and filter_int is not None:
                                try:
                                    if int(code) == filter_int:
                                        match = True
                                        break
                                except ValueError:
                                    pass
                        if not match:
                            continue

                    summary = {
                        "filename": row["filename"],
                        "disabled": bool(row["disabled"]),
                        "error_codes": error_codes,
                        "last_success": row["last_success"] or current_time,
                        "user_email": row["user_email"],
                        "rotation_order": row["rotation_order"],
                        "model_cooldowns": active_cooldowns,
                        "tier": row["tier"] if row["tier"] is not None else "pro",
                    }

                    if mode == "code_assist":
                        summary["preview"] = (
                            bool(row["preview"]) if row["preview"] is not None else True
                        )

                        if preview_filter:
                            preview_value = summary.get("preview", True)
                            if preview_filter == "preview" and not preview_value:
                                continue
                            elif preview_filter == "no_preview" and preview_value:
                                continue
                    else:
                        summary["enable_credit"] = (
                            bool(row["enable_credit"])
                            if row["enable_credit"] is not None
                            else False
                        )

                    if tier_filter and tier_filter in ("free", "pro", "ultra"):
                        if summary["tier"] != tier_filter:
                            continue

                    if cooldown_filter == "in_cooldown":
                        if active_cooldowns:
                            all_summaries.append(summary)
                    elif cooldown_filter == "no_cooldown":
                        if not active_cooldowns:
                            all_summaries.append(summary)
                    else:
                        all_summaries.append(summary)

                total_count = len(all_summaries)
                if limit is not None:
                    summaries = all_summaries[offset : offset + limit]
                else:
                    summaries = all_summaries[offset:]

                return {
                    "items": summaries,
                    "total": total_count,
                    "offset": offset,
                    "limit": limit,
                    "stats": global_stats,
                }

        except Exception as e:
            log.error(f"Error getting credentials summary: {e}")
            return {
                "items": [],
                "total": 0,
                "offset": offset,
                "limit": limit,
                "stats": {"total": 0, "normal": 0, "disabled": 0},
            }

    async def get_duplicate_credentials_by_email(self, mode: str = "code_assist") -> Dict[str, Any]:
        self._ensure_initialized()

        try:
            table_name = self._get_table_name(mode)
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    f"SELECT filename, user_email FROM {table_name} ORDER BY filename"
                )

            email_to_files: Dict[str, List[str]] = {}
            no_email_files: List[str] = []

            for row in rows:
                if row["user_email"]:
                    email_to_files.setdefault(row["user_email"], []).append(row["filename"])
                else:
                    no_email_files.append(row["filename"])

            duplicate_groups = []
            total_duplicate_count = 0
            for email, files in email_to_files.items():
                if len(files) > 1:
                    duplicate_groups.append(
                        {
                            "email": email,
                            "kept_file": files[0],
                            "duplicate_files": files[1:],
                            "duplicate_count": len(files) - 1,
                        }
                    )
                    total_duplicate_count += len(files) - 1

            return {
                "email_groups": email_to_files,
                "duplicate_groups": duplicate_groups,
                "duplicate_count": total_duplicate_count,
                "no_email_files": no_email_files,
                "no_email_count": len(no_email_files),
                "unique_email_count": len(email_to_files),
                "total_count": len(rows),
            }

        except Exception as e:
            log.error(f"Error getting duplicate credentials by email: {e}")
            return {
                "email_groups": {},
                "duplicate_groups": [],
                "duplicate_count": 0,
                "no_email_files": [],
                "no_email_count": 0,
                "unique_email_count": 0,
                "total_count": 0,
            }

    async def set_config(self, key: str, value: Any) -> bool:
        self._ensure_initialized()

        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO config (key, value, updated_at)
                    VALUES ($1, $2, EXTRACT(EPOCH FROM NOW()))
                    ON CONFLICT (key) DO UPDATE
                        SET value = EXCLUDED.value,
                            updated_at = EXCLUDED.updated_at
                """,
                    key,
                    json.dumps(value),
                )

            self._config_cache[key] = value
            return True

        except Exception as e:
            log.error(f"Error setting config {key}: {e}")
            return False

    async def reload_config_cache(self) -> None:
        self._ensure_initialized()
        self._config_loaded = False
        await self._load_config_cache()
        log.info("Config cache reloaded from database")

    async def get_config(self, key: str, default: Any = None) -> Any:
        self._ensure_initialized()
        return self._config_cache.get(key, default)

    async def get_all_config(self) -> Dict[str, Any]:
        self._ensure_initialized()
        return self._config_cache.copy()

    async def delete_config(self, key: str) -> bool:
        self._ensure_initialized()

        try:
            async with self._pool.acquire() as conn:
                await conn.execute("DELETE FROM config WHERE key = $1", key)

            self._config_cache.pop(key, None)
            return True

        except Exception as e:
            log.error(f"Error deleting config {key}: {e}")
            return False

    async def get_credential_errors(
        self, filename: str, mode: str = "code_assist"
    ) -> Dict[str, Any]:
        self._ensure_initialized()
        filename = os.path.basename(filename)

        try:
            table_name = self._get_table_name(mode)
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"SELECT error_codes, error_messages FROM {table_name} WHERE filename = $1",
                    filename,
                )

            if row:
                return {
                    "filename": filename,
                    "error_codes": json.loads(row["error_codes"] or "[]"),
                    "error_messages": json.loads(row["error_messages"] or "[]"),
                }

            return {"filename": filename, "error_codes": [], "error_messages": []}

        except Exception as e:
            log.error(f"Error getting credential errors {filename}: {e}")
            return {"filename": filename, "error_codes": [], "error_messages": [], "error": str(e)}

    async def set_model_cooldown(
        self,
        filename: str,
        model_name: str,
        cooldown_until: Optional[float],
        mode: str = "code_assist",
    ) -> bool:
        self._ensure_initialized()
        filename = os.path.basename(filename)

        try:
            table_name = self._get_table_name(mode)
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"SELECT model_cooldowns FROM {table_name} WHERE filename = $1", filename
                )

                if not row:
                    log.warning(f"Credential {filename} not found")
                    return False

                model_cooldowns = json.loads(row["model_cooldowns"] or "{}")

                if cooldown_until is None:
                    model_cooldowns.pop(model_name, None)
                else:
                    model_cooldowns[model_name] = cooldown_until

                await conn.execute(
                    f"""
                    UPDATE {table_name}
                    SET model_cooldowns = $1,
                        updated_at = EXTRACT(EPOCH FROM NOW())
                    WHERE filename = $2
                    """,
                    json.dumps(model_cooldowns),
                    filename,
                )

            log.debug(
                f"Set model cooldown: {filename}, model_name={model_name}, cooldown_until={cooldown_until}"
            )
            return True

        except Exception as e:
            log.error(f"Error setting model cooldown for {filename}: {e}")
            return False

    async def clear_all_model_cooldowns(self, filename: str, mode: str = "code_assist") -> bool:
        self._ensure_initialized()
        filename = os.path.basename(filename)

        try:
            table_name = self._get_table_name(mode)
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    f"""
                    UPDATE {table_name}
                    SET model_cooldowns = '{{}}',
                        updated_at = EXTRACT(EPOCH FROM NOW())
                    WHERE filename = $1
                    """,
                    filename,
                )
                updated_count = int(result.split()[-1])

            if updated_count == 0:
                log.warning(f"Credential {filename} not found")
                return False

            log.debug(f"Cleared all model cooldowns: {filename} (mode={mode})")
            return True

        except Exception as e:
            log.error(f"Error clearing all model cooldowns for {filename}: {e}")
            return False

    async def record_success(
        self,
        filename: str,
        model_name: Optional[str] = None,
        mode: str = "code_assist",
        call_increment: int = 1,
    ) -> None:
        self._ensure_initialized()
        filename = os.path.basename(filename)
        call_increment = max(1, int(call_increment))

        try:
            table_name = self._get_table_name(mode)
            async with self._pool.acquire() as conn:
                await conn.execute(
                    f"""
                    UPDATE {table_name}
                    SET last_success = EXTRACT(EPOCH FROM NOW()),
                        call_count = COALESCE(call_count, 0) + $2,
                        error_codes = '[]',
                        error_messages = '{{}}',
                        updated_at = EXTRACT(EPOCH FROM NOW())
                    WHERE filename = $1
                """,
                    filename,
                    call_increment,
                )

                if model_name:
                    row = await conn.fetchrow(
                        f"SELECT model_cooldowns FROM {table_name} WHERE filename = $1", filename
                    )
                    if row:
                        cooldowns = json.loads(row["model_cooldowns"] or "{}")
                        if model_name in cooldowns:
                            cooldowns.pop(model_name)
                            await conn.execute(
                                f"""
                                UPDATE {table_name}
                                SET model_cooldowns = $1, updated_at = EXTRACT(EPOCH FROM NOW())
                                WHERE filename = $2
                                """,
                                json.dumps(cooldowns),
                                filename,
                            )

        except Exception as e:
            log.error(f"Error recording success for {filename}: {e}")

    async def record_failure(self, filename: str, mode: str = "code_assist") -> None:
        """Count failed attempts so routing fairness includes all upstream traffic."""
        self._ensure_initialized()
        filename = os.path.basename(filename)

        try:
            table_name = self._get_table_name(mode)
            async with self._pool.acquire() as conn:
                await conn.execute(
                    f"""
                    UPDATE {table_name}
                    SET call_count = COALESCE(call_count, 0) + 1,
                        updated_at = EXTRACT(EPOCH FROM NOW())
                    WHERE filename = $1
                    """,
                    filename,
                )
        except Exception as e:
            log.error(f"Error recording failure for {filename}: {e}")
