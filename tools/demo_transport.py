"""Offline HTTP boundary: replay source-shaped DB fixtures through real adapters.

No management endpoint or provider normalizer is replaced. Unrecorded operations
fail, including inference; they must never become synthetic successful calls.
"""

from contextlib import asynccontextmanager

import httpx


def fixture_response(request, fixture):
    variant, responses = fixture["variant"], fixture["responses"]
    path, host = request.url.path, request.url.host
    body = None
    if variant == "google_antigravity" and host.endswith("googleapis.com"):
        body = {
            "/v1internal:fetchAvailableModels": responses.get("quota"),
            "/v1internal:loadCodeAssist": responses.get("account"),
            "/v1internal:retrieveUserQuotaSummary": responses.get("groups", {}),
        }.get(path)
    elif variant == "codex" and host == "chatgpt.com" and path.endswith("/usage"):
        body = responses.get("quota")
    elif variant == "claude_code" and host == "api.anthropic.com" and path == "/api/oauth/usage":
        body = responses.get("quota")
    elif variant == "grok" and host == "cli-chat-proxy.grok.com" and path == "/v1/billing":
        body = responses.get("weekly" if request.url.params.get("format") == "credits" else "quota")
    elif variant == "kiro" and host in {
        "q.us-east-1.amazonaws.com",
        "q.eu-central-1.amazonaws.com",
    }:
        if path == "/getUsageLimits":
            body = responses.get("quota")
        elif path == "/ListAvailableModels":
            body = {"models": [{"modelId": m} for m in fixture["models"]]}
    elif variant == "muse_code" and host == "api.meta.ai" and path == "/muse-code/key":
        body = responses.get("subscription")
    if body is not None:
        return httpx.Response(fixture.get("status", 200), json=body, request=request)
    if request.method == "GET" and (
        path.endswith("/models")
        or path.endswith("/models/metadata")
        or path.endswith("/ai/models/search")
        or path == "/api/tags"
    ):
        models = [
            model.removeprefix("muse-code/") if variant == "muse_code" else model
            for model in fixture["models"]
        ]
        if variant == "google_ai_studio":
            body = {
                "models": [
                    {"name": "models/" + m, "supportedGenerationMethods": ["generateContent"]}
                    for m in models
                ]
            }
        elif variant == "codex":
            body = {
                "models": [{"slug": m, "display_name": m, "supported_in_api": True} for m in models]
            }
        elif variant == "ollama":
            body = {"models": [{"name": m, "model": m} for m in models]}
        elif variant == "cloudflare":
            body = {
                "success": True,
                "result": [{"name": m} for m in models],
                "result_info": {"page": 1, "total_pages": 1},
            }
        elif variant == "kimchi":
            body = {"models": [{"slug": m} for m in models]}
        elif variant == "mistral":
            body = {
                "data": [
                    {
                        "id": m,
                        "object": "model",
                        "archived": False,
                        "capabilities": {"completion_chat": True},
                    }
                    for m in models
                ]
            }
        else:
            body = {"data": [{"id": m, "object": "model"} for m in models], "has_more": False}
        return httpx.Response(fixture.get("status", 200), json=body, request=request)
    raise httpx.ConnectError(
        "Offline demo has no recorded response for this operation.", request=request
    )


def install_transport():
    from core.httpx_client import http_client
    from core.storage_adapter import get_storage_adapter

    async def respond(request):
        storage = await get_storage_adapter()
        credentials = await storage.get_all_credentials(mode="primary")
        fixtures = await storage.get_config("demo_upstream_v2", {})
        token = (
            request.headers.get("authorization", "").removeprefix("Bearer ")
            or request.headers.get("x-api-key")
            or request.headers.get("x-goog-api-key")
        )
        for filename, data in credentials.items():
            if data.get("synthetic") is not True or filename not in fixtures:
                continue
            secrets = {data.get(k) for k in ("api_key", "access_token", "token") if data.get(k)}
            local = (
                data.get("base_url", "").startswith("http://ollama-")
                and request.url.host == httpx.URL(data["base_url"]).host
            )
            if (token and token in secrets) or local:
                return fixture_response(request, fixtures[filename])
            if (
                not token
                and fixtures[filename]["variant"] == "opencode"
                and str(request.url).split("?")[0] == data.get("base_url", "") + "/models"
            ):
                return fixture_response(request, fixtures[filename])
        raise httpx.ConnectError(
            "Offline demo credential has no matching stored fixture.", request=request
        )

    @asynccontextmanager
    async def client(*args, **kwargs):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond), trust_env=False
        ) as session:
            yield session

    http_client.get_client = client
    http_client.get_streaming_client = client
