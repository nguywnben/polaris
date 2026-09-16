"""Link canonical tool results before adapting them to an upstream protocol."""

from __future__ import annotations

import copy


def link_tool_history(request: dict) -> dict:
    """Preserve explicit IDs; infer missing IDs only when the match is unambiguous.

    Gemini permits name-based results. Upstream Chat, Responses and Messages
    require matching IDs, independent of text-part positions or result order.
    Never mutate caller history or guess between concurrent calls of one name.
    """
    request = copy.deepcopy(request)
    parts = [
        part
        for content in request.get("contents") or []
        if isinstance(content, dict)
        for part in content.get("parts") or []
        if isinstance(part, dict)
    ]
    used_ids = {
        str(call["id"])
        for part in parts
        if isinstance(call := part.get("functionCall") or part.get("function_call"), dict)
        and call.get("id")
    }
    pending = {}
    counter = 0
    for part in parts:
        call = part.get("functionCall") or part.get("function_call")
        if isinstance(call, dict):
            if not call.get("id"):
                counter += 1
                while f"polaris_call_{counter}" in used_ids:
                    counter += 1
                call["id"] = f"polaris_call_{counter}"
                used_ids.add(call["id"])
            call_id = str(call["id"])
            if call_id in pending:
                raise ValueError("Invalid tool call history.")
            pending[call_id] = call.get("name")
        result = part.get("functionResponse") or part.get("function_response")
        if isinstance(result, dict):
            if result.get("id"):
                call_id = str(result["id"])
                if call_id not in pending:
                    raise ValueError("Invalid tool call history.")
            else:
                matches = [key for key, name in pending.items() if name == result.get("name")]
                if len(matches) != 1:
                    raise ValueError("Invalid tool call history.")
                call_id = matches[0]
                result["id"] = call_id
            del pending[call_id]
    return request
