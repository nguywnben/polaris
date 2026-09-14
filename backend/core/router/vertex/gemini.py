from core.models import GeminiRequest, model_to_dict
from core.router.protocol_errors import adapt_protocol_error_response
from core.router.stream_passthrough import (
    build_streaming_response_or_error,
    cascade_close_async_iterator,
    sse_heartbeat_bytes,
)
from core.token_estimator import estimate_input_tokens
from core.utils import authenticate_gemini_flexible
from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.responses import JSONResponse
from log import log

router = APIRouter()


@router.post("/vertex/v1beta/models/{model:path}:generateContent")
@router.post("/vertex/v1/models/{model:path}:generateContent")
async def generate_content(
    gemini_request: GeminiRequest,
    model: str = Path(..., description="Model name"),
    api_key: str = Depends(authenticate_gemini_flexible),
):
    log.debug(f"[VERTEX ROUTER] Non-streaming request for model: {model}")

    normalized_dict = model_to_dict(gemini_request)

    normalized_dict["model"] = model

    from core.converter.gemini_fix import normalize_gemini_request

    normalized_dict = await normalize_gemini_request(normalized_dict, mode="vertex")

    api_request = {
        "model": normalized_dict.pop("model"),
        "request": normalized_dict,
    }

    from core.api.vertex import non_stream_request

    response = await non_stream_request(body=api_request)
    return adapt_protocol_error_response(response, "gemini")


@router.post("/vertex/v1beta/models/{model:path}:streamGenerateContent")
@router.post("/vertex/v1/models/{model:path}:streamGenerateContent")
async def stream_generate_content(
    gemini_request: GeminiRequest,
    model: str = Path(..., description="Model name"),
    api_key: str = Depends(authenticate_gemini_flexible),
):
    log.debug(f"[VERTEX ROUTER] Streaming request for model: {model}")

    normalized_dict = model_to_dict(gemini_request)
    normalized_dict["model"] = model

    owned_streams = []

    async def stream_generator():
        from core.api.vertex import stream_request
        from core.converter.gemini_fix import normalize_gemini_request
        from fastapi import Response

        normalized_req = await normalize_gemini_request(normalized_dict.copy(), mode="vertex")

        api_request = {
            "model": normalized_req.pop("model"),
            "request": normalized_req,
        }

        upstream = stream_request(body=api_request, native=False)
        owned_streams.append(upstream)
        async for chunk in upstream:
            if isinstance(chunk, Response):
                yield chunk
                return
            if isinstance(chunk, (str, bytes)):
                heartbeat = sse_heartbeat_bytes(chunk)
                if heartbeat is not None:
                    yield heartbeat
                    continue
                yield chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")

    return await build_streaming_response_or_error(
        cascade_close_async_iterator(stream_generator(), owned_streams),
        error_protocol="gemini",
    )


@router.post("/vertex/v1beta/models/{model:path}:countTokens")
@router.post("/vertex/v1/models/{model:path}:countTokens")
async def count_tokens(
    request: Request,
    _api_key: str = Depends(authenticate_gemini_flexible),
):
    try:
        request_data = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="The request body must contain valid JSON.",
        ) from exc

    payload = request_data.get("generateContentRequest", request_data)
    return JSONResponse(content={"totalTokens": estimate_input_tokens(payload)})
