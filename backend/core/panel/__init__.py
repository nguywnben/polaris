from fastapi import APIRouter

from . import (
    audit_routes,
    auth,
    backup_routes,
    capabilities,
    config_routes,
    credentials,
    environment_credentials,
    identity_browser_routes,
    identity_routes,
    logs,
    model_pools,
    observability_routes,
    playground,
    providers,
    quality_policy,
    root,
    trace_routes,
    usage_routes,
    version,
    virtual_keys,
)
from .utils import ConnectionManager, get_env_locked_keys, is_mobile_user_agent, validate_mode


def create_router() -> APIRouter:
    router = APIRouter()

    router.include_router(root.router)
    router.include_router(auth.router)
    router.include_router(backup_routes.router)
    router.include_router(capabilities.router)
    router.include_router(environment_credentials.router)
    router.include_router(identity_browser_routes.router)
    router.include_router(identity_routes.router)
    router.include_router(credentials.router, prefix="/api/credentials")
    router.include_router(config_routes.router)
    router.include_router(logs.router)
    router.include_router(version.router)
    router.include_router(usage_routes.router)
    router.include_router(virtual_keys.router)
    router.include_router(providers.router)
    router.include_router(model_pools.router)
    router.include_router(quality_policy.router)
    router.include_router(audit_routes.router)
    router.include_router(trace_routes.router)
    router.include_router(observability_routes.router)
    router.include_router(playground.router)

    return router


router = create_router()

__all__ = [
    "router",
    "ConnectionManager",
    "is_mobile_user_agent",
    "validate_mode",
    "get_env_locked_keys",
]
