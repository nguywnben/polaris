import io
import json
import re
from typing import Any, AsyncGenerator, Dict, List, Tuple

from core.request_trace_service import trace_decision
from fastapi.responses import StreamingResponse
from log import log

DONE_MARKER = "[done]"
MAX_ANTI_TRUNCATION_BUFFER_BYTES = 8 * 1024 * 1024
CONTINUATION_PROMPT = f"""Please continue from exactly where the previous response was truncated.

Rules:
1. Do not repeat content that has already been produced.
2. Continue directly with the remaining content; do not add a preface or explanation.
3. When the answer is fully complete, output {DONE_MARKER} on its own final line.
4. The {DONE_MARKER} marker is required so the router can verify completion.

Continue now:"""


REGEX_REPLACEMENTS: List[Tuple[str, str, str]] = []


def apply_regex_replacements(text: str) -> str:
    if not text:
        return text

    processed_text = text
    replacement_count = 0

    for rule_name, pattern, replacement in REGEX_REPLACEMENTS:
        try:
            regex = re.compile(pattern, re.IGNORECASE)

            new_text, count = regex.subn(replacement, processed_text)

            if count > 0:
                log.debug(f"Regex replacement '{rule_name}': {count} matches replaced")
                processed_text = new_text
                replacement_count += count

        except re.error as e:
            log.error(f"Invalid regex pattern in rule '{rule_name}': {e}")
            continue

    if replacement_count > 0:
        log.info(f"Applied {replacement_count} regex replacements to text")

    return processed_text


def apply_regex_replacements_to_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not REGEX_REPLACEMENTS:
        return payload

    modified_payload = payload.copy()
    request_data = modified_payload.get("request", {})

    contents = request_data.get("contents", [])
    if contents:
        new_contents = []
        for content in contents:
            if isinstance(content, dict):
                new_content = content.copy()
                parts = new_content.get("parts", [])
                if parts:
                    new_parts = []
                    for part in parts:
                        if isinstance(part, dict) and "text" in part:
                            new_part = part.copy()
                            new_part["text"] = apply_regex_replacements(part["text"])
                            new_parts.append(new_part)
                        else:
                            new_parts.append(part)
                    new_content["parts"] = new_parts
                new_contents.append(new_content)
            else:
                new_contents.append(content)

        request_data["contents"] = new_contents
        modified_payload["request"] = request_data
        log.debug("Applied regex replacements to request contents")

    return modified_payload


def apply_anti_truncation(payload: Dict[str, Any]) -> Dict[str, Any]:

    modified_payload = apply_regex_replacements_to_payload(payload)
    request_data = modified_payload.get("request", {})

    system_instruction = request_data.get("systemInstruction", {})
    if not system_instruction:
        system_instruction = {"parts": []}
    elif "parts" not in system_instruction:
        system_instruction["parts"] = []

    anti_truncation_instruction = {
        "text": f"""Strictly follow this completion rule:

1. When the answer is complete, output {DONE_MARKER} on its own final line.
2. The router treats {DONE_MARKER} as the required completion marker.
3. If the answer is truncated, the system will ask you to continue the remaining content.
4. Every answer, short or long, must end with {DONE_MARKER}.

Example:
```
Answer content...
More answer content...
{DONE_MARKER}
```

The marker must be alone on the final line with no extra characters before it."""
    }

    has_done_instruction = any(
        part.get("text", "").find(DONE_MARKER) != -1
        for part in system_instruction["parts"]
        if isinstance(part, dict)
    )

    if not has_done_instruction:
        system_instruction["parts"].append(anti_truncation_instruction)
        request_data["systemInstruction"] = system_instruction
        modified_payload["request"] = request_data

        log.debug("Applied anti-truncation instruction to request")

    return modified_payload


class AntiTruncationStreamProcessor:
    def __init__(
        self,
        original_request_func,
        payload: Dict[str, Any],
        max_attempts: int = 3,
        enable_prefill_mode: bool = False,
    ):
        self.original_request_func = original_request_func
        self.base_payload = payload.copy()
        self.max_attempts = max_attempts
        self.enable_prefill_mode = enable_prefill_mode

        self.collected_content = io.StringIO()
        self.collected_bytes = 0
        self.current_attempt = 0

    def _get_collected_text(self) -> str:
        return self.collected_content.getvalue()

    def _append_content(self, content: str):
        if content:
            added_bytes = len(content.encode("utf-8"))
            if self.collected_bytes + added_bytes > MAX_ANTI_TRUNCATION_BUFFER_BYTES:
                raise RuntimeError("Anti-truncation output exceeded its memory limit")
            self.collected_content.write(content)
            self.collected_bytes += added_bytes

    def _clear_content(self):
        self.collected_content.close()
        self.collected_content = io.StringIO()
        self.collected_bytes = 0

    async def process_stream(self) -> AsyncGenerator[bytes, None]:
        while self.current_attempt < self.max_attempts:
            self.current_attempt += 1
            attempt_output_started = False

            current_payload = self._build_current_payload()

            log.debug(f"Anti-truncation attempt {self.current_attempt}/{self.max_attempts}")

            try:
                response = await self.original_request_func(current_payload)

                if not isinstance(response, StreamingResponse):
                    yield await self._handle_non_streaming_response(response)
                    return

                chunk_buffer = io.StringIO()
                chunk_buffer_bytes = 0
                found_done_marker = False

                async for line in response.body_iterator:
                    if not line:
                        yield line
                        continue

                    from fastapi import Response as FastAPIResponse

                    if isinstance(line, FastAPIResponse):
                        log.error(
                            f"Anti-truncation: Received Response object from stream (status={line.status_code}), treating as error"
                        )
                        error_chunk = {
                            "error": {
                                "message": line.body.decode("utf-8", errors="ignore")
                                if hasattr(line, "body") and line.body
                                else "Upstream error",
                                "type": "api_error",
                                "code": line.status_code,
                            }
                        }
                        yield f"data: {json.dumps(error_chunk)}\n\n".encode()
                        yield b"data: [DONE]\n\n"
                        return

                    if isinstance(line, bytes):
                        line_str = line.decode("utf-8", errors="ignore").strip()
                    else:
                        line_str = str(line).strip()

                    if not line_str:
                        yield line
                        continue

                    if line_str.startswith("data: "):
                        payload_str = line_str[6:]

                        if payload_str.strip() == "[DONE]":
                            if found_done_marker:
                                log.info("Anti-truncation: Found [done] marker, output complete")
                                yield line

                                chunk_buffer.close()
                                self._clear_content()
                                return
                            else:
                                log.warning("Anti-truncation: Stream ended without [done] marker")

                                break

                        try:
                            data = json.loads(payload_str)
                            content = self._extract_content_from_chunk(data)

                            log.debug(
                                f"Anti-truncation: Extracted content: {repr(content[:100] if content else '')}"
                            )

                            if content:
                                content_bytes = len(content.encode("utf-8"))
                                if (
                                    self.collected_bytes + chunk_buffer_bytes + content_bytes
                                    > MAX_ANTI_TRUNCATION_BUFFER_BYTES
                                ):
                                    raise RuntimeError(
                                        "Anti-truncation output exceeded its memory limit"
                                    )
                                chunk_buffer.write(content)
                                chunk_buffer_bytes += content_bytes

                                has_marker = self._check_done_marker_in_chunk_content(content)
                                log.debug(
                                    f"Anti-truncation: Check done marker result: {has_marker}, DONE_MARKER='{DONE_MARKER}'"
                                )
                                if has_marker:
                                    found_done_marker = True
                                    log.debug(
                                        f"Anti-truncation: Found [done] marker in chunk, content: {content[:200]}"
                                    )

                            cleaned_line = self._remove_done_marker_from_line(line, line_str, data)
                            attempt_output_started = True
                            yield cleaned_line

                        except (json.JSONDecodeError, ValueError):
                            yield line
                            continue
                    else:
                        yield line

                chunk_text = chunk_buffer.getvalue()
                if chunk_text:
                    self._append_content(chunk_text)
                chunk_buffer.close()

                log.debug(
                    f"Anti-truncation: After processing stream, found_done_marker={found_done_marker}"
                )

                if found_done_marker:
                    self._clear_content()
                    yield b"data: [DONE]\n\n"
                    return

                if not found_done_marker:
                    accumulated_text = self._get_collected_text()
                    if self._check_done_marker_in_text(accumulated_text):
                        log.info("Anti-truncation: Found [done] marker in accumulated content")

                        self._clear_content()
                        yield b"data: [DONE]\n\n"
                        return

                if self.current_attempt < self.max_attempts:
                    accumulated_text = self._get_collected_text()
                    total_length = len(accumulated_text)
                    log.info(
                        f"Anti-truncation: No [done] marker found in output (length: {total_length}), preparing continuation (attempt {self.current_attempt + 1})"
                    )
                    if total_length > 100:
                        log.debug(
                            f"Anti-truncation: Current collected content ends with: ...{accumulated_text[-100:]}"
                        )

                    continue
                else:
                    log.warning("Anti-truncation: Max attempts reached, ending stream")

                    self._clear_content()
                    yield b"data: [DONE]\n\n"
                    return

            except Exception as e:
                log.error(f"Anti-truncation error in attempt {self.current_attempt}: {str(e)}")
                if attempt_output_started:
                    status_code = 504 if isinstance(e, TimeoutError) else 502
                    trace_decision(
                        category="upstream",
                        action="failed",
                        result="failed",
                        reason="timeout" if status_code == 504 else "provider_error",
                        status_code=status_code,
                    )
                    error_chunk = {
                        "error": {
                            "message": "The upstream streaming response ended unexpectedly.",
                            "type": "api_error",
                            "code": status_code,
                        }
                    }
                    self._clear_content()
                    yield f"data: {json.dumps(error_chunk)}\n\n".encode()
                    yield b"data: [DONE]\n\n"
                    return
                if self.current_attempt >= self.max_attempts:
                    error_chunk = {
                        "error": {
                            "message": "The anti-truncation stream failed.",
                            "type": "api_error",
                            "code": 502,
                        }
                    }
                    yield f"data: {json.dumps(error_chunk)}\n\n".encode()
                    yield b"data: [DONE]\n\n"
                    return

        log.error("Anti-truncation: All attempts failed")

        self._clear_content()
        yield b"data: [DONE]\n\n"

    def _build_current_payload(self) -> Dict[str, Any]:
        if self.current_attempt == 1:
            return self.base_payload

        continuation_payload = self.base_payload.copy()
        request_data = continuation_payload.get("request", {})

        contents = request_data.get("contents", [])
        new_contents = contents.copy()

        accumulated_text = self._get_collected_text()
        if accumulated_text:
            new_contents.append({"role": "model", "parts": [{"text": accumulated_text}]})

        if self.enable_prefill_mode:
            log.debug(
                "Anti-truncation: Using prefill continuation mode (no user continuation prompt)"
            )
            request_data["contents"] = new_contents
            continuation_payload["request"] = request_data
            return continuation_payload

        content_summary = ""
        if accumulated_text:
            if len(accumulated_text) > 200:
                content_summary = (
                    f"\n\nEarlier output was approximately {len(accumulated_text)} characters. "
                    f'It ended with:\n"...{accumulated_text[-100:]}"'
                )
            else:
                content_summary = f'\n\nEarlier output was:\n"{accumulated_text}"'

        detailed_continuation_prompt = f"""{CONTINUATION_PROMPT}{content_summary}"""

        continuation_message = {"role": "user", "parts": [{"text": detailed_continuation_prompt}]}
        new_contents.append(continuation_message)

        request_data["contents"] = new_contents
        continuation_payload["request"] = request_data

        return continuation_payload

    def _extract_content_from_chunk(self, data: Dict[str, Any]) -> str:
        content = ""

        if "response" in data:
            data = data["response"]

        if "candidates" in data:
            for candidate in data["candidates"]:
                if "content" in candidate:
                    parts = candidate["content"].get("parts", [])
                    for part in parts:
                        if "text" in part:
                            content += part["text"]

        elif "choices" in data:
            for choice in data["choices"]:
                if "delta" in choice and "content" in choice["delta"]:
                    delta_content = choice["delta"]["content"]
                    if delta_content:
                        content += delta_content

        return content

    async def _handle_non_streaming_response(self, response) -> bytes:
        while True:
            try:
                if isinstance(response, StreamingResponse):
                    log.error(
                        "Anti-truncation: Received StreamingResponse in non-streaming handler - this should not happen"
                    )

                    chunks = []
                    async for chunk in response.body_iterator:
                        chunks.append(chunk)
                    content = b"".join(chunks).decode() if chunks else ""

                elif hasattr(response, "body"):
                    content = (
                        response.body.decode()
                        if isinstance(response.body, bytes)
                        else response.body
                    )
                elif hasattr(response, "content"):
                    content = (
                        response.content.decode()
                        if isinstance(response.content, bytes)
                        else response.content
                    )
                else:
                    log.error(f"Anti-truncation: Unknown response type: {type(response)}")
                    content = str(response)

                if not content or not content.strip():
                    log.error("Anti-truncation: Received empty response content")
                    return json.dumps(
                        {
                            "error": {
                                "message": "Empty response from server",
                                "type": "api_error",
                                "code": 500,
                            }
                        }
                    ).encode()

                try:
                    response_data = json.loads(content)
                except json.JSONDecodeError as json_err:
                    log.error(
                        f"Anti-truncation: Failed to parse JSON response: {json_err}, content: {content[:200]}"
                    )

                    return content.encode() if isinstance(content, str) else content

                text_content = self._extract_content_from_response(response_data)
                has_done_marker = self._check_done_marker_in_text(text_content)

                if has_done_marker or self.current_attempt >= self.max_attempts:
                    return content.encode() if isinstance(content, str) else content

                if text_content:
                    self._append_content(text_content)

                log.info("Anti-truncation: Non-streaming response needs continuation")

                self.current_attempt += 1

                next_payload = self._build_current_payload()
                response = await self.original_request_func(next_payload)

            except Exception as e:
                log.error(f"Anti-truncation non-streaming error: {str(e)}")
                return json.dumps(
                    {
                        "error": {
                            "message": f"Anti-truncation failed: {str(e)}",
                            "type": "api_error",
                            "code": 500,
                        }
                    }
                ).encode()

    def _check_done_marker_in_text(self, text: str) -> bool:
        if not text:
            return False

        return DONE_MARKER in text

    def _check_done_marker_in_chunk_content(self, content: str) -> bool:
        return self._check_done_marker_in_text(content)

    def _extract_content_from_response(self, data: Dict[str, Any]) -> str:
        content = ""

        if "response" in data:
            data = data["response"]

        if "candidates" in data:
            for candidate in data["candidates"]:
                if "content" in candidate:
                    parts = candidate["content"].get("parts", [])
                    for part in parts:
                        if "text" in part:
                            content += part["text"]

        elif "choices" in data:
            for choice in data["choices"]:
                if "message" in choice and "content" in choice["message"]:
                    content += choice["message"]["content"]

        return content

    def _remove_done_marker_from_line(
        self, line: bytes, line_str: str, data: Dict[str, Any]
    ) -> bytes:
        try:
            if "[done]" not in line_str.lower():
                return line

            log.info("Anti-truncation: Attempting to remove [done] marker from line")
            log.debug(f"Anti-truncation: Original line (first 200 chars): {line_str[:200]}")

            done_pattern = re.compile(r"\s*\[done\]\s*", re.IGNORECASE)

            has_response_wrapper = "response" in data
            log.debug(
                f"Anti-truncation: has_response_wrapper={has_response_wrapper}, data keys={list(data.keys())}"
            )
            if has_response_wrapper:
                inner_data = data["response"]
            else:
                inner_data = data

            log.debug(f"Anti-truncation: inner_data keys={list(inner_data.keys())}")

            log.debug(f"Anti-truncation: inner_data keys={list(inner_data.keys())}")

            if "candidates" in inner_data:
                log.info("Anti-truncation: Processing Gemini format to remove [done] marker")
                modified_inner = inner_data.copy()
                modified_inner["candidates"] = []

                for i, candidate in enumerate(inner_data["candidates"]):
                    modified_candidate = candidate.copy()

                    is_last_candidate = i == len(inner_data["candidates"]) - 1

                    if "content" in candidate:
                        modified_content = candidate["content"].copy()
                        if "parts" in modified_content:
                            modified_parts = []
                            for part in modified_content["parts"]:
                                if "text" in part and isinstance(part["text"], str):
                                    modified_part = part.copy()
                                    original_text = part["text"]

                                    if is_last_candidate:
                                        modified_part["text"] = done_pattern.sub("", part["text"])
                                        if "[done]" in original_text.lower():
                                            log.debug(
                                                f"Anti-truncation: Removed [done] from text: '{original_text[:100]}' -> '{modified_part['text'][:100]}'"
                                            )
                                    modified_parts.append(modified_part)
                                else:
                                    modified_parts.append(part)
                            modified_content["parts"] = modified_parts
                        modified_candidate["content"] = modified_content
                    modified_inner["candidates"].append(modified_candidate)

                if has_response_wrapper:
                    modified_data = data.copy()
                    modified_data["response"] = modified_inner
                else:
                    modified_data = modified_inner

                json_str = json.dumps(modified_data, separators=(",", ":"), ensure_ascii=False)
                result = f"data: {json_str}\n\n".encode("utf-8")
                log.debug(
                    f"Anti-truncation: Modified line (first 200 chars): {result.decode('utf-8', errors='ignore')[:200]}"
                )
                return result

            elif "choices" in inner_data:
                modified_inner = inner_data.copy()
                modified_inner["choices"] = []

                for choice in inner_data["choices"]:
                    modified_choice = choice.copy()
                    if "delta" in choice and "content" in choice["delta"]:
                        modified_delta = choice["delta"].copy()
                        modified_delta["content"] = done_pattern.sub("", choice["delta"]["content"])
                        modified_choice["delta"] = modified_delta
                    elif "message" in choice and "content" in choice["message"]:
                        modified_message = choice["message"].copy()
                        modified_message["content"] = done_pattern.sub(
                            "", choice["message"]["content"]
                        )
                        modified_choice["message"] = modified_message
                    modified_inner["choices"].append(modified_choice)

                if has_response_wrapper:
                    modified_data = data.copy()
                    modified_data["response"] = modified_inner
                else:
                    modified_data = modified_inner

                json_str = json.dumps(modified_data, separators=(",", ":"), ensure_ascii=False)
                return f"data: {json_str}\n\n".encode("utf-8")

            return line

        except Exception as e:
            log.warning(f"Failed to remove [done] marker from line: {str(e)}")
            return line


async def apply_anti_truncation_to_stream(
    request_func,
    payload: Dict[str, Any],
    max_attempts: int = 3,
    enable_prefill_mode: bool = False,
) -> StreamingResponse:

    anti_truncation_payload = apply_anti_truncation(payload)

    processor = AntiTruncationStreamProcessor(
        lambda p: request_func(p),
        anti_truncation_payload,
        max_attempts,
        enable_prefill_mode,
    )

    return StreamingResponse(processor.process_stream(), media_type="text/event-stream")


def is_anti_truncation_enabled(request_data: Dict[str, Any]) -> bool:
    return request_data.get("enable_anti_truncation", False)
