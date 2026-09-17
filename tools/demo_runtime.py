"""Real runtime sessions for the isolated database preview; no UI/route fakes."""

import time
from contextlib import asynccontextmanager


def install_runtime_fixtures(app):
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application):
            from core.identity.sessions import get_session_service
            from core.storage_adapter import get_storage_adapter

            storage = await get_storage_adapter()
            metadata = await storage.get_config("demo_dataset_v1", {})
            if metadata.get("coverage") == "full-application":
                # Standalone sessions are in-process, so seed the real store
                # once per runtime, not a persisted flag that outlives them.
                for age in (120, 600):
                    await get_session_service().issue_local_owner(now=time.time() - age)
                # Populate diagnostics by asking the actual router to select and
                # immediately release a credential. This makes no provider call.
                from core.credential_manager import credential_manager
                from core.provider_registry import get_credential_provider

                manager = await credential_manager._get_or_create()
                records = await storage.get_all_credentials(mode="primary")
                seen = set()
                for data in records.values():
                    provider = get_credential_provider(data)
                    if provider in seen or not data.get("model_ids"):
                        continue
                    seen.add(provider)
                    result = await manager._routing.acquire(
                        storage,
                        mode="primary",
                        model_name=data["model_ids"][0],
                        provider_id=provider,
                        routing_strategy="balanced",
                        preferred_provider="",
                    )
                    if result:
                        await manager.release_credential(result[0], mode="primary")
            yield

    app.router.lifespan_context = lifespan
