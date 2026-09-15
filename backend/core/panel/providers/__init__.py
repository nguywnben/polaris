"""Provider-specific management console routes."""

from fastapi import APIRouter

from . import anthropic, antigravity, catalog, extended, google_ai_studio, ollama, openai, xai


def create_router() -> APIRouter:
    router = APIRouter()
    router.include_router(catalog.router)
    router.include_router(antigravity.router)
    router.include_router(google_ai_studio.router)
    router.include_router(xai.router)
    router.include_router(openai.router)
    router.include_router(anthropic.router)
    router.include_router(ollama.router)
    router.include_router(extended.router)
    return router


router = create_router()

__all__ = ["router"]
