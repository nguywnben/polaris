"""MongoDB repository for durable management identities and role bindings."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

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
from pymongo import ASCENDING, IndexModel, ReturnDocument
from pymongo.collation import Collation
from pymongo.errors import DuplicateKeyError

_MANAGED_DOCUMENT = "managed_identity"
_POLICY_DOCUMENT = "oidc_policy_revision"
_MIGRATION_DOCUMENT = "identity_migration"
_POLICY_ID = "oidc-policy-revision"
_SIMPLE_COLLATION = Collation(locale="simple")


class MongoDBIdentityRepository:
    """Fail-closed MongoDB identity repository with atomic managed documents."""

    def __init__(
        self,
        collection: Any,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._collection = collection
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._initialized = False
        self._initialize_lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._initialize_lock:
            self._initialized = False
            try:
                await self._create_indexes()
                await self._bootstrap()
                await self._validate_store()
            except IdentityStoreCorrupt:
                raise
            except Exception as exc:
                raise IdentityStoreCorrupt("Management identity store is invalid.") from exc
            self._initialized = True

    async def _create_indexes(self) -> None:
        await self._collection.create_indexes(
            [
                IndexModel(
                    [("identity.issuer", ASCENDING), ("identity.subject", ASCENDING)],
                    unique=True,
                    name="idx_management_identity_oidc_unique",
                    partialFilterExpression={
                        "document_type": _MANAGED_DOCUMENT,
                        "identity.principal_type": "oidc_user",
                    },
                    collation=_SIMPLE_COLLATION,
                ),
                IndexModel(
                    [
                        ("identity.created_at", ASCENDING),
                        ("identity.identity_id", ASCENDING),
                    ],
                    name="idx_management_identity_order",
                    partialFilterExpression={"document_type": _MANAGED_DOCUMENT},
                ),
            ]
        )

    async def _bootstrap(self) -> None:
        now = self._clock()
        owner = ManagedIdentity(
            identity=IdentityRecord.local_owner(now=now),
            binding=RoleBindingRecord.local_owner(now=now),
        )
        policy = OidcPolicyRevisionRecord.initial(now=now)
        migration = IdentityMigrationRecord.applied(now=now)
        await self._collection.update_one(
            {"_id": LOCAL_OWNER_ID},
            {"$setOnInsert": self._managed_to_document(owner)},
            upsert=True,
        )
        await self._collection.update_one(
            {"_id": _POLICY_ID},
            {
                "$setOnInsert": {
                    "_id": _POLICY_ID,
                    "document_type": _POLICY_DOCUMENT,
                    "record": policy.to_record(),
                }
            },
            upsert=True,
        )
        await self._collection.update_one(
            {"_id": IDENTITY_MIGRATION_ID},
            {
                "$setOnInsert": {
                    "_id": IDENTITY_MIGRATION_ID,
                    "document_type": _MIGRATION_DOCUMENT,
                    "record": migration.to_record(),
                }
            },
            upsert=True,
        )

    async def _validate_store(self) -> None:
        cursor = self._collection.find({"document_type": _MANAGED_DOCUMENT})
        documents = [document async for document in cursor]
        managed = [self._managed_from_document(document) for document in documents]
        count = await self._collection.count_documents({"document_type": _MANAGED_DOCUMENT})
        if type(count) is not int or count != len(managed):
            raise IdentityStoreCorrupt("Management identity store is invalid.")
        owners = [item for item in managed if item.identity.identity_id == LOCAL_OWNER_ID]
        if len(owners) != 1:
            raise IdentityStoreCorrupt("Management identity store is invalid.")
        await self._policy_from_store()
        await self._migration_from_store()

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("MongoDB identity repository is not initialized.")

    async def get_identity(self, identity_id: str) -> ManagedIdentity | None:
        self._ensure_initialized()
        self._validate_lookup_id(identity_id)
        document = await self._collection.find_one(
            {"_id": identity_id, "document_type": _MANAGED_DOCUMENT}
        )
        return None if document is None else self._managed_from_document(document)

    async def get_identity_by_oidc(self, *, issuer: str, subject: str) -> ManagedIdentity | None:
        self._ensure_initialized()
        self._validate_oidc_pair(issuer, subject)
        document = await self._collection.find_one(
            {
                "document_type": _MANAGED_DOCUMENT,
                "identity.principal_type": "oidc_user",
                "identity.issuer": issuer,
                "identity.subject": subject,
            },
            collation=_SIMPLE_COLLATION,
        )
        return None if document is None else self._managed_from_document(document)

    async def list_identities(
        self, *, limit: int = 100, after: IdentityPageCursor | None = None
    ) -> list[ManagedIdentity]:
        self._ensure_initialized()
        if type(limit) is not int or not 1 <= limit <= MAX_IDENTITY_PAGE_SIZE:
            raise ValueError("Identity page size is invalid.")
        if after is not None and type(after) is not IdentityPageCursor:
            raise ValueError("Identity cursor is invalid.")
        query: dict[str, object] = {"document_type": _MANAGED_DOCUMENT}
        if after is not None:
            query["$or"] = [
                {"identity.created_at": {"$gt": after.created_at}},
                {
                    "identity.created_at": after.created_at,
                    "identity.identity_id": {"$gt": after.identity_id},
                },
            ]
        cursor = self._collection.find(query)
        cursor = cursor.sort(
            [("identity.created_at", ASCENDING), ("identity.identity_id", ASCENDING)]
        )
        cursor = cursor.limit(limit)
        return [self._managed_from_document(document) async for document in cursor]

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
        managed = ManagedIdentity(identity=identity, binding=binding)
        try:
            await self._collection.insert_one(self._managed_to_document(managed))
        except DuplicateKeyError as exc:
            raise IdentityAlreadyExists("Management identity already exists.") from exc
        return managed

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
        document = await self._collection.find_one_and_update(
            {
                "_id": identity_id,
                "document_type": _MANAGED_DOCUMENT,
                "identity.revision": expected_revision,
            },
            {
                "$set": {
                    "identity.enabled": enabled,
                    "identity.updated_at": self._utc_now_text(),
                },
                "$inc": {
                    "identity.revision": 1,
                    "identity.authorization_epoch": 1,
                },
            },
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            await self._raise_missing_or_conflict(identity_id)
        return self._managed_from_document(document)

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
        RoleBindingRecord.oidc_user(
            binding_id="rbd_00000000000000000000000000000000",
            identity_id=identity_id,
            role=role,
            source=source,
            now=self._clock(),
        )
        timestamp = self._utc_now_text()
        document = await self._collection.find_one_and_update(
            {
                "_id": identity_id,
                "document_type": _MANAGED_DOCUMENT,
                "binding.revision": expected_revision,
            },
            {
                "$set": {
                    "binding.role": role.value,
                    "binding.source": source.value,
                    "binding.updated_at": timestamp,
                    "identity.updated_at": timestamp,
                },
                "$inc": {
                    "binding.revision": 1,
                    "identity.revision": 1,
                    "identity.authorization_epoch": 1,
                },
            },
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            await self._raise_missing_or_conflict(identity_id)
        return self._managed_from_document(document)

    async def get_oidc_policy_revision(self) -> OidcPolicyRevisionRecord:
        self._ensure_initialized()
        return await self._policy_from_store()

    async def advance_oidc_policy_revision(
        self, *, expected_revision: int
    ) -> OidcPolicyRevisionRecord:
        self._ensure_initialized()
        self._validate_revision(expected_revision)
        document = await self._collection.find_one_and_update(
            {
                "_id": _POLICY_ID,
                "document_type": _POLICY_DOCUMENT,
                "record.revision": expected_revision,
            },
            {
                "$set": {"record.updated_at": self._utc_now_text()},
                "$inc": {"record.revision": 1, "record.authorization_epoch": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            existing = await self._collection.find_one({"_id": _POLICY_ID})
            if existing is None:
                raise IdentityStoreCorrupt("Management identity store is invalid.")
            raise IdentityRevisionConflict("OIDC policy revision conflict.")
        return self._policy_from_document(document)

    async def get_migration(self) -> IdentityMigrationRecord:
        self._ensure_initialized()
        return await self._migration_from_store()

    async def _raise_missing_or_conflict(self, identity_id: str) -> None:
        existing = await self._collection.find_one(
            {"_id": identity_id, "document_type": _MANAGED_DOCUMENT}
        )
        if existing is None:
            raise IdentityNotFound("Management identity was not found.")
        self._managed_from_document(existing)
        raise IdentityRevisionConflict("Identity revision conflict.")

    async def _policy_from_store(self) -> OidcPolicyRevisionRecord:
        document = await self._collection.find_one({"_id": _POLICY_ID})
        if document is None:
            raise IdentityStoreCorrupt("Management identity store is invalid.")
        return self._policy_from_document(document)

    async def _migration_from_store(self) -> IdentityMigrationRecord:
        document = await self._collection.find_one({"_id": IDENTITY_MIGRATION_ID})
        if document is None:
            raise IdentityStoreCorrupt("Management identity store is invalid.")
        try:
            if set(document) != {"_id", "document_type", "record"}:
                raise ValueError("Stored identity migration is invalid.")
            if document["document_type"] != _MIGRATION_DOCUMENT:
                raise ValueError("Stored identity migration is invalid.")
            return migration_from_record(document["record"])
        except (KeyError, TypeError, ValueError) as exc:
            raise IdentityStoreCorrupt("Management identity store is invalid.") from exc

    @staticmethod
    def _managed_to_document(managed: ManagedIdentity) -> dict[str, Any]:
        return {
            "_id": managed.identity.identity_id,
            "document_type": _MANAGED_DOCUMENT,
            "schema_version": IDENTITY_SCHEMA_VERSION,
            "identity": managed.identity.to_record(),
            "binding": managed.binding.to_record(),
        }

    @staticmethod
    def _managed_from_document(document: Any) -> ManagedIdentity:
        try:
            if type(document) is not dict or set(document) != {
                "_id",
                "document_type",
                "schema_version",
                "identity",
                "binding",
            }:
                raise ValueError("Stored managed identity is invalid.")
            if (
                document["document_type"] != _MANAGED_DOCUMENT
                or document["schema_version"] != IDENTITY_SCHEMA_VERSION
            ):
                raise ValueError("Stored managed identity is invalid.")
            managed = ManagedIdentity(
                identity=identity_from_record(document["identity"]),
                binding=role_binding_from_record(document["binding"]),
            )
            if document["_id"] != managed.identity.identity_id:
                raise ValueError("Stored managed identity is invalid.")
            return managed
        except (KeyError, TypeError, ValueError) as exc:
            raise IdentityStoreCorrupt("Management identity store is invalid.") from exc

    @staticmethod
    def _policy_from_document(document: Any) -> OidcPolicyRevisionRecord:
        try:
            if type(document) is not dict or set(document) != {
                "_id",
                "document_type",
                "record",
            }:
                raise ValueError("Stored OIDC policy is invalid.")
            if document["_id"] != _POLICY_ID or document["document_type"] != _POLICY_DOCUMENT:
                raise ValueError("Stored OIDC policy is invalid.")
            return oidc_policy_revision_from_record(document["record"])
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

    def _utc_now_text(self) -> str:
        now = self._clock()
        if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Timestamp is invalid.")
        return now.astimezone(timezone.utc).isoformat()
