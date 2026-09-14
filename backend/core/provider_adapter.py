"""Universal Provider Plugin Interface & Registry for Polaris.

Enables zero-boilerplate pluggable architecture to add arbitrary future providers
(e.g., DeepSeek, Mistral, Bedrock, Vertex AI, Cohere, Together AI, vLLM, SGLang)
without touching the gateway core dispatch pipeline.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Type


@dataclass
class NormalizedRequest:
    messages: List[Dict[str, Any]]
    model: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedResponse:
    id: str
    model: str
    content: str
    finish_reason: str = "stop"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class NormalizedStreamChunk:
    id: str
    model: str
    delta_content: str
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None


class BaseProviderAdapter(abc.ABC):
    """Abstract base class for all current and future LLM provider adapters."""

    provider_id: str = "base"
    supported_models: List[str] = []

    @abc.abstractmethod
    def validate_credential(self, credential_data: Dict[str, Any]) -> bool:
        """Verify if the credential payload is well-formed for this provider."""
        pass

    @abc.abstractmethod
    async def refresh_auth(self, credential_data: Dict[str, Any]) -> Dict[str, Any]:
        """Perform OAuth/API key token refresh lifecycle."""
        return credential_data

    @abc.abstractmethod
    def transform_request(
        self, request: NormalizedRequest, credential_data: Dict[str, Any]
    ) -> Tuple[str, Dict[str, str], Dict[str, Any]]:
        """Transform normalized request into (url, headers, payload)."""
        pass

    @abc.abstractmethod
    def transform_response(self, raw_json: Dict[str, Any], model: str) -> NormalizedResponse:
        """Convert provider response into gateway standard response."""
        pass

    @abc.abstractmethod
    def transform_stream_chunk(
        self, raw_chunk_str: str, model: str
    ) -> Optional[NormalizedStreamChunk]:
        """Convert provider SSE chunk into gateway standard chunk."""
        pass


class ProviderRegistry:
    """Central registry managing all registered provider adapters."""

    _adapters: Dict[str, Type[BaseProviderAdapter]] = {}

    @classmethod
    def register(
        cls, provider_id: str
    ) -> Callable[[Type[BaseProviderAdapter]], Type[BaseProviderAdapter]]:
        def decorator(subclass: Type[BaseProviderAdapter]) -> Type[BaseProviderAdapter]:
            subclass.provider_id = provider_id
            cls._adapters[provider_id.lower()] = subclass
            return subclass

        return decorator

    @classmethod
    def get_adapter_class(cls, provider_id: str) -> Optional[Type[BaseProviderAdapter]]:
        return cls._adapters.get(provider_id.lower())

    @classmethod
    def list_registered_providers(cls) -> List[str]:
        return sorted(list(cls._adapters.keys()))


# Built-in Standard OpenAI-Compatible Provider Adapter (Covers DeepSeek, Mistral, vLLM, Groq, Together)
@ProviderRegistry.register("openai_generic")
class GenericOpenAIAdapter(BaseProviderAdapter):
    provider_id = "openai_generic"
    supported_models = ["*"]

    def validate_credential(self, credential_data: Dict[str, Any]) -> bool:
        return bool(credential_data.get("api_key"))

    async def refresh_auth(self, credential_data: Dict[str, Any]) -> Dict[str, Any]:
        return credential_data

    def transform_request(
        self, request: NormalizedRequest, credential_data: Dict[str, Any]
    ) -> Tuple[str, Dict[str, str], Dict[str, Any]]:
        base_url = credential_data.get("base_url", "https://api.openai.com/v1").rstrip("/")
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {credential_data['api_key']}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "stream": request.stream,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = request.tools
        return url, headers, payload

    def transform_response(self, raw_json: Dict[str, Any], model: str) -> NormalizedResponse:
        choices = raw_json.get("choices", [{}])
        choice = choices[0] if choices else {}
        content = choice.get("message", {}).get("content", "") or ""
        finish_reason = choice.get("finish_reason", "stop")
        usage = raw_json.get("usage", {})
        return NormalizedResponse(
            id=raw_json.get("id", "res-generic"),
            model=model,
            content=content,
            finish_reason=finish_reason,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            raw_response=raw_json,
        )

    def transform_stream_chunk(
        self, raw_chunk_str: str, model: str
    ) -> Optional[NormalizedStreamChunk]:
        import json

        clean_str = raw_chunk_str.strip()
        if clean_str.startswith("data:"):
            clean_str = clean_str[5:].strip()
        if not clean_str or clean_str == "[DONE]":
            return None
        try:
            parsed = json.loads(clean_str)
            choices = parsed.get("choices", [{}])
            choice = choices[0] if choices else {}
            delta = choice.get("delta", {}).get("content", "") or ""
            finish_reason = choice.get("finish_reason")
            return NormalizedStreamChunk(
                id=parsed.get("id", "chunk"),
                model=model,
                delta_content=delta,
                finish_reason=finish_reason,
            )
        except Exception:
            return None
