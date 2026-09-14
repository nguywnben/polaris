import json
import uuid

from core.models import OpenAIChatCompletionRequest, model_to_dict
from core.router.protocol_errors import adapt_protocol_error_response
from core.router.stream_passthrough import (
    build_streaming_response_or_error,
    cascade_close_async_iterator,
    prepend_async_item,
    read_first_async_item,
    sse_heartbeat_bytes,
)
from core.utils import authenticate_bearer, get_base_model_from_feature_model
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from log import log

router = APIRouter()


@router.post("/vertex/v1/chat/completions")
async def chat_completions(
    openai_request: OpenAIChatCompletionRequest,
    token: str = Depends(authenticate_bearer),
):
    log.debug(f"[VERTEX-OPENAI] Request for model: {openai_request.model}")

    normalized_dict = model_to_dict(openai_request)

    real_model = get_base_model_from_feature_model(openai_request.model)
    is_streaming = openai_request.stream

    normalized_dict["model"] = real_model

    from core.converter.openai_to_gemini import convert_openai_to_gemini_request

    gemini_dict = await convert_openai_to_gemini_request(normalized_dict)
    gemini_dict["model"] = real_model

    from core.converter.gemini_fix import normalize_gemini_request

    gemini_dict = await normalize_gemini_request(gemini_dict, mode="vertex")

    api_request = {
        "model": gemini_dict.pop("model"),
        "request": gemini_dict,
    }

    if not is_streaming:
        from core.api.vertex import non_stream_request

        response = await non_stream_request(body=api_request)

        status_code = getattr(response, "status_code", 200)
        if status_code >= 400:
            return adapt_protocol_error_response(response, "openai")

        if hasattr(response, "body"):
            response_body = (
                response.body.decode() if isinstance(response.body, bytes) else response.body
            )
        elif hasattr(response, "content"):
            response_body = (
                response.content.decode()
                if isinstance(response.content, bytes)
                else response.content
            )
        else:
            response_body = str(response)

        try:
            gemini_response = json.loads(response_body)
        except Exception as e:
            log.error(f"[vertex openai] failed to parse response: {e}")
            return JSONResponse(content={"error": "Response parsing failed."}, status_code=500)

        from core.converter.openai_to_gemini import convert_gemini_to_openai_response

        openai_response = convert_gemini_to_openai_response(
            gemini_response, real_model, status_code
        )
        return JSONResponse(content=openai_response, status_code=status_code)

    owned_streams = []

    async def stream_generator():
        from core.api.vertex import stream_request
        from fastapi import Response

        stream_gen = stream_request(body=api_request, native=False)
        owned_streams.append(stream_gen)
        try:
            first_chunk = await read_first_async_item(stream_gen)
        except StopAsyncIteration:
            return

        if isinstance(first_chunk, Response):
            yield first_chunk
            return

        response_id = str(uuid.uuid4())

        async for chunk in prepend_async_item(first_chunk, stream_gen):
            if isinstance(chunk, Response):
                try:
                    error_content = (
                        chunk.body
                        if isinstance(chunk.body, bytes)
                        else (chunk.body or b"").encode()
                    )
                    gemini_error = json.loads(error_content.decode())
                    from core.converter.openai_to_gemini import convert_gemini_to_openai_response

                    openai_error = convert_gemini_to_openai_response(
                        gemini_error, real_model, chunk.status_code
                    )
                    yield f"data: {json.dumps(openai_error)}\n\n".encode()
                except Exception:
                    yield f"data: {json.dumps({'error': 'Stream error'})}\n\n".encode()
                yield b"data: [DONE]\n\n"
                return

            chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk

            heartbeat = sse_heartbeat_bytes(chunk_str)
            if heartbeat is not None:
                yield heartbeat
                continue

            if not chunk_str.strip():
                continue

            if chunk_str.strip() == "data: [DONE]":
                yield "data: [DONE]\n\n".encode("utf-8")
                return

            if chunk_str.startswith("data: "):
                try:
                    from core.converter.openai_to_gemini import convert_gemini_to_openai_stream

                    openai_chunk_str = convert_gemini_to_openai_stream(
                        chunk_str, real_model, response_id
                    )
                    if openai_chunk_str:
                        yield openai_chunk_str.encode("utf-8")
                except Exception as e:
                    log.error(f"[vertex openai] failed to convert chunk: {e}")
                    continue

        yield "data: [DONE]\n\n".encode("utf-8")

    return await build_streaming_response_or_error(
        cascade_close_async_iterator(stream_generator(), owned_streams),
        error_protocol="openai",
    )
