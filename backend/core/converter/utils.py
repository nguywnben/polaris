from typing import Any, Dict

from core.converter.thought_signature import (
    is_internal_placeholder_text,
    is_skip_thought_signature_placeholder,
)


def extract_content_and_reasoning(parts: list) -> tuple:
    content = ""
    reasoning_content = ""
    images = []

    for part in parts:
        if is_skip_thought_signature_placeholder(part):
            continue

        text = part.get("text", "")
        if is_internal_placeholder_text(text):
            continue
        if text:
            if part.get("thought", False):
                reasoning_content += text
            else:
                content += text

        if "inlineData" in part:
            inline_data = part["inlineData"]
            mime_type = inline_data.get("mimeType", "image/png")
            base64_data = inline_data.get("data", "")
            images.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_data}"},
                }
            )

    return content, reasoning_content, images


async def merge_system_messages(request_body: Dict[str, Any]) -> Dict[str, Any]:
    from config import get_compatibility_mode_enabled

    compatibility_mode = await get_compatibility_mode_enabled()

    system_content = request_body.get("system")
    if system_content:
        system_parts = []

        if isinstance(system_content, str):
            if system_content.strip():
                system_parts.append({"text": system_content})
        elif isinstance(system_content, list):
            for item in system_content:
                if isinstance(item, dict):
                    if item.get("type") == "text" and item.get("text", "").strip():
                        system_parts.append({"text": item["text"]})
                elif isinstance(item, str) and item.strip():
                    system_parts.append({"text": item})

        if system_parts:
            if compatibility_mode:
                user_system_message = {
                    "role": "user",
                    "content": system_content
                    if isinstance(system_content, str)
                    else "\n".join(part["text"] for part in system_parts),
                }
                messages = request_body.get("messages", [])
                request_body = request_body.copy()
                request_body["messages"] = [user_system_message] + messages
            else:
                request_body = request_body.copy()
                request_body["systemInstruction"] = {"parts": system_parts}

    messages = request_body.get("messages", [])
    if not messages:
        return request_body

    compatibility_mode = await get_compatibility_mode_enabled()

    if compatibility_mode:
        converted_messages = []
        for message in messages:
            if message.get("role") in {"system", "developer"}:
                converted_message = message.copy()
                converted_message["role"] = "user"
                converted_messages.append(converted_message)
            else:
                converted_messages.append(message)

        result = request_body.copy()
        result["messages"] = converted_messages
        return result
    else:
        system_parts = []

        if "systemInstruction" in request_body:
            existing_instruction = request_body.get("systemInstruction", {})
            if isinstance(existing_instruction, dict):
                system_parts = existing_instruction.get("parts", []).copy()

        remaining_messages = []
        collecting_system = True

        for message in messages:
            role = message.get("role", "")
            content = message.get("content", "")

            if role in {"system", "developer"} and collecting_system:
                if isinstance(content, str):
                    if content.strip():
                        system_parts.append({"text": content})
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            if item.get("type") == "text" and item.get("text", "").strip():
                                system_parts.append({"text": item["text"]})
                        elif isinstance(item, str) and item.strip():
                            system_parts.append({"text": item})
            else:
                collecting_system = False
                if role in {"system", "developer"}:
                    converted_message = message.copy()
                    converted_message["role"] = "user"
                    remaining_messages.append(converted_message)
                else:
                    remaining_messages.append(message)

        if not system_parts:
            return request_body

        result = request_body.copy()

        result["systemInstruction"] = {"parts": system_parts}

        result["messages"] = remaining_messages

        return result
