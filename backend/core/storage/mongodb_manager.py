import asyncio
import os
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from core.credential_pool_mutation import (
    CredentialPoolMutation,
    CredentialPoolMutationError,
    CredentialPoolPlanner,
    CredentialPoolRecord,
    normalize_pool_mode,
    validate_credential_pool_mutation,
)
from log import log
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

if TYPE_CHECKING:
    from core.audit import AuditRepository
    from core.durable_migration_runner import MigrationCheckpointRepository
    from core.identity.repository import IdentityRepository


class MongoDBManager:
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

    @staticmethod
    def _escape_model_name(model_name: str) -> str:
        return model_name.replace(".", "-")

    def __init__(self):
        self._client: Optional[AsyncMongoClient] = None
        self._db: Optional[AsyncDatabase] = None
        self._initialized = False

        self._config_cache: Dict[str, Any] = {}
        self._config_loaded = False

        self._credential_pool_locks = {
            "code_assist": asyncio.Lock(),
            "primary": asyncio.Lock(),
        }

    async def initialize(self) -> None:
        if self._initialized:
            return

        try:
            mongodb_uri = os.getenv("MONGODB_URI")
            if not mongodb_uri:
                raise ValueError("MONGODB_URI environment variable not set")

            database_name = os.getenv("MONGODB_DATABASE", "polaris")

            self._client = AsyncMongoClient(mongodb_uri)
            self._db = self._client[database_name]

            await self._db.command("ping")

            await self._create_indexes()

            await self._load_config_cache()

            self._initialized = True
            log.info(f"MongoDB storage initialized (database: {database_name})")

        except Exception as e:
            log.error(f"MongoDB initialization failed ({type(e).__name__}).")
            raise

    async def _create_indexes(self):
        from pymongo import ASCENDING, IndexModel

        credentials_collection = self._db["credentials"]
        primary_credentials_collection = self._db["primary_credentials"]

        code_assist_indexes = [
            IndexModel([("filename", ASCENDING)], unique=True, name="idx_filename_unique"),
            IndexModel(
                [("disabled", ASCENDING), ("rotation_order", ASCENDING)],
                name="idx_disabled_rotation",
            ),
            IndexModel([("error_codes", ASCENDING)], name="idx_error_codes"),
            IndexModel([("user_email", ASCENDING)], name="idx_user_email"),
        ]

        primary_indexes = [
            IndexModel([("filename", ASCENDING)], unique=True, name="idx_filename_unique"),
            IndexModel(
                [("disabled", ASCENDING), ("rotation_order", ASCENDING)],
                name="idx_disabled_rotation",
            ),
            IndexModel([("error_codes", ASCENDING)], name="idx_error_codes"),
            IndexModel([("user_email", ASCENDING)], name="idx_user_email"),
        ]

        try:
            await credentials_collection.create_indexes(code_assist_indexes)
            await primary_credentials_collection.create_indexes(primary_indexes)
            log.debug("MongoDB indexes created.")
        except Exception as e:
            if "already exists" not in str(e).lower():
                log.warning(f"Index creation warning: {e}")

    async def _load_config_cache(self):
        if self._config_loaded:
            return

        try:
            config_collection = self._db["config"]
            cursor = config_collection.find({})

            async for doc in cursor:
                self._config_cache[doc["key"]] = doc.get("value")

            self._config_loaded = True
            log.debug(f"Loaded {len(self._config_cache)} config items into cache")

        except Exception as e:
            log.error(f"Error loading config cache: {e}")
            self._config_cache = {}

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
            self._db = None
        self._initialized = False
        log.debug("MongoDB storage closed")

    def _ensure_initialized(self):
        if not self._initialized:
            raise RuntimeError("MongoDB manager not initialized")

    async def create_audit_repository(self, *, cursor_signing_key: bytes) -> "AuditRepository":
        self._ensure_initialized()
        from .audit_mongodb import MongoAuditRepository

        repository = MongoAuditRepository(
            self._db["audit_events"],
            cursor_signing_key=cursor_signing_key,
        )
        await repository.initialize()
        return repository

    async def create_identity_repository(self) -> "IdentityRepository":
        self._ensure_initialized()
        from .identity_mongodb import MongoDBIdentityRepository

        repository = MongoDBIdentityRepository(self._db["management_identity_state"])
        await repository.initialize()
        return repository

    async def create_migration_checkpoint_repository(
        self,
    ) -> "MigrationCheckpointRepository":
        self._ensure_initialized()
        from .migration_mongodb import MongoMigrationCheckpointRepository

        repository = MongoMigrationCheckpointRepository(self._db["durable_migration_checkpoints"])
        await repository.initialize()
        return repository

    async def create_request_trace_repository(self, *, cursor_signing_key: bytes):
        self._ensure_initialized()
        from .request_trace_mongodb import MongoRequestTraceRepository

        repository = MongoRequestTraceRepository(
            self._db["request_traces"],
            cursor_signing_key=cursor_signing_key,
        )
        await repository.initialize()
        return repository

    async def create_usage_ledger_repository(self):
        self._ensure_initialized()
        from paths import DEFAULT_CREDENTIALS_DIR

        from .usage_ledger_mongodb import MongoDBUsageLedgerRepository
        from .usage_legacy_gate import require_external_usage_migration_ready

        credentials_dir = os.getenv("CREDENTIALS_DIR", str(DEFAULT_CREDENTIALS_DIR))
        await require_external_usage_migration_ready(
            os.path.join(credentials_dir, "usage_stats.db")
        )
        repository = MongoDBUsageLedgerRepository(
            self._client,
            self._db["durable_usage_ledger"],
            self._db["durable_usage_budget_keys"],
        )
        await repository.initialize()
        return repository

    def _get_collection_name(self, mode: str) -> str:
        if mode == "primary":
            return "primary_credentials"
        elif mode == "code_assist":
            return "credentials"
        else:
            raise ValueError(f"Invalid mode: {mode}. Must be 'code_assist' or 'primary'")

    async def get_next_available_credential(
        self, mode: str = "code_assist", model_name: Optional[str] = None
    ) -> Optional[tuple[str, Dict[str, Any]]]:
        self._ensure_initialized()

        try:
            collection_name = self._get_collection_name(mode)
            collection = self._db[collection_name]
            current_time = time.time()

            match_query: Dict[str, Any] = {"disabled": False}

            if mode == "code_assist" and model_name and "preview" in model_name.lower():
                match_query["preview"] = True

            if model_name:
                escaped_model_name = self._escape_model_name(model_name)
                field = f"model_cooldowns.{escaped_model_name}"
                match_query["$or"] = [
                    {field: {"$exists": False}},
                    {field: {"$lte": current_time}},
                ]

            projection = {"filename": 1, "credential_data": 1, "enable_credit": 1, "_id": 0}
            docs = await (
                collection.find(match_query, projection)
                .sort(
                    [("call_count", 1), ("last_success", 1), ("rotation_order", 1), ("filename", 1)]
                )
                .limit(1)
                .to_list(1)
            )

            if docs:
                doc = docs[0]
                credential_data = doc.get("credential_data") or {}
                if mode == "primary":
                    credential_data["enable_credit"] = bool(doc.get("enable_credit", False))
                return doc["filename"], credential_data

            return None

        except Exception as e:
            log.error(
                f"Error getting next available credential (mode={mode}, model_name={model_name}): {e}"
            )
            return None

    async def get_available_credentials_list(self, mode: str = "code_assist") -> List[str]:
        self._ensure_initialized()

        try:
            collection_name = self._get_collection_name(mode)
            collection = self._db[collection_name]

            pipeline = [
                {"$match": {"disabled": False}},
                {"$sort": {"rotation_order": 1}},
                {"$project": {"filename": 1, "_id": 0}},
            ]

            docs = await collection.aggregate(pipeline).to_list(length=None)
            return [doc["filename"] for doc in docs]

        except Exception as e:
            log.error(f"Error getting available credentials list (mode={mode}): {e}")
            return []

    async def store_credential(
        self, filename: str, credential_data: Dict[str, Any], mode: str = "code_assist"
    ) -> bool:
        self._ensure_initialized()

        filename = os.path.basename(filename)

        try:
            collection_name = self._get_collection_name(mode)
            collection = self._db[collection_name]
            current_ts = time.time()

            result = await collection.update_one(
                {"filename": filename},
                {
                    "$set": {
                        "credential_data": credential_data,
                        "updated_at": current_ts,
                    }
                },
            )

            if result.matched_count == 0:
                pipeline = [
                    {"$group": {"_id": None, "max_order": {"$max": "$rotation_order"}}},
                    {"$project": {"_id": 0, "next_order": {"$add": ["$max_order", 1]}}},
                ]

                result_list = await collection.aggregate(pipeline).to_list(length=1)
                next_order = result_list[0]["next_order"] if result_list else 0

                try:
                    new_credential = {
                        "filename": filename,
                        "credential_data": credential_data,
                        "disabled": False,
                        "error_codes": [],
                        "error_messages": [],
                        "last_success": current_ts,
                        "user_email": None,
                        "model_cooldowns": {},
                        "preview": True,
                        "tier": "pro",
                        "rotation_order": next_order,
                        "call_count": 0,
                        "created_at": current_ts,
                        "updated_at": current_ts,
                    }

                    if mode == "primary":
                        new_credential["enable_credit"] = False

                    await collection.insert_one(new_credential)
                except Exception as insert_error:
                    if "duplicate key" in str(insert_error).lower():
                        await collection.update_one(
                            {"filename": filename},
                            {
                                "$set": {
                                    "credential_data": credential_data,
                                    "updated_at": current_ts,
                                }
                            },
                        )
                    else:
                        raise

            log.debug(f"Stored credential: {filename} (mode={mode})")
            return True

        except Exception as e:
            log.error(f"Error storing credential {filename}: {e}")
            return False

    async def _mutate_credential_pool_in_session(
        self,
        mode: str,
        planner: CredentialPoolPlanner,
        *,
        session=None,
    ) -> CredentialPoolMutation:
        collection = self._db[self._get_collection_name(mode)]
        cursor = collection.find(
            {},
            {"filename": 1, "credential_data": 1, "user_email": 1, "rotation_order": 1, "_id": 0},
            session=session,
        ).sort([("rotation_order", 1), ("filename", 1)])
        documents = await cursor.to_list(length=None)
        records = []
        for document in documents:
            credential_data = document.get("credential_data")
            if type(credential_data) is not dict:
                raise CredentialPoolMutationError("Stored credential payload is invalid.")
            records.append(
                CredentialPoolRecord(
                    filename=document.get("filename"),
                    credential_data=credential_data,
                    user_email=document.get("user_email"),
                    rotation_order=document.get("rotation_order", 0),
                )
            )
        mutation = validate_credential_pool_mutation(planner(tuple(records)))
        if mutation.deletes:
            await collection.delete_many(
                {"filename": {"$in": list(mutation.deletes)}}, session=session
            )
        next_order = max((record.rotation_order for record in records), default=-1) + 1
        existing_names = {record.filename for record in records}
        current_time = time.time()
        for write in mutation.writes:
            update = {
                "$set": {
                    "credential_data": write.credential_data,
                    "user_email": write.user_email,
                    "updated_at": current_time,
                }
            }
            if write.filename not in existing_names:
                update["$setOnInsert"] = {
                    "disabled": False,
                    "error_codes": [],
                    "error_messages": [],
                    "last_success": current_time,
                    "model_cooldowns": {},
                    "preview": True,
                    "tier": "pro",
                    "rotation_order": next_order,
                    "call_count": 0,
                    "created_at": current_time,
                }
                if mode == "primary":
                    update["$setOnInsert"]["enable_credit"] = False
                next_order += 1
            await collection.update_one(
                {"filename": write.filename}, update, upsert=True, session=session
            )
        return mutation

    async def mutate_credential_pool(
        self, mode: str, planner: CredentialPoolPlanner
    ) -> CredentialPoolMutation:
        """Apply one pool plan atomically relative to this process."""
        self._ensure_initialized()
        mode = normalize_pool_mode(mode)
        if not callable(planner):
            raise CredentialPoolMutationError("Credential pool planner is invalid.")
        try:
            async with self._credential_pool_locks[mode]:
                return await self._mutate_credential_pool_in_session(mode, planner)
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
            collection_name = self._get_collection_name(mode)
            collection = self._db[collection_name]

            doc = await collection.find_one(
                {"filename": filename}, {"credential_data": 1, "_id": 0}
            )
            if doc:
                return doc.get("credential_data")

            return None

        except Exception as e:
            log.error(f"Error getting credential {filename}: {e}")
            return None

    async def list_credentials(self, mode: str = "code_assist") -> List[str]:
        self._ensure_initialized()

        try:
            collection_name = self._get_collection_name(mode)
            collection = self._db[collection_name]

            pipeline = [{"$sort": {"rotation_order": 1}}, {"$project": {"filename": 1, "_id": 0}}]

            docs = await collection.aggregate(pipeline).to_list(length=None)
            return [doc["filename"] for doc in docs]

        except Exception as e:
            log.error(f"Error listing credentials: {e}")
            return []

    async def get_all_credentials(self, mode: str = "code_assist") -> Dict[str, Dict[str, Any]]:
        self._ensure_initialized()
        try:
            collection = self._db[self._get_collection_name(mode)]
            pipeline = [
                {"$sort": {"rotation_order": 1}},
                {"$project": {"filename": 1, "credential_data": 1, "_id": 0}},
            ]
            docs = await collection.aggregate(pipeline).to_list(length=None)
            return {
                doc["filename"]: doc["credential_data"]
                for doc in docs
                if doc.get("filename") and isinstance(doc.get("credential_data"), dict)
            }
        except Exception as e:
            log.error(f"Error loading credentials: {e}")
            return {}

    async def delete_credential(self, filename: str, mode: str = "code_assist") -> bool:
        self._ensure_initialized()

        filename = os.path.basename(filename)

        try:
            collection_name = self._get_collection_name(mode)
            collection = self._db[collection_name]

            result = await collection.delete_one({"filename": filename})
            deleted_count = result.deleted_count

            if deleted_count > 0:
                log.debug(f"Deleted credential: {filename} (mode={mode}).")
                return True
            else:
                log.warning(f"No credential found to delete: {filename} (mode={mode})")
                return False

        except Exception as e:
            log.error(f"Error deleting credential {filename}: {e}")
            return False

    async def get_duplicate_credentials_by_email(self, mode: str = "code_assist") -> Dict[str, Any]:
        self._ensure_initialized()

        try:
            collection_name = self._get_collection_name(mode)
            collection = self._db[collection_name]

            pipeline = [
                {"$project": {"filename": 1, "user_email": 1, "_id": 0}},
                {"$sort": {"filename": 1}},
            ]

            docs = await collection.aggregate(pipeline).to_list(length=None)

            email_to_files = {}
            no_email_files = []

            for doc in docs:
                filename = doc.get("filename")
                user_email = doc.get("user_email")

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
                "total_count": len(docs),
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

    async def update_credential_state(
        self, filename: str, state_updates: Dict[str, Any], mode: str = "code_assist"
    ) -> bool:
        self._ensure_initialized()

        filename = os.path.basename(filename)

        try:
            collection_name = self._get_collection_name(mode)
            collection = self._db[collection_name]

            valid_updates = {k: v for k, v in state_updates.items() if k in self.STATE_FIELDS}

            if mode != "primary":
                valid_updates.pop("enable_credit", None)

            if not valid_updates:
                return True

            valid_updates["updated_at"] = time.time()

            result = await collection.update_one({"filename": filename}, {"$set": valid_updates})
            updated_count = result.modified_count + result.matched_count

            return updated_count > 0

        except Exception as e:
            log.error(f"Error updating credential state {filename}: {e}")
            return False

    async def get_credential_state(
        self, filename: str, mode: str = "code_assist"
    ) -> Dict[str, Any]:
        self._ensure_initialized()

        filename = os.path.basename(filename)

        try:
            collection_name = self._get_collection_name(mode)
            collection = self._db[collection_name]
            current_time = time.time()

            doc = await collection.find_one({"filename": filename})

            if doc:
                model_cooldowns = doc.get("model_cooldowns", {})

                if model_cooldowns:
                    model_cooldowns = {
                        k: v
                        for k, v in model_cooldowns.items()
                        if isinstance(v, (int, float)) and v > current_time
                    }

                state = {
                    "disabled": doc.get("disabled", False),
                    "error_codes": doc.get("error_codes", []),
                    "last_success": doc.get("last_success", current_time),
                    "user_email": doc.get("user_email"),
                    "model_cooldowns": model_cooldowns,
                    "preview": doc.get("preview", True),
                    "tier": doc.get("tier", "pro"),
                    "call_count": doc.get("call_count", 0),
                    "rotation_order": doc.get("rotation_order", 0),
                }
                if mode == "primary":
                    state["enable_credit"] = doc.get("enable_credit", False)
                return state

            default_state = {
                "disabled": False,
                "error_codes": [],
                "last_success": current_time,
                "user_email": None,
                "model_cooldowns": {},
                "preview": True,
                "tier": "pro",
                "call_count": 0,
                "rotation_order": 0,
            }
            if mode == "primary":
                default_state["enable_credit"] = False
            return default_state

        except Exception as e:
            log.error(f"Error getting credential state {filename}: {e}")
            return {}

    async def get_all_credential_states(
        self, mode: str = "code_assist"
    ) -> Dict[str, Dict[str, Any]]:
        self._ensure_initialized()

        try:
            collection_name = self._get_collection_name(mode)
            collection = self._db[collection_name]

            projection = {
                "filename": 1,
                "disabled": 1,
                "error_codes": 1,
                "last_success": 1,
                "user_email": 1,
                "model_cooldowns": 1,
                "preview": 1,
                "tier": 1,
                "enable_credit": 1,
                "call_count": 1,
                "rotation_order": 1,
                "_id": 0,
            }

            cursor = collection.find({}, projection=projection)

            states = {}
            current_time = time.time()

            async for doc in cursor:
                filename = doc["filename"]
                model_cooldowns = doc.get("model_cooldowns", {})

                if model_cooldowns:
                    model_cooldowns = {
                        k: v
                        for k, v in model_cooldowns.items()
                        if isinstance(v, (int, float)) and v > current_time
                    }

                state = {
                    "disabled": doc.get("disabled", False),
                    "error_codes": doc.get("error_codes", []),
                    "last_success": doc.get("last_success", time.time()),
                    "user_email": doc.get("user_email"),
                    "model_cooldowns": model_cooldowns,
                    "preview": doc.get("preview", True),
                    "tier": doc.get("tier", "pro"),
                    "call_count": doc.get("call_count", 0),
                    "rotation_order": doc.get("rotation_order", 0),
                }
                if mode == "primary":
                    state["enable_credit"] = doc.get("enable_credit", False)
                states[filename] = state

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
            collection_name = self._get_collection_name(mode)
            collection = self._db[collection_name]

            query = {}
            if status_filter == "enabled":
                query["disabled"] = False
            elif status_filter == "disabled":
                query["disabled"] = True

            if error_code_filter and str(error_code_filter).strip().lower() != "all":
                if str(error_code_filter).strip().lower() == "none":
                    query["$or"] = [
                        {"error_codes": {"$exists": False}},
                        {"error_codes": None},
                        {"error_codes": []},
                        {"error_codes": "[]"},
                    ]
                else:
                    filter_value = str(error_code_filter).strip()
                    query_values = [filter_value]
                    try:
                        query_values.append(int(filter_value))
                    except ValueError:
                        pass
                    query["error_codes"] = {"$in": query_values}

            global_stats = {"total": 0, "normal": 0, "disabled": 0}
            stats_pipeline = [{"$group": {"_id": "$disabled", "count": {"$sum": 1}}}]

            stats_result = await collection.aggregate(stats_pipeline).to_list(length=10)
            for item in stats_result:
                count = item["count"]
                global_stats["total"] += count
                if item["_id"]:
                    global_stats["disabled"] = count
                else:
                    global_stats["normal"] = count

            projection = {
                "filename": 1,
                "disabled": 1,
                "error_codes": 1,
                "last_success": 1,
                "user_email": 1,
                "rotation_order": 1,
                "model_cooldowns": 1,
                "preview": 1,
                "tier": 1,
                "enable_credit": 1,
                "_id": 0,
            }

            cursor = collection.find(query, projection=projection).sort("rotation_order", 1)

            all_summaries = []
            current_time = time.time()

            async for doc in cursor:
                model_cooldowns = doc.get("model_cooldowns", {})

                active_cooldowns = {}
                if model_cooldowns:
                    active_cooldowns = {
                        k: v
                        for k, v in model_cooldowns.items()
                        if isinstance(v, (int, float)) and v > current_time
                    }

                summary = {
                    "filename": doc["filename"],
                    "disabled": doc.get("disabled", False),
                    "error_codes": doc.get("error_codes", []),
                    "last_success": doc.get("last_success", current_time),
                    "user_email": doc.get("user_email"),
                    "rotation_order": doc.get("rotation_order", 0),
                    "model_cooldowns": active_cooldowns,
                    "preview": doc.get("preview", True),
                    "tier": doc.get("tier", "pro"),
                }

                if mode == "primary":
                    summary["enable_credit"] = bool(doc.get("enable_credit", False))

                if mode == "code_assist" and preview_filter:
                    preview_value = summary.get("preview", True)
                    if preview_filter == "preview" and not preview_value:
                        continue
                    if preview_filter == "no_preview" and preview_value:
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

    async def set_config(self, key: str, value: Any) -> bool:
        self._ensure_initialized()

        try:
            config_collection = self._db["config"]
            await config_collection.update_one(
                {"key": key},
                {"$set": {"value": value, "updated_at": time.time()}},
                upsert=True,
            )

            self._config_cache[key] = value

            return True

        except Exception as e:
            log.error(f"Error setting config {key}: {e}")
            return False

    async def reload_config_cache(self):
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
            config_collection = self._db["config"]
            result = await config_collection.delete_one({"key": key})

            self._config_cache.pop(key, None)

            return result.deleted_count > 0

        except Exception as e:
            log.error(f"Error deleting config {key}: {e}")
            return False

    async def get_credential_errors(
        self, filename: str, mode: str = "code_assist"
    ) -> Dict[str, Any]:
        self._ensure_initialized()

        filename = os.path.basename(filename)

        try:
            collection_name = self._get_collection_name(mode)
            collection = self._db[collection_name]

            doc = await collection.find_one(
                {"filename": filename}, {"error_codes": 1, "error_messages": 1, "_id": 0}
            )

            if doc:
                return {
                    "filename": filename,
                    "error_codes": doc.get("error_codes", []),
                    "error_messages": doc.get("error_messages", []),
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
            collection_name = self._get_collection_name(mode)
            collection = self._db[collection_name]

            escaped_model_name = self._escape_model_name(model_name)

            if cooldown_until is None:
                result = await collection.update_one(
                    {"filename": filename},
                    {
                        "$unset": {f"model_cooldowns.{escaped_model_name}": ""},
                        "$set": {"updated_at": time.time()},
                    },
                )
            else:
                result = await collection.update_one(
                    {"filename": filename},
                    {
                        "$set": {
                            f"model_cooldowns.{escaped_model_name}": cooldown_until,
                            "updated_at": time.time(),
                        }
                    },
                )

            if result.matched_count == 0:
                log.warning(f"Credential {filename} not found")
                return False

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
            collection_name = self._get_collection_name(mode)
            collection = self._db[collection_name]

            doc = await collection.find_one(
                {"filename": filename}, {"model_cooldowns": 1, "_id": 0}
            )
            if not doc:
                log.warning(f"Credential {filename} not found")
                return False

            await collection.update_one(
                {"filename": filename},
                {
                    "$set": {
                        "model_cooldowns": {},
                        "updated_at": time.time(),
                    }
                },
            )

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
            collection_name = self._get_collection_name(mode)
            collection = self._db[collection_name]
            now = time.time()

            await collection.update_one(
                {"filename": filename},
                {
                    "$set": {
                        "last_success": now,
                        "error_codes": [],
                        "error_messages": {},
                        "updated_at": now,
                    },
                    "$inc": {"call_count": call_increment},
                },
            )

            if model_name:
                escaped = self._escape_model_name(model_name)
                await collection.update_one(
                    {"filename": filename, f"model_cooldowns.{escaped}": {"$exists": True}},
                    {"$unset": {f"model_cooldowns.{escaped}": ""}, "$set": {"updated_at": now}},
                )

        except Exception as e:
            log.error(f"Error recording success for {filename}: {e}")

    async def record_failure(self, filename: str, mode: str = "code_assist") -> None:
        """Count failed attempts so routing fairness includes all upstream traffic."""
        self._ensure_initialized()
        filename = os.path.basename(filename)

        try:
            collection = self._db[self._get_collection_name(mode)]
            now = time.time()
            await collection.update_one(
                {"filename": filename},
                {
                    "$inc": {"call_count": 1},
                    "$set": {"updated_at": now},
                },
            )
        except Exception as e:
            log.error(f"Error recording failure for {filename}: {e}")
