"""SQLite repository for durable management identities and role bindings."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
from core.identity import ManagementRole
from core.identity.repository import (
    IDENTITY_MIGRATION_ID,
    IDENTITY_SCHEMA_VERSION,
    LOCAL_OWNER_ID,
    MAX_IDENTITY_PAGE_SIZE,
    IdentityAlreadyExists,
    IdentityMigrationRecord,
    IdentityNotFound,
    IdentityOwnerInvariant,
    IdentityPageCursor,
    IdentityRecord,
    IdentityRevisionConflict,
    IdentityStoreCorrupt,
    ManagedIdentity,
    OidcPolicyRevisionRecord,
    RoleBindingRecord,
    RoleBindingSource,
    identity_from_record,
    migration_from_record,
    oidc_policy_revision_from_record,
    role_binding_from_record,
)
from core.storage.sqlite_runtime import open_sqlite

_IDENTITY_COLUMNS = (
    "schema_version",
    "identity_id",
    "principal_type",
    "issuer",
    "subject",
    "enabled",
    "revision",
    "authorization_epoch",
    "created_at",
    "updated_at",
)
_BINDING_COLUMNS = (
    "schema_version",
    "binding_id",
    "identity_id",
    "role",
    "source",
    "revision",
    "created_at",
    "updated_at",
)


class SQLiteIdentityRepository:
    """Additive, fail-closed SQLite implementation of the identity contract."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._database_path = str(database_path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._initialized = False
        self._initialize_lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._initialize_lock:
            self._initialized = False
            try:
                async with open_sqlite(self._database_path) as db:
                    db.row_factory = aiosqlite.Row
                    await db.execute("PRAGMA journal_mode=WAL")
                    await db.execute("BEGIN IMMEDIATE")
                    try:
                        await self._create_schema(db)
                        await self._bootstrap(db)
                        await self._validate_store(db)
                        await db.commit()
                    except Exception:
                        await db.rollback()
                        raise
            except IdentityStoreCorrupt:
                raise
            except Exception as exc:
                raise IdentityStoreCorrupt("Management identity store is invalid.") from exc
            self._initialized = True

    @staticmethod
    async def _create_schema(db: aiosqlite.Connection) -> None:
        await db.execute(f"""
            CREATE TABLE IF NOT EXISTS management_identities (
                schema_version INTEGER NOT NULL CHECK(schema_version = {IDENTITY_SCHEMA_VERSION}),
                identity_id TEXT NOT NULL PRIMARY KEY,
                principal_type TEXT NOT NULL CHECK(principal_type IN ('local_owner', 'oidc_user')),
                issuer TEXT COLLATE BINARY,
                subject TEXT COLLATE BINARY,
                enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
                revision INTEGER NOT NULL CHECK(revision >= 1),
                authorization_epoch INTEGER NOT NULL CHECK(authorization_epoch >= 1),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(issuer, subject),
                CHECK(
                    (principal_type = 'local_owner' AND identity_id = 'local-owner'
                     AND issuer IS NULL AND subject IS NULL AND enabled = 1)
                    OR
                    (principal_type = 'oidc_user' AND issuer IS NOT NULL AND subject IS NOT NULL)
                )
            )
        """)
        await db.execute(f"""
            CREATE TABLE IF NOT EXISTS management_role_bindings (
                schema_version INTEGER NOT NULL CHECK(schema_version = {IDENTITY_SCHEMA_VERSION}),
                binding_id TEXT NOT NULL PRIMARY KEY,
                identity_id TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL CHECK(role IN ('viewer', 'operator', 'security_admin', 'owner')),
                source TEXT NOT NULL CHECK(source IN (
                    'local_bootstrap', 'direct_binding', 'claim_mapping'
                )),
                revision INTEGER NOT NULL CHECK(revision >= 1),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(identity_id) REFERENCES management_identities(identity_id)
                    ON DELETE RESTRICT,
                CHECK(source != 'claim_mapping' OR role != 'owner')
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_management_identity_oidc
            ON management_identities(issuer, subject)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_management_identity_order
            ON management_identities(created_at, identity_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_management_binding_identity
            ON management_role_bindings(identity_id)
        """)
        await db.execute(f"""
            CREATE TABLE IF NOT EXISTS oidc_policy_revision (
                singleton_id INTEGER NOT NULL PRIMARY KEY CHECK(singleton_id = 1),
                schema_version INTEGER NOT NULL CHECK(schema_version = {IDENTITY_SCHEMA_VERSION}),
                revision INTEGER NOT NULL CHECK(revision >= 1),
                authorization_epoch INTEGER NOT NULL CHECK(authorization_epoch >= 1),
                updated_at TEXT NOT NULL
            )
        """)
        await db.execute(f"""
            CREATE TABLE IF NOT EXISTS identity_migrations (
                migration_id TEXT NOT NULL PRIMARY KEY,
                schema_version INTEGER NOT NULL CHECK(schema_version = {IDENTITY_SCHEMA_VERSION}),
                applied_at TEXT NOT NULL
            )
        """)

    async def _bootstrap(self, db: aiosqlite.Connection) -> None:
        now = self._clock()
        owner = IdentityRecord.local_owner(now=now).to_record()
        binding = RoleBindingRecord.local_owner(now=now).to_record()
        policy = OidcPolicyRevisionRecord.initial(now=now).to_record()
        migration = IdentityMigrationRecord.applied(now=now).to_record()
        await db.execute(
            f"INSERT OR IGNORE INTO management_identities "
            f"({', '.join(_IDENTITY_COLUMNS)}) VALUES ({', '.join('?' for _ in _IDENTITY_COLUMNS)})",
            self._identity_values(owner),
        )
        await db.execute(
            f"INSERT OR IGNORE INTO management_role_bindings "
            f"({', '.join(_BINDING_COLUMNS)}) VALUES ({', '.join('?' for _ in _BINDING_COLUMNS)})",
            tuple(binding[column] for column in _BINDING_COLUMNS),
        )
        await db.execute(
            """
            INSERT OR IGNORE INTO oidc_policy_revision
                (singleton_id, schema_version, revision, authorization_epoch, updated_at)
            VALUES (1, ?, ?, ?, ?)
            """,
            (
                policy["schema_version"],
                policy["revision"],
                policy["authorization_epoch"],
                policy["updated_at"],
            ),
        )
        await db.execute(
            """
            INSERT OR IGNORE INTO identity_migrations
                (migration_id, schema_version, applied_at)
            VALUES (?, ?, ?)
            """,
            (
                migration["migration_id"],
                migration["schema_version"],
                migration["applied_at"],
            ),
        )

    async def _validate_store(self, db: aiosqlite.Connection) -> None:
        async with db.execute(
            f"SELECT {self._joined_columns()} FROM management_identities AS i "
            "LEFT JOIN management_role_bindings AS b ON b.identity_id = i.identity_id"
        ) as cursor:
            rows = await cursor.fetchall()
        managed = [self._managed_from_row(row) for row in rows]
        async with db.execute("SELECT COUNT(*) FROM management_role_bindings") as cursor:
            binding_count = int((await cursor.fetchone())[0])
        if binding_count != len(managed):
            raise IdentityStoreCorrupt("Management identity store is invalid.")
        owners = [item for item in managed if item.identity.identity_id == LOCAL_OWNER_ID]
        if len(owners) != 1:
            raise IdentityStoreCorrupt("Management identity store is invalid.")
        await self._policy_from_db(db)
        await self._migration_from_db(db)

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("SQLite identity repository is not initialized.")

    @staticmethod
    async def _prepare_connection(db: aiosqlite.Connection) -> None:
        db.row_factory = aiosqlite.Row

    async def get_identity(self, identity_id: str) -> ManagedIdentity | None:
        self._ensure_initialized()
        self._validate_lookup_id(identity_id)
        async with open_sqlite(self._database_path) as db:
            await self._prepare_connection(db)
            return await self._get_identity(db, identity_id)

    async def get_identity_by_oidc(self, *, issuer: str, subject: str) -> ManagedIdentity | None:
        self._ensure_initialized()
        self._validate_oidc_pair(issuer, subject)
        async with open_sqlite(self._database_path) as db:
            await self._prepare_connection(db)
            async with db.execute(
                f"SELECT {self._joined_columns()} FROM management_identities AS i "
                "JOIN management_role_bindings AS b ON b.identity_id = i.identity_id "
                "WHERE i.issuer = ? COLLATE BINARY AND i.subject = ? COLLATE BINARY",
                (issuer, subject),
            ) as cursor:
                row = await cursor.fetchone()
        return None if row is None else self._managed_from_row(row)

    async def list_identities(
        self, *, limit: int = 100, after: IdentityPageCursor | None = None
    ) -> list[ManagedIdentity]:
        self._ensure_initialized()
        if type(limit) is not int or not 1 <= limit <= MAX_IDENTITY_PAGE_SIZE:
            raise ValueError("Identity page size is invalid.")
        if after is not None and type(after) is not IdentityPageCursor:
            raise ValueError("Identity cursor is invalid.")
        where = ""
        parameters: tuple[object, ...] = (limit,)
        if after is not None:
            where = (
                "WHERE (i.created_at > ? COLLATE BINARY OR "
                "(i.created_at = ? COLLATE BINARY AND i.identity_id > ? COLLATE BINARY)) "
            )
            parameters = (after.created_at, after.created_at, after.identity_id, limit)
        async with open_sqlite(self._database_path) as db:
            await self._prepare_connection(db)
            async with db.execute(
                f"SELECT {self._joined_columns()} FROM management_identities AS i "
                "JOIN management_role_bindings AS b ON b.identity_id = i.identity_id "
                f"{where}ORDER BY i.created_at ASC, i.identity_id ASC LIMIT ?",
                parameters,
            ) as cursor:
                rows = await cursor.fetchall()
        return [self._managed_from_row(row) for row in rows]

    async def create_oidc_identity(
        self,
        *,
        issuer: str,
        subject: str,
        role: ManagementRole,
        source: RoleBindingSource = RoleBindingSource.DIRECT_BINDING,
    ) -> ManagedIdentity:
        self._ensure_initialized()
        now = self._clock()
        identity = IdentityRecord.oidc_user(
            identity_id=f"idn_{uuid.uuid4().hex}",
            issuer=issuer,
            subject=subject,
            now=now,
        )
        binding = RoleBindingRecord.oidc_user(
            binding_id=f"rbd_{uuid.uuid4().hex}",
            identity_id=identity.identity_id,
            role=role,
            source=source,
            now=now,
        )
        try:
            async with open_sqlite(self._database_path) as db:
                await self._prepare_connection(db)
                await db.execute("BEGIN IMMEDIATE")
                try:
                    await self._insert_identity(db, identity)
                    await self._insert_binding(db, binding)
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise
        except aiosqlite.IntegrityError as exc:
            raise IdentityAlreadyExists("Management identity already exists.") from exc
        return ManagedIdentity(identity=identity, binding=binding)

    async def set_identity_enabled(
        self, *, identity_id: str, enabled: bool, expected_revision: int
    ) -> ManagedIdentity:
        self._ensure_initialized()
        self._validate_lookup_id(identity_id)
        self._validate_revision(expected_revision)
        if type(enabled) is not bool:
            raise ValueError("Identity enabled state is invalid.")
        if identity_id == LOCAL_OWNER_ID and not enabled:
            raise IdentityOwnerInvariant("The local owner must remain enabled.")
        async with open_sqlite(self._database_path) as db:
            await self._prepare_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            try:
                current = await self._required_identity(db, identity_id)
                self._require_revision(current.identity.revision, expected_revision)
                timestamp = self._utc_now_text()
                cursor = await db.execute(
                    """
                    UPDATE management_identities
                    SET enabled = ?, revision = revision + 1,
                        authorization_epoch = authorization_epoch + 1, updated_at = ?
                    WHERE identity_id = ? AND revision = ?
                    """,
                    (int(enabled), timestamp, identity_id, expected_revision),
                )
                if cursor.rowcount != 1:
                    raise IdentityRevisionConflict("Identity revision conflict.")
                await db.commit()
            except Exception:
                await db.rollback()
                raise
        return await self._required_after_commit(identity_id)

    async def set_role(
        self,
        *,
        identity_id: str,
        role: ManagementRole,
        source: RoleBindingSource,
        expected_revision: int,
    ) -> ManagedIdentity:
        self._ensure_initialized()
        self._validate_lookup_id(identity_id)
        self._validate_revision(expected_revision)
        if type(role) is not ManagementRole or type(source) is not RoleBindingSource:
            raise ValueError("Role binding is invalid.")
        if identity_id == LOCAL_OWNER_ID:
            raise IdentityOwnerInvariant("The local-owner role binding is immutable.")
        async with open_sqlite(self._database_path) as db:
            await self._prepare_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            try:
                current = await self._required_identity(db, identity_id)
                RoleBindingRecord.oidc_user(
                    binding_id=current.binding.binding_id,
                    identity_id=identity_id,
                    role=role,
                    source=source,
                    now=self._clock(),
                )
                self._require_revision(current.binding.revision, expected_revision)
                timestamp = self._utc_now_text()
                binding_cursor = await db.execute(
                    """
                    UPDATE management_role_bindings
                    SET role = ?, source = ?, revision = revision + 1, updated_at = ?
                    WHERE identity_id = ? AND revision = ?
                    """,
                    (role.value, source.value, timestamp, identity_id, expected_revision),
                )
                identity_cursor = await db.execute(
                    """
                    UPDATE management_identities
                    SET revision = revision + 1,
                        authorization_epoch = authorization_epoch + 1, updated_at = ?
                    WHERE identity_id = ? AND revision = ?
                    """,
                    (timestamp, identity_id, current.identity.revision),
                )
                if binding_cursor.rowcount != 1 or identity_cursor.rowcount != 1:
                    raise IdentityRevisionConflict("Identity revision conflict.")
                await db.commit()
            except Exception:
                await db.rollback()
                raise
        return await self._required_after_commit(identity_id)

    async def get_oidc_policy_revision(self) -> OidcPolicyRevisionRecord:
        self._ensure_initialized()
        async with open_sqlite(self._database_path) as db:
            await self._prepare_connection(db)
            return await self._policy_from_db(db)

    async def advance_oidc_policy_revision(
        self, *, expected_revision: int
    ) -> OidcPolicyRevisionRecord:
        self._ensure_initialized()
        self._validate_revision(expected_revision)
        async with open_sqlite(self._database_path) as db:
            await self._prepare_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            try:
                current = await self._policy_from_db(db)
                self._require_revision(current.revision, expected_revision)
                cursor = await db.execute(
                    """
                    UPDATE oidc_policy_revision
                    SET revision = revision + 1,
                        authorization_epoch = authorization_epoch + 1, updated_at = ?
                    WHERE singleton_id = 1 AND revision = ?
                    """,
                    (self._utc_now_text(), expected_revision),
                )
                if cursor.rowcount != 1:
                    raise IdentityRevisionConflict("OIDC policy revision conflict.")
                await db.commit()
            except Exception:
                await db.rollback()
                raise
        return await self.get_oidc_policy_revision()

    async def get_migration(self) -> IdentityMigrationRecord:
        self._ensure_initialized()
        async with open_sqlite(self._database_path) as db:
            await self._prepare_connection(db)
            return await self._migration_from_db(db)

    async def _get_identity(
        self, db: aiosqlite.Connection, identity_id: str
    ) -> ManagedIdentity | None:
        async with db.execute(
            f"SELECT {self._joined_columns()} FROM management_identities AS i "
            "JOIN management_role_bindings AS b ON b.identity_id = i.identity_id "
            "WHERE i.identity_id = ?",
            (identity_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return None if row is None else self._managed_from_row(row)

    async def _required_identity(
        self, db: aiosqlite.Connection, identity_id: str
    ) -> ManagedIdentity:
        found = await self._get_identity(db, identity_id)
        if found is None:
            raise IdentityNotFound("Management identity was not found.")
        return found

    async def _required_after_commit(self, identity_id: str) -> ManagedIdentity:
        found = await self.get_identity(identity_id)
        if found is None:
            raise IdentityStoreCorrupt("Management identity store is invalid.")
        return found

    @staticmethod
    async def _insert_identity(db: aiosqlite.Connection, identity: IdentityRecord) -> None:
        record = identity.to_record()
        await db.execute(
            f"INSERT INTO management_identities ({', '.join(_IDENTITY_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in _IDENTITY_COLUMNS)})",
            SQLiteIdentityRepository._identity_values(record),
        )

    @staticmethod
    async def _insert_binding(db: aiosqlite.Connection, binding: RoleBindingRecord) -> None:
        record = binding.to_record()
        await db.execute(
            f"INSERT INTO management_role_bindings ({', '.join(_BINDING_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in _BINDING_COLUMNS)})",
            tuple(record[column] for column in _BINDING_COLUMNS),
        )

    @staticmethod
    def _identity_values(record: dict[str, object]) -> tuple[object, ...]:
        return tuple(
            int(record[column]) if column == "enabled" else record[column]
            for column in _IDENTITY_COLUMNS
        )

    @staticmethod
    def _joined_columns() -> str:
        identity = ", ".join(f"i.{column} AS i_{column}" for column in _IDENTITY_COLUMNS)
        binding = ", ".join(f"b.{column} AS b_{column}" for column in _BINDING_COLUMNS)
        return f"{identity}, {binding}"

    @staticmethod
    def _managed_from_row(row: aiosqlite.Row) -> ManagedIdentity:
        try:
            identity_values = {column: row[f"i_{column}"] for column in _IDENTITY_COLUMNS}
            if identity_values["enabled"] not in (0, 1):
                raise ValueError("Stored identity enabled state is invalid.")
            identity_values["enabled"] = bool(identity_values["enabled"])
            binding_values = {column: row[f"b_{column}"] for column in _BINDING_COLUMNS}
            return ManagedIdentity(
                identity=identity_from_record(identity_values),
                binding=role_binding_from_record(binding_values),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise IdentityStoreCorrupt("Management identity store is invalid.") from exc

    @staticmethod
    async def _policy_from_db(
        db: aiosqlite.Connection,
    ) -> OidcPolicyRevisionRecord:
        async with db.execute(
            """
            SELECT schema_version, revision, authorization_epoch, updated_at
            FROM oidc_policy_revision WHERE singleton_id = 1
            """
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise IdentityStoreCorrupt("Management identity store is invalid.")
        try:
            return oidc_policy_revision_from_record(dict(row))
        except (TypeError, ValueError) as exc:
            raise IdentityStoreCorrupt("Management identity store is invalid.") from exc

    @staticmethod
    async def _migration_from_db(db: aiosqlite.Connection) -> IdentityMigrationRecord:
        async with db.execute(
            """
            SELECT migration_id, schema_version, applied_at
            FROM identity_migrations WHERE migration_id = ?
            """,
            (IDENTITY_MIGRATION_ID,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise IdentityStoreCorrupt("Management identity store is invalid.")
        try:
            return migration_from_record(dict(row))
        except (TypeError, ValueError) as exc:
            raise IdentityStoreCorrupt("Management identity store is invalid.") from exc

    @staticmethod
    def _validate_lookup_id(identity_id: object) -> None:
        if identity_id == LOCAL_OWNER_ID:
            return
        if (
            type(identity_id) is not str
            or len(identity_id) != 36
            or not identity_id.startswith("idn_")
            or any(character not in "0123456789abcdef" for character in identity_id[4:])
        ):
            raise ValueError("Identity identifier is invalid.")

    @staticmethod
    def _validate_oidc_pair(issuer: object, subject: object) -> None:
        IdentityRecord.oidc_user(
            identity_id="idn_00000000000000000000000000000000",
            issuer=issuer,
            subject=subject,
            now=datetime.now(timezone.utc),
        )

    @staticmethod
    def _validate_revision(value: object) -> None:
        if type(value) is not int or value < 1:
            raise ValueError("Expected revision is invalid.")

    @staticmethod
    def _require_revision(actual: int, expected: int) -> None:
        if actual != expected:
            raise IdentityRevisionConflict("Identity revision conflict.")

    def _utc_now_text(self) -> str:
        now = self._clock()
        if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Timestamp is invalid.")
        return now.astimezone(timezone.utc).isoformat()
