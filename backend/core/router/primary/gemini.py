import json

from config import get_anti_truncation_max_attempts
from core.converter.fake_stream import (
    build_gemini_fake_stream_chunks,
    parse_response_for_fake_stream,
)
from core.model_pool import ModelPoolError, resolve_model_request
from core.models import GeminiRequest, model_to_dict
from core.router.protocol_errors import adapt_protocol_error_response
from core.router.stream_passthrough import (
    build_streaming_response_or_error,
    cascade_close_async_iterator,
    prepend_async_item,
    read_first_async_item,
    sse_heartbeat_bytes,
)
from core.token_estimator import estimate_input_tokens
from core.utils import (
    authenticate_gemini_flexible,
    get_base_model_from_feature_model,
    is_anti_truncation_model,
    is_fake_streaming_model,
)
from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.responses import JSONResponse, StreamingResponse
from log import log

router = APIRouter()


@router.post("/v1beta/models/{model:path}:generateContent")
async def generate_content(
    gemini_request: "GeminiRequest",
    model: str = Path(..., description="Model name"),
    api_key: str = Depends(authenticate_gemini_flexible),
):
    log.debug(f"[provider] Non-streaming request for model: {model}")

    normalized_dict = model_to_dict(gemini_request)

    use_anti_truncation = is_anti_truncation_model(model)
    requested_model = get_base_model_from_feature_model(model)
    try:
        model_resolution = await resolve_model_request(requested_model)
    except ModelPoolError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    model_candidates = list(model_resolution.candidates)
    real_model = model_candidates[0]

    if use_anti_truncation:
        log.warning(
            "Anti-truncation feature is only effective during streaming; this setting will be ignored for non-streaming requests"
        )

    normalized_dict["model"] = real_model

    from core.converter.gemini_fix import normalize_gemini_request

    normalized_dict = await normalize_gemini_request(normalized_dict, mode="primary")

    api_request = {"model": normalized_dict.pop("model"), "request": normalized_dict}

    from core.api.primary import non_stream_request

    response = await non_stream_request(
        body=api_request,
        model_candidates=model_candidates,
        model_routing=model_resolution.is_virtual,
    )

    if response.status_code >= 400:
        return adapt_protocol_error_response(response, "gemini")

    try:
        if response.status_code == 200:
            response_data = json.loads(
                response.body if hasattr(response, "body") else response.content
            )

            if "response" in response_data:
                unwrapped_data = response_data["response"]
                return JSONResponse(content=unwrapped_data)

        return response
    except Exception as e:
        log.warning(f"Failed to unwrap response: {e}. Returning the original response.")
        return response


@router.post("/v1beta/models/{model:path}:streamGenerateContent")
async def stream_generate_content(
    gemini_request: GeminiRequest,
    model: str = Path(..., description="Model name"),
    api_key: str = Depends(authenticate_gemini_flexible),
):
    log.debug(f"[provider] Streaming request for model: {model}")

    normalized_dict = model_to_dict(gemini_request)

    use_fake_streaming = is_fake_streaming_model(model)
    use_anti_truncation = is_anti_truncation_model(model)
    requested_model = get_base_model_from_feature_model(model)
    try:
        model_resolution = await resolve_model_request(requested_model)
    except ModelPoolError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    model_candidates = list(model_resolution.candidates)
    real_model = model_candidates[0]

    normalized_dict["model"] = real_model

    anti_owned_streams = []
    normal_owned_streams = []

    async def fake_stream_generator():
        from core.api.primary import non_stream_request
        from core.converter.gemini_fix import normalize_gemini_request

        normalized_req = await normalize_gemini_request(normalized_dict.copy(), mode="primary")

        api_request = {"model": normalized_req.pop("model"), "request": normalized_req}

        response = await non_stream_request(
            body=api_request,
            model_candidates=model_candidates,
            model_routing=model_resolution.is_virtual,
        )

        if hasattr(response, "status_code") and response.status_code != 200:
            log.error(f"Fake streaming got error response: status={response.status_code}")
            yield response
            return

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
            response_data = json.loads(response_body)
            log.debug(f"Gemini fake stream response data: {response_data}")

            if "error" in response_data:
                log.error(f"Fake streaming got error in response body: {response_data['error']}")
                yield f"data: {json.dumps(response_data)}\n\n".encode()
                yield "data: [DONE]\n\n".encode()
                return

            content, reasoning_content, finish_reason, images = parse_response_for_fake_stream(
                response_data
            )

            log.debug(f"Gemini extracted content: {content}")
            log.debug(
                f"Gemini extracted reasoning: {reasoning_content[:100] if reasoning_content else 'None'}..."
            )
            log.debug(f"Gemini extracted images count: {len(images)}")

            chunks = build_gemini_fake_stream_chunks(
                content, reasoning_content, finish_reason, images
            )
            for idx, chunk in enumerate(chunks):
                chunk_json = json.dumps(chunk)
                log.debug(f"[FAKE_STREAM] Yielding chunk #{idx + 1}: {chunk_json[:200]}")
                yield f"data: {chunk_json}\n\n".encode()

        except Exception as e:
            log.error(f"Response parsing failed: {e}. Returning the original response.")

            yield f"data: {response_body}\n\n".encode()

        yield "data: [DONE]\n\n".encode()

    async def anti_truncation_generator():
        from core.api.primary import stream_request
        from core.converter.anti_truncation import (
            AntiTruncationStreamProcessor,
            apply_anti_truncation,
        )
        from core.converter.gemini_fix import normalize_gemini_request
        from fastapi import Response

        normalized_req = await normalize_gemini_request(normalized_dict.copy(), mode="primary")

        api_request = {
            "model": normalized_req.pop("model") if "model" in normalized_req else real_model,
            "request": normalized_req,
        }

        max_attempts = await get_anti_truncation_max_attempts()

        anti_truncation_payload = apply_anti_truncation(api_request)

        first_attempt_stream = stream_request(
            body=anti_truncation_payload,
            native=False,
            model_candidates=model_candidates,
            model_routing=model_resolution.is_virtual,
        )
        anti_owned_streams.append(first_attempt_stream)
        try:
            first_chunk = await read_first_async_item(first_attempt_stream)
        except StopAsyncIteration:
            return

        if isinstance(first_chunk, Response):
            yield first_chunk
            return

        first_attempt_pending = True

        async def stream_request_wrapper(payload):
            nonlocal first_attempt_pending

            if first_attempt_pending:
                first_attempt_pending = False
                stream_gen = prepend_async_item(first_chunk, first_attempt_stream)
            else:
                stream_gen = stream_request(
                    body=payload,
                    native=False,
                    model_candidates=model_candidates,
                    model_routing=model_resolution.is_virtual,
                )
            anti_owned_streams.append(stream_gen)
            return StreamingResponse(stream_gen, media_type="text/event-stream")

        processor = AntiTruncationStreamProcessor(
            stream_request_wrapper,
            anti_truncation_payload,
            max_attempts,
            enable_prefill_mode=("claude" not in str(api_request.get("model", "")).lower()),
        )

        processor_stream = processor.process_stream()
        anti_owned_streams.append(processor_stream)
        async for chunk in processor_stream:
            heartbeat = sse_heartbeat_bytes(chunk)
            if heartbeat is not None:
                yield heartbeat
                continue
            if isinstance(chunk, (str, bytes)):
                chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk

                if chunk_str.startswith("data: "):
                    json_str = chunk_str[6:].strip()

                    if json_str == "[DONE]":
                        yield chunk
                        continue

                    try:
                        data = json.loads(json_str)

                        if "response" in data and "candidates" not in data:
                            log.debug("[provider anti-truncation] Expand response packaging")
                            unwrapped_data = data["response"]

                            yield f"data: {json.dumps(unwrapped_data, ensure_ascii=False)}\n\n".encode(
                                "utf-8"
                            )
                        else:
                            yield chunk
                    except json.JSONDecodeError:
                        yield chunk
                else:
                    yield chunk
            else:
                yield chunk

    async def normal_stream_generator():
        from core.api.primary import stream_request
        from core.converter.gemini_fix import normalize_gemini_request
        from fastapi import Response

        normalized_req = await normalize_gemini_request(normalized_dict.copy(), mode="primary")

        api_request = {"model": normalized_req.pop("model"), "request": normalized_req}

        log.debug("[provider] Using non-native mode, the response wrapper will be expanded")
        stream_gen = stream_request(
            body=api_request,
            native=False,
            model_candidates=model_candidates,
            model_routing=model_resolution.is_virtual,
        )
        normal_owned_streams.append(stream_gen)
        try:
            first_chunk = await read_first_async_item(stream_gen)
        except StopAsyncIteration:
            return

        if isinstance(first_chunk, Response):
            yield first_chunk
            return

        async for chunk in prepend_async_item(first_chunk, stream_gen):
            heartbeat = sse_heartbeat_bytes(chunk)
            if heartbeat is not None:
                yield heartbeat
                continue
            if isinstance(chunk, Response):
                try:
                    error_content = (
                        chunk.body
                        if isinstance(chunk.body, bytes)
                        else (chunk.body or b"").encode("utf-8")
                    )
                    error_json = json.loads(error_content.decode("utf-8"))
                except Exception:
                    error_json = {
                        "error": {
                            "code": chunk.status_code,
                            "message": "upstream error",
                            "status": "ERROR",
                        }
                    }
                log.error(
                    f"[provider stream] returns an error to the client: status = {chunk.status_code}, error = {str(error_json)[:200]}"
                )
                yield f"data: {json.dumps(error_json)}\n\n".encode("utf-8")
                yield b"data: [DONE]\n\n"
                return

            if isinstance(chunk, (str, bytes)):
                chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk

                if chunk_str.startswith("data: "):
                    json_str = chunk_str[6:].strip()

                    if json_str == "[DONE]":
                        yield chunk
                        continue

                    try:
                        data = json.loads(json_str)

                        if "response" in data and "candidates" not in data:
                            log.debug("[provider] Expand response packaging")
                            unwrapped_data = data["response"]

                            yield f"data: {json.dumps(unwrapped_data, ensure_ascii=False)}\n\n".encode(
                                "utf-8"
                            )
                        else:
                            yield chunk
                    except json.JSONDecodeError:
                        yield chunk
                else:
                    yield chunk

    if use_fake_streaming:
        return await build_streaming_response_or_error(
            fake_stream_generator(), error_protocol="gemini"
        )
    elif use_anti_truncation:
        log.info("Enabling anti-truncation streaming feature")
        return await build_streaming_response_or_error(
            cascade_close_async_iterator(anti_truncation_generator(), anti_owned_streams),
            error_protocol="gemini",
        )
    else:
        return await build_streaming_response_or_error(
            cascade_close_async_iterator(normal_stream_generator(), normal_owned_streams),
            error_protocol="gemini",
        )


@router.post("/v1beta/models/{model:path}:countTokens")
async def count_tokens(
    request: Request,
    _api_key: str = Depends(authenticate_gemini_flexible),
):
    try:
        request_data = await request.json()
    except Exception as exc:
        log.debug(f"Failed to parse count-tokens JSON request: {exc}")
        raise HTTPException(
            status_code=400,
            detail="The request body must contain valid JSON.",
        ) from exc

    payload = request_data.get("generateContentRequest", request_data)
    return JSONResponse(content={"totalTokens": estimate_input_tokens(payload)})
