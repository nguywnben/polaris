"""PostgreSQL repository for durable management identities and role bindings."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

import asyncpg
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
_IDENTITY_SCHEMA_LOCK_ID = 0x4F4D4E4949445631


class PostgreSQLIdentityRepository:
    """Additive, fail-closed PostgreSQL implementation of the identity contract."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._pool = pool
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._initialized = False
        self._initialize_lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._initialize_lock:
            self._initialized = False
            try:
                async with self._pool.acquire() as connection:
                    async with connection.transaction():
                        # Multiple replicas may initialize the additive schema at
                        # the same instant. PostgreSQL's IF NOT EXISTS does not
                        # serialize the related table/index/bootstrap lock graph.
                        await connection.execute(
                            "SELECT pg_advisory_xact_lock($1)",
                            _IDENTITY_SCHEMA_LOCK_ID,
                        )
                        await self._create_schema(connection)
                        await self._bootstrap(connection)
                        await self._validate_store(connection)
            except IdentityStoreCorrupt:
                raise
            except Exception as exc:
                raise IdentityStoreCorrupt("Management identity store is invalid.") from exc
            self._initialized = True

    @staticmethod
    async def _create_schema(connection: asyncpg.Connection) -> None:
        await connection.execute(f"""
            CREATE TABLE IF NOT EXISTS management_identities (
                schema_version INTEGER NOT NULL CHECK (schema_version = {IDENTITY_SCHEMA_VERSION}),
                identity_id TEXT NOT NULL PRIMARY KEY,
                principal_type TEXT NOT NULL
                    CHECK (principal_type IN ('local_owner', 'oidc_user')),
                issuer TEXT COLLATE "C",
                subject TEXT COLLATE "C",
                enabled BOOLEAN NOT NULL,
                revision INTEGER NOT NULL CHECK (revision >= 1),
                authorization_epoch INTEGER NOT NULL CHECK (authorization_epoch >= 1),
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                UNIQUE (issuer, subject),
                CHECK (
                    (principal_type = 'local_owner' AND identity_id = 'local-owner'
                     AND issuer IS NULL AND subject IS NULL AND enabled)
                    OR
                    (principal_type = 'oidc_user' AND issuer IS NOT NULL AND subject IS NOT NULL)
                )
            )
        """)
        await connection.execute(f"""
            CREATE TABLE IF NOT EXISTS management_role_bindings (
                schema_version INTEGER NOT NULL CHECK (schema_version = {IDENTITY_SCHEMA_VERSION}),
                binding_id TEXT NOT NULL PRIMARY KEY,
                identity_id TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL
                    CHECK (role IN ('owner', 'security_admin', 'operator', 'viewer')),
                source TEXT NOT NULL
                    CHECK (source IN ('local_bootstrap', 'direct_binding', 'claim_mapping')),
                revision INTEGER NOT NULL CHECK (revision >= 1),
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                FOREIGN KEY (identity_id) REFERENCES management_identities(identity_id)
                    ON DELETE RESTRICT,
                CHECK (source != 'claim_mapping' OR role != 'owner')
            )
        """)
        await connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_management_identity_oidc
            ON management_identities (issuer, subject)
        """)
        await connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_management_identity_order
            ON management_identities (created_at, identity_id)
        """)
        await connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_management_binding_identity
            ON management_role_bindings (identity_id)
        """)
        await connection.execute(f"""
            CREATE TABLE IF NOT EXISTS oidc_policy_revision (
                singleton_id INTEGER NOT NULL PRIMARY KEY CHECK (singleton_id = 1),
                schema_version INTEGER NOT NULL CHECK (schema_version = {IDENTITY_SCHEMA_VERSION}),
                revision INTEGER NOT NULL CHECK (revision >= 1),
                authorization_epoch INTEGER NOT NULL CHECK (authorization_epoch >= 1),
                updated_at TIMESTAMPTZ NOT NULL
            )
        """)
        await connection.execute(f"""
            CREATE TABLE IF NOT EXISTS identity_migrations (
                migration_id TEXT NOT NULL PRIMARY KEY,
                schema_version INTEGER NOT NULL CHECK (schema_version = {IDENTITY_SCHEMA_VERSION}),
                applied_at TIMESTAMPTZ NOT NULL
            )
        """)

    async def _bootstrap(self, connection: asyncpg.Connection) -> None:
        now = self._clock()
        owner = IdentityRecord.local_owner(now=now).to_record()
        binding = RoleBindingRecord.local_owner(now=now).to_record()
        policy = OidcPolicyRevisionRecord.initial(now=now).to_record()
        migration = IdentityMigrationRecord.applied(now=now).to_record()
        await connection.execute(
            f"INSERT INTO management_identities ({', '.join(_IDENTITY_COLUMNS)}) "
            f"VALUES ({self._placeholders(len(_IDENTITY_COLUMNS))}) ON CONFLICT DO NOTHING",
            *self._identity_values(owner),
        )
        await connection.execute(
            f"INSERT INTO management_role_bindings ({', '.join(_BINDING_COLUMNS)}) "
            f"VALUES ({self._placeholders(len(_BINDING_COLUMNS))}) ON CONFLICT DO NOTHING",
            *self._database_values(binding, _BINDING_COLUMNS),
        )
        await connection.execute(
            """
            INSERT INTO oidc_policy_revision
                (singleton_id, schema_version, revision, authorization_epoch, updated_at)
            VALUES (1, $1, $2, $3, $4) ON CONFLICT DO NOTHING
            """,
            policy["schema_version"],
            policy["revision"],
            policy["authorization_epoch"],
            self._timestamp_value(policy["updated_at"]),
        )
        await connection.execute(
            """
            INSERT INTO identity_migrations (migration_id, schema_version, applied_at)
            VALUES ($1, $2, $3) ON CONFLICT DO NOTHING
            """,
            migration["migration_id"],
            migration["schema_version"],
            self._timestamp_value(migration["applied_at"]),
        )

    async def _validate_store(self, connection: asyncpg.Connection) -> None:
        rows = await connection.fetch(
            f"SELECT {self._joined_columns()} FROM management_identities AS i "
            "LEFT JOIN management_role_bindings AS b ON b.identity_id = i.identity_id"
        )
        managed = [self._managed_from_row(row) for row in rows]
        binding_count = await connection.fetchval("SELECT COUNT(*) FROM management_role_bindings")
        if type(binding_count) is not int or binding_count != len(managed):
            raise IdentityStoreCorrupt("Management identity store is invalid.")
        owners = [item for item in managed if item.identity.identity_id == LOCAL_OWNER_ID]
        if len(owners) != 1:
            raise IdentityStoreCorrupt("Management identity store is invalid.")
        await self._policy_from_connection(connection)
        await self._migration_from_connection(connection)

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("PostgreSQL identity repository is not initialized.")

    async def get_identity(self, identity_id: str) -> ManagedIdentity | None:
        self._ensure_initialized()
        self._validate_lookup_id(identity_id)
        async with self._pool.acquire() as connection:
            return await self._get_identity(connection, identity_id)

    async def get_identity_by_oidc(self, *, issuer: str, subject: str) -> ManagedIdentity | None:
        self._ensure_initialized()
        self._validate_oidc_pair(issuer, subject)
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                f"SELECT {self._joined_columns()} FROM management_identities AS i "
                "JOIN management_role_bindings AS b ON b.identity_id = i.identity_id "
                "WHERE i.issuer = $1 AND i.subject = $2",
                issuer,
                subject,
            )
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
        arguments: tuple[object, ...] = (limit,)
        limit_placeholder = "$1"
        if after is not None:
            where = "WHERE (i.created_at, i.identity_id) > ($1, $2) "
            arguments = (datetime.fromisoformat(after.created_at), after.identity_id, limit)
            limit_placeholder = "$3"
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(
                f"SELECT {self._joined_columns()} FROM management_identities AS i "
                "JOIN management_role_bindings AS b ON b.identity_id = i.identity_id "
                f"{where}ORDER BY i.created_at ASC, i.identity_id ASC LIMIT {limit_placeholder}",
                *arguments,
            )
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
            identity_id=f"idn_{uuid.uuid4().hex}", issuer=issuer, subject=subject, now=now
        )
        binding = RoleBindingRecord.oidc_user(
            binding_id=f"rbd_{uuid.uuid4().hex}",
            identity_id=identity.identity_id,
            role=role,
            source=source,
            now=now,
        )
        try:
            async with self._pool.acquire() as connection:
                async with connection.transaction():
                    await self._insert_identity(connection, identity)
                    await self._insert_binding(connection, binding)
        except asyncpg.UniqueViolationError as exc:
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
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    UPDATE management_identities
                    SET enabled = $1, updated_at = $2, revision = revision + 1,
                        authorization_epoch = authorization_epoch + 1
                    WHERE identity_id = $3 AND revision = $4
                    RETURNING revision
                    """,
                    enabled,
                    self._utc_now(),
                    identity_id,
                    expected_revision,
                )
                if row is None:
                    existing = await connection.fetchrow(
                        "SELECT revision FROM management_identities WHERE identity_id = $1",
                        identity_id,
                    )
                    if existing is None:
                        raise IdentityNotFound("Management identity was not found.")
                    raise IdentityRevisionConflict("Identity revision conflict.")
                updated = await self._get_identity(connection, identity_id)
                if updated is None:
                    raise IdentityStoreCorrupt("Management identity store is invalid.")
                return updated

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
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                current = await self._get_identity(connection, identity_id, for_update=True)
                if current is None:
                    raise IdentityNotFound("Management identity was not found.")
                RoleBindingRecord.oidc_user(
                    binding_id=current.binding.binding_id,
                    identity_id=identity_id,
                    role=role,
                    source=source,
                    now=self._clock(),
                )
                self._require_revision(current.binding.revision, expected_revision)
                timestamp = self._utc_now()
                binding_status = await connection.execute(
                    """
                    UPDATE management_role_bindings
                    SET role = $1, source = $2, revision = revision + 1, updated_at = $3
                    WHERE identity_id = $4 AND revision = $5
                    """,
                    role.value,
                    source.value,
                    timestamp,
                    identity_id,
                    expected_revision,
                )
                identity_status = await connection.execute(
                    """
                    UPDATE management_identities
                    SET revision = revision + 1,
                        authorization_epoch = authorization_epoch + 1, updated_at = $1
                    WHERE identity_id = $2 AND revision = $3
                    """,
                    timestamp,
                    identity_id,
                    current.identity.revision,
                )
                if binding_status != "UPDATE 1" or identity_status != "UPDATE 1":
                    raise IdentityRevisionConflict("Identity revision conflict.")
                updated = await self._get_identity(connection, identity_id)
                if updated is None:
                    raise IdentityStoreCorrupt("Management identity store is invalid.")
                return updated

    async def get_oidc_policy_revision(self) -> OidcPolicyRevisionRecord:
        self._ensure_initialized()
        async with self._pool.acquire() as connection:
            return await self._policy_from_connection(connection)

    async def advance_oidc_policy_revision(
        self, *, expected_revision: int
    ) -> OidcPolicyRevisionRecord:
        self._ensure_initialized()
        self._validate_revision(expected_revision)
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE oidc_policy_revision
                SET revision = revision + 1,
                    authorization_epoch = authorization_epoch + 1, updated_at = $1
                WHERE singleton_id = 1 AND revision = $2
                RETURNING schema_version, revision, authorization_epoch, updated_at
                """,
                self._utc_now(),
                expected_revision,
            )
            if row is None:
                existing = await connection.fetchrow(
                    "SELECT revision FROM oidc_policy_revision WHERE singleton_id = 1"
                )
                if existing is None:
                    raise IdentityStoreCorrupt("Management identity store is invalid.")
                raise IdentityRevisionConflict("OIDC policy revision conflict.")
        return self._policy_from_row(row)

    async def get_migration(self) -> IdentityMigrationRecord:
        self._ensure_initialized()
        async with self._pool.acquire() as connection:
            return await self._migration_from_connection(connection)

    async def _get_identity(
        self,
        connection: asyncpg.Connection,
        identity_id: str,
        *,
        for_update: bool = False,
    ) -> ManagedIdentity | None:
        lock_clause = " FOR UPDATE OF i, b" if for_update else ""
        row = await connection.fetchrow(
            f"SELECT {self._joined_columns()} FROM management_identities AS i "
            "JOIN management_role_bindings AS b ON b.identity_id = i.identity_id "
            f"WHERE i.identity_id = $1{lock_clause}",
            identity_id,
        )
        return None if row is None else self._managed_from_row(row)

    @staticmethod
    async def _insert_identity(connection: asyncpg.Connection, identity: IdentityRecord) -> None:
        record = identity.to_record()
        await connection.execute(
            f"INSERT INTO management_identities ({', '.join(_IDENTITY_COLUMNS)}) "
            f"VALUES ({PostgreSQLIdentityRepository._placeholders(len(_IDENTITY_COLUMNS))})",
            *PostgreSQLIdentityRepository._identity_values(record),
        )

    @staticmethod
    async def _insert_binding(connection: asyncpg.Connection, binding: RoleBindingRecord) -> None:
        record = binding.to_record()
        await connection.execute(
            f"INSERT INTO management_role_bindings ({', '.join(_BINDING_COLUMNS)}) "
            f"VALUES ({PostgreSQLIdentityRepository._placeholders(len(_BINDING_COLUMNS))})",
            *PostgreSQLIdentityRepository._database_values(record, _BINDING_COLUMNS),
        )

    @staticmethod
    def _placeholders(count: int) -> str:
        return ", ".join(f"${index}" for index in range(1, count + 1))

    @staticmethod
    def _identity_values(record: dict[str, object]) -> tuple[object, ...]:
        return PostgreSQLIdentityRepository._database_values(record, _IDENTITY_COLUMNS)

    @staticmethod
    def _database_values(record: dict[str, object], columns: tuple[str, ...]) -> tuple[object, ...]:
        return tuple(
            PostgreSQLIdentityRepository._timestamp_value(record[column])
            if column in {"created_at", "updated_at", "applied_at"}
            else record[column]
            for column in columns
        )

    @staticmethod
    def _timestamp_value(value: object) -> datetime:
        if type(value) is not str:
            raise ValueError("Timestamp is invalid.")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Timestamp is invalid.") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Timestamp is invalid.")
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _joined_columns() -> str:
        identity = ", ".join(f"i.{column} AS i_{column}" for column in _IDENTITY_COLUMNS)
        binding = ", ".join(f"b.{column} AS b_{column}" for column in _BINDING_COLUMNS)
        return f"{identity}, {binding}"

    @staticmethod
    def _stored_value(value: Any) -> Any:
        if type(value) is datetime:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Stored timestamp is invalid.")
            return value.astimezone(timezone.utc).isoformat()
        return value

    @classmethod
    def _managed_from_row(cls, row: Mapping[str, Any]) -> ManagedIdentity:
        try:
            identity_values = {
                column: cls._stored_value(row[f"i_{column}"]) for column in _IDENTITY_COLUMNS
            }
            binding_values = {
                column: cls._stored_value(row[f"b_{column}"]) for column in _BINDING_COLUMNS
            }
            return ManagedIdentity(
                identity=identity_from_record(identity_values),
                binding=role_binding_from_record(binding_values),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise IdentityStoreCorrupt("Management identity store is invalid.") from exc

    @classmethod
    def _policy_from_row(cls, row: Mapping[str, Any]) -> OidcPolicyRevisionRecord:
        try:
            return oidc_policy_revision_from_record(
                {
                    "schema_version": row["schema_version"],
                    "revision": row["revision"],
                    "authorization_epoch": row["authorization_epoch"],
                    "updated_at": cls._stored_value(row["updated_at"]),
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise IdentityStoreCorrupt("Management identity store is invalid.") from exc

    @classmethod
    async def _policy_from_connection(
        cls, connection: asyncpg.Connection
    ) -> OidcPolicyRevisionRecord:
        row = await connection.fetchrow(
            """
            SELECT schema_version, revision, authorization_epoch, updated_at
            FROM oidc_policy_revision WHERE singleton_id = 1
            """
        )
        if row is None:
            raise IdentityStoreCorrupt("Management identity store is invalid.")
        return cls._policy_from_row(row)

    @classmethod
    async def _migration_from_connection(
        cls, connection: asyncpg.Connection
    ) -> IdentityMigrationRecord:
        row = await connection.fetchrow(
            """
            SELECT migration_id, schema_version, applied_at
            FROM identity_migrations WHERE migration_id = $1
            """,
            IDENTITY_MIGRATION_ID,
        )
        if row is None:
            raise IdentityStoreCorrupt("Management identity store is invalid.")
        try:
            return migration_from_record(
                {
                    "migration_id": row["migration_id"],
                    "schema_version": row["schema_version"],
                    "applied_at": cls._stored_value(row["applied_at"]),
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
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

    def _utc_now(self) -> datetime:
        now = self._clock()
        if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Timestamp is invalid.")
        return now.astimezone(timezone.utc)
