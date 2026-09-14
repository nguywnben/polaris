import asyncio
import json
import os
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import aiosqlite
from core.credential_pool_mutation import (
    CredentialPoolMutation,
    CredentialPoolMutationError,
    CredentialPoolPlanner,
    CredentialPoolRecord,
    normalize_pool_mode,
    validate_credential_pool_mutation,
)
from log import log
from paths import DEFAULT_CREDENTIALS_DIR

from .sqlite_runtime import open_sqlite, verify_existing_sqlite_database

if TYPE_CHECKING:
    from core.audit import AuditRepository
    from core.durable_migration_runner import MigrationCheckpointRepository
    from core.identity.repository import IdentityRepository


class SQLiteManager:
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

    REQUIRED_COLUMNS = {
        "credentials": [
            ("disabled", "INTEGER DEFAULT 0"),
            ("error_codes", "TEXT DEFAULT '[]'"),
            ("error_messages", "TEXT DEFAULT '[]'"),
            ("last_success", "REAL"),
            ("user_email", "TEXT"),
            ("model_cooldowns", "TEXT DEFAULT '{}'"),
            ("preview", "INTEGER DEFAULT 1"),
            ("tier", "TEXT DEFAULT 'pro'"),
            ("rotation_order", "INTEGER DEFAULT 0"),
            ("call_count", "INTEGER DEFAULT 0"),
            ("created_at", "REAL"),
            ("updated_at", "REAL"),
        ],
        "primary_credentials": [
            ("disabled", "INTEGER DEFAULT 0"),
            ("error_codes", "TEXT DEFAULT '[]'"),
            ("error_messages", "TEXT DEFAULT '[]'"),
            ("last_success", "REAL"),
            ("user_email", "TEXT"),
            ("model_cooldowns", "TEXT DEFAULT '{}'"),
            ("tier", "TEXT DEFAULT 'pro'"),
            ("enable_credit", "INTEGER DEFAULT 0"),
            ("rotation_order", "INTEGER DEFAULT 0"),
            ("call_count", "INTEGER DEFAULT 0"),
            ("created_at", "REAL"),
            ("updated_at", "REAL"),
        ],
    }

    def __init__(self):
        self._db_path = None
        self._credentials_dir = None
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
                self._credentials_dir = os.getenv("CREDENTIALS_DIR", str(DEFAULT_CREDENTIALS_DIR))
                self._db_path = os.path.join(self._credentials_dir, "credentials.db")

                os.makedirs(self._credentials_dir, exist_ok=True)
                await asyncio.to_thread(verify_existing_sqlite_database, self._db_path)

                async with open_sqlite(self._db_path) as db:
                    await db.execute("PRAGMA journal_mode=WAL")
                    await db.execute("BEGIN IMMEDIATE")
                    try:
                        await self._ensure_schema_compatibility(db)
                        await self._create_tables(db)
                        await self._repair_credential_filenames(db)
                        await db.commit()
                    except Exception:
                        await db.rollback()
                        raise

                await self._load_config_cache()

                self._initialized = True
                log.info(f"SQLite storage initialized at {self._db_path}")

            except Exception as e:
                log.error(f"SQLite initialization failed ({type(e).__name__}).")
                raise

    async def _ensure_schema_compatibility(self, db: aiosqlite.Connection) -> None:
        try:
            for table_name, columns in self.REQUIRED_COLUMNS.items():
                async with db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
                ) as cursor:
                    if not await cursor.fetchone():
                        log.debug(f"Table {table_name} does not exist, will be created")
                        continue

                async with db.execute(f"PRAGMA table_info({table_name})") as cursor:
                    existing_columns = {row[1] for row in await cursor.fetchall()}

                added_count = 0
                added_columns = set()
                for col_name, col_def in columns:
                    if col_name not in existing_columns:
                        await db.execute(
                            f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"
                        )
                        log.info(f"Added missing column {table_name}.{col_name}")
                        added_count += 1
                        added_columns.add(col_name)

                timestamp_columns = added_columns & {"created_at", "updated_at"}
                for column in timestamp_columns:
                    await db.execute(
                        f"UPDATE {table_name} SET {column} = unixepoch() WHERE {column} IS NULL"
                    )

                if added_count > 0:
                    log.info(f"Table {table_name}: added {added_count} missing column(s)")

        except Exception as e:
            log.error(f"Error ensuring schema compatibility: {e}")
            raise

    async def _create_tables(self, db: aiosqlite.Connection):
        await db.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT UNIQUE NOT NULL,
                credential_data TEXT NOT NULL,

                --
                disabled INTEGER DEFAULT 0,
                error_codes TEXT DEFAULT '[]',
                error_messages TEXT DEFAULT '[]',
                last_success REAL,
                user_email TEXT,

                --  CD  (JSON: {model_name: cooldown_timestamp})
                model_cooldowns TEXT DEFAULT '{}',

                -- preview  ( code_assist  true)
                preview INTEGER DEFAULT 1,

                -- tier  ( code_assist  pro)
                tier TEXT DEFAULT 'pro',

                --
                rotation_order INTEGER DEFAULT 0,
                call_count INTEGER DEFAULT 0,

                --
                created_at REAL DEFAULT (unixepoch()),
                updated_at REAL DEFAULT (unixepoch())
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS primary_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT UNIQUE NOT NULL,
                credential_data TEXT NOT NULL,

                --
                disabled INTEGER DEFAULT 0,
                error_codes TEXT DEFAULT '[]',
                error_messages TEXT DEFAULT '[]',
                last_success REAL,
                user_email TEXT,

                --  CD  (JSON: {model_name: cooldown_timestamp})
                model_cooldowns TEXT DEFAULT '{}',

                -- tier  ( pro)
                tier TEXT DEFAULT 'pro',

                --  primary 0/1
                enable_credit INTEGER DEFAULT 0,

                --
                rotation_order INTEGER DEFAULT 0,
                call_count INTEGER DEFAULT 0,

                --
                created_at REAL DEFAULT (unixepoch()),
                updated_at REAL DEFAULT (unixepoch())
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_disabled
            ON credentials(disabled)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_rotation_order
            ON credentials(rotation_order)
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_primary_disabled
            ON primary_credentials(disabled)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_primary_rotation_order
            ON primary_credentials(rotation_order)
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL DEFAULT (unixepoch())
            )
        """)

        log.debug("SQLite tables and indexes created")

    async def _repair_credential_filenames(self, db: aiosqlite.Connection):
        try:
            repaired_count = 0

            async with db.execute("SELECT filename FROM credentials") as cursor:
                rows = await cursor.fetchall()
                for (filename,) in rows:
                    basename = os.path.basename(filename)
                    if basename != filename:
                        async with db.execute(
                            "SELECT COUNT(*) FROM credentials WHERE filename = ?", (basename,)
                        ) as check_cursor:
                            count = (await check_cursor.fetchone())[0]

                        if count == 0:
                            await db.execute(
                                "UPDATE credentials SET filename = ? WHERE filename = ?",
                                (basename, filename),
                            )
                            repaired_count += 1
                            log.info(f"Repaired credential filename: {filename} -> {basename}")
                        else:
                            await db.execute(
                                "DELETE FROM credentials WHERE filename = ?", (filename,)
                            )
                            repaired_count += 1
                            log.warning(
                                f"Removed duplicate credential with path: {filename} (kept {basename})"
                            )

            async with db.execute("SELECT filename FROM primary_credentials") as cursor:
                rows = await cursor.fetchall()
                for (filename,) in rows:
                    basename = os.path.basename(filename)
                    if basename != filename:
                        async with db.execute(
                            "SELECT COUNT(*) FROM primary_credentials WHERE filename = ?",
                            (basename,),
                        ) as check_cursor:
                            count = (await check_cursor.fetchone())[0]

                        if count == 0:
                            await db.execute(
                                "UPDATE primary_credentials SET filename = ? WHERE filename = ?",
                                (basename, filename),
                            )
                            repaired_count += 1
                            log.info(
                                f"Repaired primary credential filename: {filename} -> {basename}"
                            )
                        else:
                            await db.execute(
                                "DELETE FROM primary_credentials WHERE filename = ?", (filename,)
                            )
                            repaired_count += 1
                            log.warning(
                                f"Removed duplicate primary credential with path: {filename} (kept {basename})"
                            )

            if repaired_count > 0:
                log.info(f"Repaired {repaired_count} credential filename(s)")
            else:
                log.debug("No credential filenames need repair")

        except Exception as e:
            log.error(f"Error repairing credential filenames: {e}")
            raise

    async def _load_config_cache(self):
        if self._config_loaded:
            return

        try:
            async with open_sqlite(self._db_path) as db:
                async with db.execute("SELECT key, value FROM config") as cursor:
                    rows = await cursor.fetchall()

                for key, value in rows:
                    try:
                        self._config_cache[key] = json.loads(value)
                    except json.JSONDecodeError:
                        self._config_cache[key] = value

            self._config_loaded = True
            log.debug(f"Loaded {len(self._config_cache)} config items into cache")

        except Exception as e:
            log.error(f"Error loading config cache: {e}")
            self._config_cache = {}

    async def close(self) -> None:
        self._initialized = False
        log.debug("SQLite storage closed")

    def _ensure_initialized(self):
        if not self._initialized:
            raise RuntimeError("SQLite manager not initialized")

    async def create_audit_repository(self, *, cursor_signing_key: bytes) -> "AuditRepository":
        self._ensure_initialized()
        from .audit_sqlite import SQLiteAuditRepository

        repository = SQLiteAuditRepository(
            self._db_path,
            cursor_signing_key=cursor_signing_key,
        )
        await repository.initialize()
        return repository

    async def create_identity_repository(self) -> "IdentityRepository":
        self._ensure_initialized()
        from .identity_sqlite import SQLiteIdentityRepository

        repository = SQLiteIdentityRepository(self._db_path)
        await repository.initialize()
        return repository

    async def create_migration_checkpoint_repository(
        self,
    ) -> "MigrationCheckpointRepository":
        self._ensure_initialized()
        from .migration_sqlite import SQLiteMigrationCheckpointRepository

        repository = SQLiteMigrationCheckpointRepository(self._db_path)
        await repository.initialize()
        return repository

    async def create_request_trace_repository(self, *, cursor_signing_key: bytes):
        self._ensure_initialized()
        from .request_trace_sqlite import SQLiteRequestTraceRepository

        repository = SQLiteRequestTraceRepository(
            self._db_path,
            cursor_signing_key=cursor_signing_key,
        )
        await repository.initialize()
        return repository

    async def create_usage_ledger_repository(self):
        self._ensure_initialized()
        from .usage_ledger_sqlite import SQLiteUsageLedgerRepository

        repository = SQLiteUsageLedgerRepository(self._db_path)
        await repository.initialize()
        await repository.import_legacy_usage(os.path.join(self._credentials_dir, "usage_stats.db"))
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
            async with open_sqlite(self._db_path) as db:
                current_time = time.time()

                if mode == "code_assist":
                    async with db.execute(f"""
                        SELECT filename, credential_data, model_cooldowns, preview
                        FROM {table_name}
                        WHERE disabled = 0
                        ORDER BY call_count ASC,
                                 COALESCE(last_success, 0) ASC,
                                 rotation_order ASC,
                                 filename ASC
                    """) as cursor:
                        rows = await cursor.fetchall()

                        if not model_name:
                            if rows:
                                filename, credential_json, _, _ = rows[0]
                                credential_data = json.loads(credential_json)
                                return filename, credential_data
                            return None

                        is_preview_model = "preview" in model_name.lower()
                        non_preview_creds = []
                        preview_creds = []

                        for filename, credential_json, model_cooldowns_json, preview in rows:
                            model_cooldowns = json.loads(model_cooldowns_json or "{}")
                            model_cooldown = model_cooldowns.get(model_name)
                            if model_cooldown is None or current_time >= model_cooldown:
                                if preview:
                                    preview_creds.append((filename, credential_json))
                                else:
                                    non_preview_creds.append((filename, credential_json))

                        if is_preview_model:
                            if preview_creds:
                                filename, credential_json = preview_creds[0]
                                credential_data = json.loads(credential_json)
                                return filename, credential_data
                        else:
                            if non_preview_creds:
                                filename, credential_json = non_preview_creds[0]
                                credential_data = json.loads(credential_json)
                                return filename, credential_data
                            elif preview_creds:
                                filename, credential_json = preview_creds[0]
                                credential_data = json.loads(credential_json)
                                return filename, credential_data

                        return None
                else:
                    async with db.execute(f"""
                        SELECT filename, credential_data, model_cooldowns, enable_credit
                        FROM {table_name}
                        WHERE disabled = 0
                        ORDER BY call_count ASC,
                                 COALESCE(last_success, 0) ASC,
                                 rotation_order ASC,
                                 filename ASC
                    """) as cursor:
                        rows = await cursor.fetchall()

                        if not model_name:
                            if rows:
                                filename, credential_json, _, enable_credit = rows[0]
                                credential_data = json.loads(credential_json)
                                credential_data["enable_credit"] = bool(enable_credit)
                                return filename, credential_data
                            return None

                        for filename, credential_json, model_cooldowns_json, enable_credit in rows:
                            model_cooldowns = json.loads(model_cooldowns_json or "{}")
                            model_cooldown = model_cooldowns.get(model_name)
                            if model_cooldown is None or current_time >= model_cooldown:
                                credential_data = json.loads(credential_json)
                                credential_data["enable_credit"] = bool(enable_credit)
                                return filename, credential_data

                        return None

        except Exception as e:
            log.error(
                f"Error getting next available credential (mode={mode}, model_name={model_name}): {e}"
            )
            return None

    async def get_available_credentials_list(self) -> List[str]:
        self._ensure_initialized()

        try:
            async with open_sqlite(self._db_path) as db:
                async with db.execute("""
                    SELECT filename
                    FROM credentials
                    WHERE disabled = 0
                    ORDER BY rotation_order ASC
                """) as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]

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
            async with open_sqlite(self._db_path) as db:
                async with db.execute(
                    f"""
                    SELECT disabled, error_codes, last_success, user_email,
                           rotation_order, call_count
                    FROM {table_name} WHERE filename = ?
                """,
                    (filename,),
                ) as cursor:
                    existing = await cursor.fetchone()

                if existing:
                    await db.execute(
                        f"""
                        UPDATE {table_name}
                        SET credential_data = ?,
                            updated_at = unixepoch()
                        WHERE filename = ?
                    """,
                        (json.dumps(credential_data), filename),
                    )
                else:
                    async with db.execute(f"""
                        SELECT COALESCE(MAX(rotation_order), -1) + 1 FROM {table_name}
                    """) as cursor:
                        row = await cursor.fetchone()
                        next_order = row[0]

                    await db.execute(
                        f"""
                        INSERT INTO {table_name}
                        (filename, credential_data, rotation_order, last_success,
                         created_at, updated_at)
                        VALUES (?, ?, ?, ?, unixepoch(), unixepoch())
                    """,
                        (filename, json.dumps(credential_data), next_order, time.time()),
                    )

                await db.commit()
                log.debug(f"Stored credential: {filename} (mode={mode})")
                return True

        except Exception as e:
            log.error(f"Error storing credential {filename}: {e}")
            return False

    async def mutate_credential_pool(
        self, mode: str, planner: CredentialPoolPlanner
    ) -> CredentialPoolMutation:
        """Apply one pool plan while holding SQLite's durable writer lock."""
        self._ensure_initialized()
        mode = normalize_pool_mode(mode)
        table_name = self._get_table_name(mode)
        if not callable(planner):
            raise CredentialPoolMutationError("Credential pool planner is invalid.")
        try:
            async with open_sqlite(self._db_path) as db:
                await db.execute("BEGIN IMMEDIATE")
                try:
                    async with db.execute(
                        f"""SELECT filename, credential_data, user_email, rotation_order
                            FROM {table_name} ORDER BY rotation_order, filename"""
                    ) as cursor:
                        rows = await cursor.fetchall()
                    records = []
                    for filename, payload, user_email, rotation_order in rows:
                        credential_data = json.loads(payload)
                        if type(credential_data) is not dict:
                            raise CredentialPoolMutationError(
                                "Stored credential payload is invalid."
                            )
                        records.append(
                            CredentialPoolRecord(
                                filename=filename,
                                credential_data=credential_data,
                                user_email=user_email,
                                rotation_order=rotation_order,
                            )
                        )
                    mutation = validate_credential_pool_mutation(planner(tuple(records)))
                    for filename in mutation.deletes:
                        await db.execute(
                            f"DELETE FROM {table_name} WHERE filename = ?", (filename,)
                        )
                    next_order = max((record.rotation_order for record in records), default=-1) + 1
                    existing_names = {record.filename for record in records}
                    for write in mutation.writes:
                        if write.filename in existing_names:
                            await db.execute(
                                f"""UPDATE {table_name}
                                    SET credential_data = ?, user_email = ?, updated_at = unixepoch()
                                    WHERE filename = ?""",
                                (
                                    json.dumps(write.credential_data),
                                    write.user_email,
                                    write.filename,
                                ),
                            )
                        else:
                            await db.execute(
                                f"""INSERT INTO {table_name}
                                    (filename, credential_data, user_email, rotation_order,
                                     last_success, created_at, updated_at)
                                    VALUES (?, ?, ?, ?, ?, unixepoch(), unixepoch())""",
                                (
                                    write.filename,
                                    json.dumps(write.credential_data),
                                    write.user_email,
                                    next_order,
                                    time.time(),
                                ),
                            )
                            next_order += 1
                    await db.commit()
                    return mutation
                except BaseException:
                    await db.rollback()
                    raise
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
            async with open_sqlite(self._db_path) as db:
                async with db.execute(
                    f"""
                    SELECT credential_data FROM {table_name} WHERE filename = ?
                """,
                    (filename,),
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return json.loads(row[0])

                return None

        except Exception as e:
            log.error(f"Error getting credential {filename}: {e}")
            return None

    async def list_credentials(self, mode: str = "code_assist") -> List[str]:
        self._ensure_initialized()

        try:
            table_name = self._get_table_name(mode)
            async with open_sqlite(self._db_path) as db:
                async with db.execute(f"""
                    SELECT filename FROM {table_name} ORDER BY rotation_order
                """) as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]

        except Exception as e:
            log.error(f"Error listing credentials: {e}")
            return []

    async def get_all_credentials(self, mode: str = "code_assist") -> Dict[str, Dict[str, Any]]:
        self._ensure_initialized()
        try:
            table_name = self._get_table_name(mode)
            async with open_sqlite(self._db_path) as db:
                async with db.execute(f"""
                    SELECT filename, credential_data
                    FROM {table_name}
                    ORDER BY rotation_order
                """) as cursor:
                    rows = await cursor.fetchall()
            credentials = {}
            for filename, credential_json in rows:
                try:
                    credentials[filename] = json.loads(credential_json)
                except (TypeError, json.JSONDecodeError):
                    log.warning(f"Ignoring invalid credential data for {filename}.")
            return credentials
        except Exception as e:
            log.error(f"Error loading credentials: {e}")
            return {}

    async def delete_credential(self, filename: str, mode: str = "code_assist") -> bool:
        self._ensure_initialized()

        filename = os.path.basename(filename)

        try:
            table_name = self._get_table_name(mode)
            async with open_sqlite(self._db_path) as db:
                await db.execute("PRAGMA secure_delete=ON")
                result = await db.execute(
                    f"""
                    DELETE FROM {table_name} WHERE filename = ?
                """,
                    (filename,),
                )
                deleted_count = result.rowcount
                await result.close()
                await db.commit()

                if deleted_count > 0:
                    try:
                        await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    except Exception as checkpoint_error:
                        log.warning(
                            f"Credential deleted, but the SQLite WAL could not be truncated: {checkpoint_error}"
                        )

                if deleted_count > 0:
                    log.debug(f"Deleted credential: {filename} (mode={mode}).")
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
                f"[DB] update_credential_state start: filename = {filename}, state_updates = {state_updates}, mode = {mode}, table = {table_name}"
            )

            set_clauses = []
            values = []

            for key, value in state_updates.items():
                if key in self.STATE_FIELDS:
                    if key == "enable_credit" and mode != "primary":
                        continue
                    if key in ("error_codes", "error_messages", "model_cooldowns"):
                        set_clauses.append(f"{key} = ?")
                        values.append(json.dumps(value))
                    else:
                        set_clauses.append(f"{key} = ?")
                        values.append(value)

            if not set_clauses:
                log.info("[DB] No status fields to update")
                return True

            set_clauses.append("updated_at = unixepoch()")
            values.append(filename)

            log.debug(f"[DB] SQL parameters: set_clauses = {set_clauses}, values = {values}")

            async with open_sqlite(self._db_path) as db:
                sql_exact = f"""
                    UPDATE {table_name}
                    SET {", ".join(set_clauses)}
                    WHERE filename = ?
                """
                log.debug(f"[DB] Execute Exact Match SQL: {sql_exact}")
                log.debug(f"[DB] SQL parameter value: {values}")

                result = await db.execute(sql_exact, values)
                updated_count = result.rowcount
                log.debug(f"[DB] Exact match rowcount = {updated_count}")

                log.debug(f"[DB] Ready to commit, total update lines = {updated_count}")
                await db.commit()
                log.debug("[DB] commit complete")

                success = updated_count > 0
                log.debug(
                    f"[DB] end of update_credential_state: success = {success}, updated_count = {updated_count}"
                )
                return success

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
            async with open_sqlite(self._db_path) as db:
                if mode == "code_assist":
                    async with db.execute(
                        f"""
                        SELECT disabled, error_codes, last_success, user_email, model_cooldowns,
                               preview, tier, call_count, rotation_order
                        FROM {table_name} WHERE filename = ?
                    """,
                        (filename,),
                    ) as cursor:
                        row = await cursor.fetchone()

                        if row:
                            error_codes_json = row[1] or "[]"
                            model_cooldowns_json = row[4] or "{}"
                            return {
                                "disabled": bool(row[0]),
                                "error_codes": json.loads(error_codes_json),
                                "last_success": row[2] or time.time(),
                                "user_email": row[3],
                                "model_cooldowns": json.loads(model_cooldowns_json),
                                "preview": bool(row[5]) if row[5] is not None else True,
                                "tier": row[6] if row[6] is not None else "pro",
                                "call_count": row[7] or 0,
                                "rotation_order": row[8] or 0,
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
                    async with db.execute(
                        f"""
                        SELECT disabled, error_codes, last_success, user_email, model_cooldowns,
                               tier, enable_credit, call_count, rotation_order
                        FROM {table_name} WHERE filename = ?
                    """,
                        (filename,),
                    ) as cursor:
                        row = await cursor.fetchone()

                        if row:
                            error_codes_json = row[1] or "[]"
                            model_cooldowns_json = row[4] or "{}"
                            return {
                                "disabled": bool(row[0]),
                                "error_codes": json.loads(error_codes_json),
                                "last_success": row[2] or time.time(),
                                "user_email": row[3],
                                "model_cooldowns": json.loads(model_cooldowns_json),
                                "tier": row[5] if row[5] is not None else "pro",
                                "enable_credit": bool(row[6]) if row[6] is not None else False,
                                "call_count": row[7] or 0,
                                "rotation_order": row[8] or 0,
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
            async with open_sqlite(self._db_path) as db:
                if mode == "code_assist":
                    async with db.execute(f"""
                        SELECT filename, disabled, error_codes, last_success,
                               user_email, model_cooldowns, preview, tier,
                               call_count, rotation_order
                        FROM {table_name}
                    """) as cursor:
                        rows = await cursor.fetchall()

                        states = {}
                        current_time = time.time()

                        for row in rows:
                            filename = row[0]
                            error_codes_json = row[2] or "[]"
                            model_cooldowns_json = row[5] or "{}"
                            model_cooldowns = json.loads(model_cooldowns_json)

                            if model_cooldowns:
                                model_cooldowns = {
                                    k: v for k, v in model_cooldowns.items() if v > current_time
                                }

                            states[filename] = {
                                "disabled": bool(row[1]),
                                "error_codes": json.loads(error_codes_json),
                                "last_success": row[3] or time.time(),
                                "user_email": row[4],
                                "model_cooldowns": model_cooldowns,
                                "preview": bool(row[6]) if row[6] is not None else True,
                                "tier": row[7] if row[7] is not None else "pro",
                                "call_count": row[8] or 0,
                                "rotation_order": row[9] or 0,
                            }

                        return states
                else:
                    async with db.execute(f"""
                        SELECT filename, disabled, error_codes, last_success,
                               user_email, model_cooldowns, tier, enable_credit,
                               call_count, rotation_order
                        FROM {table_name}
                    """) as cursor:
                        rows = await cursor.fetchall()

                        states = {}
                        current_time = time.time()

                        for row in rows:
                            filename = row[0]
                            error_codes_json = row[2] or "[]"
                            model_cooldowns_json = row[5] or "{}"
                            model_cooldowns = json.loads(model_cooldowns_json)

                            if model_cooldowns:
                                model_cooldowns = {
                                    k: v for k, v in model_cooldowns.items() if v > current_time
                                }

                            states[filename] = {
                                "disabled": bool(row[1]),
                                "error_codes": json.loads(error_codes_json),
                                "last_success": row[3] or time.time(),
                                "user_email": row[4],
                                "model_cooldowns": model_cooldowns,
                                "tier": row[6] if row[6] is not None else "pro",
                                "enable_credit": bool(row[7]) if row[7] is not None else False,
                                "call_count": row[8] or 0,
                                "rotation_order": row[9] or 0,
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

            async with open_sqlite(self._db_path) as db:
                global_stats = {"total": 0, "normal": 0, "disabled": 0}
                async with db.execute(f"""
                    SELECT disabled, COUNT(*) FROM {table_name} GROUP BY disabled
                """) as stats_cursor:
                    stats_rows = await stats_cursor.fetchall()
                    for disabled, count in stats_rows:
                        global_stats["total"] += count
                        if disabled:
                            global_stats["disabled"] = count
                        else:
                            global_stats["normal"] = count

                where_clauses = []
                count_params = []

                if status_filter == "enabled":
                    where_clauses.append("disabled = 0")
                elif status_filter == "disabled":
                    where_clauses.append("disabled = 1")

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

                where_clause = ""
                if where_clauses:
                    where_clause = "WHERE " + " AND ".join(where_clauses)

                if mode == "code_assist":
                    all_query = f"""
                        SELECT filename, disabled, error_codes, last_success,
                               user_email, rotation_order, model_cooldowns, preview, tier
                        FROM {table_name}
                        {where_clause}
                        ORDER BY rotation_order
                    """
                else:
                    all_query = f"""
                        SELECT filename, disabled, error_codes, last_success,
                               user_email, rotation_order, model_cooldowns, tier, enable_credit
                        FROM {table_name}
                        {where_clause}
                        ORDER BY rotation_order
                    """

                async with db.execute(all_query, count_params) as cursor:
                    all_rows = await cursor.fetchall()

                    current_time = time.time()
                    all_summaries = []

                    for row in all_rows:
                        filename = row[0]
                        error_codes_json = row[2] or "[]"
                        model_cooldowns_json = row[6] or "{}"
                        model_cooldowns = json.loads(model_cooldowns_json)

                        active_cooldowns = {}
                        if model_cooldowns:
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
                            "filename": filename,
                            "disabled": bool(row[1]),
                            "error_codes": error_codes,
                            "last_success": row[3] or current_time,
                            "user_email": row[4],
                            "rotation_order": row[5],
                            "model_cooldowns": active_cooldowns,
                            "tier": row[8]
                            if mode == "code_assist" and row[8] is not None
                            else (
                                row[7] if mode != "code_assist" and row[7] is not None else "pro"
                            ),
                        }

                        if mode != "code_assist":
                            summary["enable_credit"] = bool(row[8]) if row[8] is not None else False

                        if mode == "code_assist":
                            summary["preview"] = bool(row[7]) if row[7] is not None else True

                            if preview_filter:
                                preview_value = summary.get("preview", True)
                                if preview_filter == "preview" and not preview_value:
                                    continue
                                elif preview_filter == "no_preview" and preview_value:
                                    continue

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

            async with open_sqlite(self._db_path) as db:
                query = f"""
                    SELECT filename, user_email
                    FROM {table_name}
                    ORDER BY filename
                """

                async with db.execute(query) as cursor:
                    rows = await cursor.fetchall()

                    email_to_files = {}
                    no_email_files = []

                    for filename, user_email in rows:
                        if user_email:
                            if user_email not in email_to_files:
                                email_to_files[user_email] = []
                            email_to_files[user_email].append(filename)
                        else:
                            no_email_files.append(filename)

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
            async with open_sqlite(self._db_path) as db:
                await db.execute(
                    """
                    INSERT INTO config (key, value, updated_at)
                    VALUES (?, ?, unixepoch())
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                """,
                    (key, json.dumps(value)),
                )
                await db.commit()

            self._config_cache[key] = value
            return True

        except Exception as e:
            log.error(f"Error setting config {key}: {e}")
            return False

    async def reload_config_cache(self):
        self._ensure_initialized()
        self._config_cache = {}
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
            async with open_sqlite(self._db_path) as db:
                await db.execute("DELETE FROM config WHERE key = ?", (key,))
                await db.commit()

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
            async with open_sqlite(self._db_path) as db:
                async with db.execute(
                    f"""
                    SELECT error_codes, error_messages FROM {table_name} WHERE filename = ?
                """,
                    (filename,),
                ) as cursor:
                    row = await cursor.fetchone()

                    if row:
                        error_codes_json = row[0] or "[]"
                        error_messages_json = row[1] or "[]"
                        return {
                            "filename": filename,
                            "error_codes": json.loads(error_codes_json),
                            "error_messages": json.loads(error_messages_json),
                        }

                return {
                    "filename": filename,
                    "error_codes": [],
                    "error_messages": [],
                }

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
            async with open_sqlite(self._db_path) as db:
                async with db.execute(
                    f"""
                    SELECT model_cooldowns FROM {table_name} WHERE filename = ?
                """,
                    (filename,),
                ) as cursor:
                    row = await cursor.fetchone()

                    if not row:
                        log.warning(f"Credential {filename} not found")
                        return False

                    model_cooldowns = json.loads(row[0] or "{}")

                    if cooldown_until is None:
                        model_cooldowns.pop(model_name, None)
                    else:
                        model_cooldowns[model_name] = cooldown_until

                    await db.execute(
                        f"""
                        UPDATE {table_name}
                        SET model_cooldowns = ?,
                            updated_at = unixepoch()
                        WHERE filename = ?
                    """,
                        (json.dumps(model_cooldowns), filename),
                    )
                    await db.commit()

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
            async with open_sqlite(self._db_path) as db:
                result = await db.execute(
                    f"""
                    UPDATE {table_name}
                    SET model_cooldowns = '{{}}',
                        updated_at = unixepoch()
                    WHERE filename = ?
                """,
                    (filename,),
                )
                updated_count = result.rowcount
                await db.commit()

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
            async with open_sqlite(self._db_path) as db:
                await db.execute(
                    f"""
                    UPDATE {table_name}
                    SET last_success = unixepoch(),
                        call_count = COALESCE(call_count, 0) + ?,
                        error_codes = '[]',
                        error_messages = '{{}}',
                        updated_at = unixepoch()
                    WHERE filename = ?
                """,
                    (call_increment, filename),
                )

                if model_name:
                    async with db.execute(
                        f"""
                        SELECT model_cooldowns FROM {table_name} WHERE filename = ?
                    """,
                        (filename,),
                    ) as cursor:
                        row = await cursor.fetchone()
                        if row:
                            cooldowns = json.loads(row[0] or "{}")
                            if model_name in cooldowns:
                                cooldowns.pop(model_name)
                                await db.execute(
                                    f"""
                                    UPDATE {table_name}
                                    SET model_cooldowns = ?, updated_at = unixepoch()
                                    WHERE filename = ?
                                """,
                                    (json.dumps(cooldowns), filename),
                                )

                await db.commit()

        except Exception as e:
            log.error(f"Error recording success for {filename}: {e}")

    async def record_failure(self, filename: str, mode: str = "code_assist") -> None:
        """Count failed attempts so routing fairness includes all upstream traffic."""
        self._ensure_initialized()
        filename = os.path.basename(filename)

        try:
            table_name = self._get_table_name(mode)
            async with open_sqlite(self._db_path) as db:
                await db.execute(
                    f"""
                    UPDATE {table_name}
                    SET call_count = COALESCE(call_count, 0) + 1,
                        updated_at = unixepoch()
                    WHERE filename = ?
                    """,
                    (filename,),
                )
                await db.commit()
        except Exception as e:
            log.error(f"Error recording failure for {filename}: {e}")
