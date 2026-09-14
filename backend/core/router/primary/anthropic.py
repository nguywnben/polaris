import json

from config import get_anti_truncation_max_attempts
from core.converter.fake_stream import (
    build_anthropic_fake_stream_chunks,
    parse_response_for_fake_stream,
)
from core.model_pool import ModelPoolError, resolve_model_request
from core.models import ClaudeRequest, model_to_dict
from core.router.protocol_errors import adapt_protocol_error_response
from core.router.stream_passthrough import (
    build_streaming_response_or_error,
    cascade_close_async_iterator,
    prepend_async_item,
    read_first_async_item,
)
from core.token_estimator import estimate_input_tokens
from core.utils import (
    authenticate_bearer,
    get_base_model_from_feature_model,
    is_anti_truncation_model,
    is_fake_streaming_model,
)
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from log import log

router = APIRouter()


@router.post("/v1/messages")
async def messages(claude_request: ClaudeRequest, _token: str = Depends(authenticate_bearer)):
    log.debug(f"[provider anthropic] Request for model: {claude_request.model}")

    normalized_dict = model_to_dict(claude_request)

    use_fake_streaming = is_fake_streaming_model(claude_request.model)
    use_anti_truncation = is_anti_truncation_model(claude_request.model)
    requested_model = get_base_model_from_feature_model(claude_request.model)
    try:
        model_resolution = await resolve_model_request(requested_model)
    except ModelPoolError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    model_candidates = list(model_resolution.candidates)
    real_model = model_candidates[0]
    response_model = model_resolution.response_model

    is_streaming = claude_request.stream

    if use_anti_truncation and not is_streaming:
        log.warning(
            "Anti-truncation feature is only effective during streaming; this setting will be ignored for non-streaming requests"
        )

    normalized_dict["model"] = real_model

    from core.converter.anthropic_to_gemini import anthropic_to_gemini_request

    gemini_dict = await anthropic_to_gemini_request(normalized_dict)

    gemini_dict["model"] = real_model

    from core.converter.gemini_fix import normalize_gemini_request

    gemini_dict = await normalize_gemini_request(gemini_dict, mode="primary")

    api_request = {"model": gemini_dict.pop("model"), "request": gemini_dict}

    if not is_streaming:
        from core.api.primary import non_stream_request

        response = await non_stream_request(
            body=api_request,
            model_candidates=model_candidates,
            model_routing=model_resolution.is_virtual,
        )

        status_code = getattr(response, "status_code", 200)
        if status_code >= 400:
            return adapt_protocol_error_response(response, "anthropic")

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
            log.error(f"Failed to parse Gemini response: {e}")
            raise HTTPException(status_code=500, detail="Response parsing failed.")

        from core.converter.anthropic_to_gemini import gemini_to_anthropic_response

        anthropic_response = gemini_to_anthropic_response(
            gemini_response, response_model, status_code
        )

        return JSONResponse(content=anthropic_response, status_code=status_code)

    anti_owned_streams = []
    normal_owned_streams = []

    async def fake_stream_generator():
        from core.api.primary import non_stream_request

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
            gemini_response = json.loads(response_body)
            log.debug(f"Anthropic fake stream Gemini response: {gemini_response}")

            if "error" in gemini_response:
                log.error(f"Fake streaming got error in response body: {gemini_response['error']}")

                from core.converter.anthropic_to_gemini import gemini_to_anthropic_response

                anthropic_error = gemini_to_anthropic_response(gemini_response, response_model, 200)
                yield f"data: {json.dumps(anthropic_error)}\n\n".encode()
                yield "data: [DONE]\n\n".encode()
                return

            content, reasoning_content, finish_reason, images = parse_response_for_fake_stream(
                gemini_response
            )

            log.debug(f"Anthropic extracted content: {content}")
            log.debug(
                f"Anthropic extracted reasoning: {reasoning_content[:100] if reasoning_content else 'None'}..."
            )
            log.debug(f"Anthropic extracted images count: {len(images)}")

            chunks = build_anthropic_fake_stream_chunks(
                content, reasoning_content, finish_reason, response_model, images
            )
            for idx, chunk in enumerate(chunks):
                chunk_json = json.dumps(chunk)
                log.debug(f"[FAKE_STREAM] Yielding chunk #{idx + 1}: {chunk_json[:200]}")
                yield f"data: {chunk_json}\n\n".encode()

        except Exception as e:
            log.error(f"Response parsing failed: {e}. Returning the upstream error.")

            error_chunk = {
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": "The upstream response could not be parsed.",
                },
            }
            yield f"data: {json.dumps(error_chunk)}\n\n".encode()

        yield "data: [DONE]\n\n".encode()

    async def anti_truncation_generator():
        from core.api.primary import stream_request
        from core.converter.anthropic_to_gemini import gemini_stream_to_anthropic_stream
        from core.converter.anti_truncation import (
            AntiTruncationStreamProcessor,
            apply_anti_truncation,
        )
        from fastapi import Response

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

        async def bytes_wrapper():
            async for chunk in processor.process_stream():
                if isinstance(chunk, str):
                    yield chunk.encode("utf-8")
                else:
                    yield chunk

        anthropic_stream = gemini_stream_to_anthropic_stream(bytes_wrapper(), response_model, 200)
        anti_owned_streams.append(anthropic_stream)
        async for anthropic_chunk in anthropic_stream:
            if anthropic_chunk:
                yield anthropic_chunk

    async def normal_stream_generator():
        from core.api.primary import stream_request
        from core.converter.anthropic_to_gemini import gemini_stream_to_anthropic_stream
        from fastapi import Response

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

        async def gemini_chunk_wrapper():
            async for chunk in prepend_async_item(first_chunk, stream_gen):
                if isinstance(chunk, Response):
                    try:
                        error_content = (
                            chunk.body
                            if isinstance(chunk.body, bytes)
                            else (chunk.body or b"").encode("utf-8")
                        )
                        gemini_error = json.loads(error_content.decode("utf-8"))
                        from core.converter.anthropic_to_gemini import gemini_to_anthropic_response

                        anthropic_error = gemini_to_anthropic_response(
                            gemini_error, response_model, chunk.status_code
                        )
                        yield f"data: {json.dumps(anthropic_error)}\n\n".encode("utf-8")
                    except Exception:
                        yield f"data: {json.dumps({'type': 'error', 'error': {'type': 'api_error', 'message': 'Stream error'}})}\n\n".encode(
                            "utf-8"
                        )
                    yield b"data: [DONE]\n\n"
                    return
                else:
                    if isinstance(chunk, str):
                        yield chunk.encode("utf-8")
                    else:
                        yield chunk

        anthropic_stream = gemini_stream_to_anthropic_stream(
            gemini_chunk_wrapper(), response_model, 200
        )
        normal_owned_streams.append(anthropic_stream)
        async for anthropic_chunk in anthropic_stream:
            if anthropic_chunk:
                yield anthropic_chunk

    if use_fake_streaming:
        return await build_streaming_response_or_error(
            fake_stream_generator(), error_protocol="anthropic"
        )
    elif use_anti_truncation:
        log.info("Enabling anti-truncation streaming feature")
        return await build_streaming_response_or_error(
            cascade_close_async_iterator(anti_truncation_generator(), anti_owned_streams),
            error_protocol="anthropic",
        )
    else:
        return await build_streaming_response_or_error(
            cascade_close_async_iterator(normal_stream_generator(), normal_owned_streams),
            error_protocol="anthropic",
        )


@router.post("/v1/messages/count_tokens")
async def count_tokens(request: Request, _token: str = Depends(authenticate_bearer)):
    try:
        payload = await request.json()
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": f"JSON parsing failed: {str(e)}.",
                },
            },
        )

    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=400,
            content={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": "Request body must be a JSON object.",
                },
            },
        )

    if not payload.get("model") or not isinstance(payload.get("messages"), list):
        return JSONResponse(
            status_code=400,
            content={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": "Missing required fields: model and messages.",
                },
            },
        )

    try:
        client_host = request.client.host if request.client else "unknown"
        client_port = request.client.port if request.client else "unknown"
    except Exception:
        client_host = "unknown"
        client_port = "unknown"

    thinking_present = "thinking" in payload
    thinking_value = payload.get("thinking")
    thinking_summary = None
    if thinking_present:
        if isinstance(thinking_value, dict):
            thinking_summary = {
                "type": thinking_value.get("type"),
                "budget_tokens": thinking_value.get("budget_tokens"),
            }
        else:
            thinking_summary = thinking_value

    user_agent = request.headers.get("user-agent", "")
    log.info(
        f"[provider anthropic] /messages/count_tokens received request: client={client_host}:{client_port}, "
        f"model={payload.get('model')}, messages={len(payload.get('messages') or [])}, "
        f"thinking_present={thinking_present}, thinking={thinking_summary}, ua={user_agent}"
    )

    input_tokens = 0
    try:
        input_tokens = estimate_input_tokens(payload)
    except Exception as e:
        log.error(f"[provider anthropic] token evaluation failed: {e}")

    return JSONResponse(content={"input_tokens": input_tokens})
