from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, SecretStr, WithJsonSchema, model_validator
from pydantic.json_schema import SkipJsonSchema


def model_to_dict(model: BaseModel) -> Dict[str, Any]:
    return model.model_dump(exclude_none=True)


def _reject_unknown_input_keys(value: Any, allowed: set[str], label: str) -> Any:
    if isinstance(value, dict):
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"Unknown {label} fields: {', '.join(sorted(unknown))}.")
    return value


def _validate_image_data_url(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.startswith("data:image/"):
        raise ValueError(f"Only image data URLs are supported for {label}.")
    prefix, separator, payload = value.partition(";base64,")
    if not separator or not prefix.removeprefix("data:") or not payload or ";" in prefix:
        raise ValueError(f"Invalid base64 image data URL for {label}.")


# Common Models
class Model(BaseModel):
    id: str
    object: str = "model"
    created: Optional[int] = None
    owned_by: Optional[str] = "google"


class ModelList(BaseModel):
    object: str = "list"
    data: List[Model]


# OpenAI Models
class OpenAIToolFunction(BaseModel):
    name: str
    arguments: str  # JSON string

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_fields(cls, value: Any) -> Any:
        return _reject_unknown_input_keys(value, {"name", "arguments"}, "OpenAI tool function")


class OpenAIToolCall(BaseModel):
    id: str
    type: str = "function"
    function: OpenAIToolFunction

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_fields(cls, value: Any) -> Any:
        return _reject_unknown_input_keys(value, {"id", "type", "function"}, "OpenAI tool call")


class OpenAITool(BaseModel):
    type: str = "function"
    function: Dict[str, Any]

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_fields(cls, value: Any) -> Any:
        value = _reject_unknown_input_keys(value, {"type", "function"}, "OpenAI tool")
        if isinstance(value, dict) and isinstance(value.get("function"), dict):
            _reject_unknown_input_keys(
                value["function"],
                {"name", "description", "parameters"},
                "OpenAI tool definition",
            )
            function = value["function"]
            if not isinstance(function.get("name"), str) or not function["name"].strip():
                raise ValueError("OpenAI function tools require a name.")
            if "parameters" in function and not isinstance(function["parameters"], dict):
                raise ValueError("OpenAI function tool parameters must be an object.")
        if isinstance(value, dict) and value.get("type", "function") != "function":
            raise ValueError("Only OpenAI function tools are supported.")
        return value


class OpenAIChatMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]], None] = None
    reasoning_content: Optional[str] = None
    name: Optional[str] = None
    tool_calls: Optional[List[OpenAIToolCall]] = None
    tool_call_id: Optional[str] = None  # for role="tool"

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_fields(cls, value: Any) -> Any:
        return _reject_unknown_input_keys(
            value,
            {"role", "content", "reasoning_content", "name", "tool_calls", "tool_call_id"},
            "OpenAI message",
        )

    @model_validator(mode="after")
    def validate_translatable_message(self) -> "OpenAIChatMessage":
        if self.role not in {"developer", "system", "user", "assistant", "tool"}:
            raise ValueError(f"Unsupported OpenAI message role: {self.role}.")
        if self.name is not None and self.role != "tool":
            raise ValueError("OpenAI message name is supported only for tool results.")
        if self.tool_calls is not None and self.role != "assistant":
            raise ValueError("OpenAI tool_calls are supported only for assistant messages.")
        if self.tool_call_id is not None and self.role != "tool":
            raise ValueError("OpenAI tool_call_id is supported only for tool messages.")
        if not isinstance(self.content, list):
            return self
        for part in self.content:
            if not isinstance(part, dict):
                raise ValueError("OpenAI message content parts must be objects.")
            part_type = part.get("type")
            if part_type == "text":
                if set(part) - {"type", "text"} or not isinstance(part.get("text"), str):
                    raise ValueError("Invalid OpenAI text content part.")
                continue
            if part_type == "image_url":
                image = part.get("image_url")
                if set(part) - {"type", "image_url"} or not isinstance(image, dict):
                    raise ValueError("Invalid OpenAI image_url content part.")
                if set(image) - {"url", "detail"}:
                    raise ValueError("Unknown OpenAI image_url field.")
                url = image.get("url")
                _validate_image_data_url(url, "OpenAI image input")
                continue
            raise ValueError(f"Unsupported OpenAI message content type: {part_type}.")
        return self


class OpenAIChatCompletionRequest(BaseModel):
    model: str
    messages: List[OpenAIChatMessage]
    stream: bool = False
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(None, ge=1)
    max_completion_tokens: SkipJsonSchema[Optional[int]] = Field(None, ge=1)
    stop: Optional[Union[str, List[str]]] = None
    frequency_penalty: Optional[float] = Field(None, ge=-2.0, le=2.0)
    presence_penalty: Optional[float] = Field(None, ge=-2.0, le=2.0)
    n: Optional[int] = Field(1, ge=1, le=128)
    seed: Optional[int] = None
    response_format: Optional[Dict[str, Any]] = None
    top_k: Optional[int] = Field(None, ge=1)
    tools: Optional[List[OpenAITool]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    reasoning_effort: SkipJsonSchema[Optional[str]] = None
    size: SkipJsonSchema[Optional[str]] = None

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_fields(cls, value: Any) -> Any:
        return _reject_unknown_input_keys(
            value,
            {
                "model",
                "messages",
                "stream",
                "temperature",
                "top_p",
                "max_tokens",
                "max_completion_tokens",
                "stop",
                "frequency_penalty",
                "presence_penalty",
                "n",
                "seed",
                "response_format",
                "top_k",
                "tools",
                "tool_choice",
                "reasoning_effort",
                "size",
            },
            "OpenAI Chat request",
        )

    @model_validator(mode="after")
    def reject_unsupported_reasoning_control(self) -> "OpenAIChatCompletionRequest":
        if self.reasoning_effort is not None:
            raise ValueError(
                "reasoning_effort is not supported by the Chat Completions translation."
            )
        if any(message.reasoning_content is not None for message in self.messages):
            raise ValueError("reasoning_content cannot be translated safely in request history.")
        if self.response_format is not None:
            format_type = self.response_format.get("type")
            if format_type in {"text", "json_object"}:
                _reject_unknown_input_keys(self.response_format, {"type"}, "OpenAI response_format")
            elif format_type == "json_schema":
                _reject_unknown_input_keys(
                    self.response_format, {"type", "json_schema"}, "OpenAI response_format"
                )
                schema = self.response_format.get("json_schema")
                if not isinstance(schema, dict):
                    raise ValueError("OpenAI json_schema response format requires an object.")
                _reject_unknown_input_keys(
                    schema,
                    {"name", "description", "schema", "strict"},
                    "OpenAI json_schema response format",
                )
                if not isinstance(schema.get("name"), str) or not isinstance(
                    schema.get("schema"), dict
                ):
                    raise ValueError("OpenAI json_schema response format requires name and schema.")
            else:
                raise ValueError(f"Unsupported OpenAI response format: {format_type}.")
        if isinstance(self.tool_choice, dict):
            _reject_unknown_input_keys(self.tool_choice, {"type", "function"}, "OpenAI tool_choice")
            function = self.tool_choice.get("function")
            if self.tool_choice.get("type") != "function" or not isinstance(function, dict):
                raise ValueError("OpenAI object tool_choice must select a function.")
            _reject_unknown_input_keys(function, {"name"}, "OpenAI tool_choice function")
            if not isinstance(function.get("name"), str) or not function["name"].strip():
                raise ValueError("OpenAI tool_choice function requires a name.")
        elif self.tool_choice not in {None, "none", "auto", "required"}:
            raise ValueError(f"Unsupported OpenAI tool_choice: {self.tool_choice}.")
        return self

    model_config = ConfigDict(extra="allow")


ChatCompletionRequest = OpenAIChatCompletionRequest


class OpenAIResponsesRequest(BaseModel):
    """Supported subset of the OpenAI Responses create contract."""

    model: str
    input: Union[str, List[Dict[str, Any]]]
    instructions: Optional[str] = None
    stream: bool = False
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_output_tokens: Optional[int] = Field(None, ge=1)
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    parallel_tool_calls: bool = True
    metadata: Optional[Dict[str, str]] = None
    store: bool = False
    text: SkipJsonSchema[Optional[Dict[str, Any]]] = None
    reasoning: SkipJsonSchema[Optional[Dict[str, Any]]] = None
    previous_response_id: SkipJsonSchema[Optional[str]] = None
    conversation: SkipJsonSchema[Optional[Union[str, Dict[str, Any]]]] = None

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_fields(cls, value: Any) -> Any:
        return _reject_unknown_input_keys(
            value,
            {
                "model",
                "input",
                "instructions",
                "stream",
                "temperature",
                "top_p",
                "max_output_tokens",
                "tools",
                "tool_choice",
                "parallel_tool_calls",
                "metadata",
                "store",
                "text",
                "reasoning",
                "previous_response_id",
                "conversation",
            },
            "OpenAI Responses request",
        )

    @model_validator(mode="after")
    def validate_translatable_responses_request(self) -> "OpenAIResponsesRequest":
        if self.reasoning is not None:
            raise ValueError("reasoning is not supported by the Responses translation.")
        if self.text is not None:
            if set(self.text) != {"format"} or not isinstance(self.text.get("format"), dict):
                raise ValueError("Responses text must contain exactly one format object.")
            output_format = self.text["format"]
            format_type = output_format.get("type")
            allowed = (
                {"type"}
                if format_type in {"text", "json_object"}
                else {"type", "name", "description", "schema", "strict"}
            )
            if format_type not in {"text", "json_object", "json_schema"}:
                raise ValueError(f"Unsupported Responses text format: {format_type}.")
            if set(output_format) - allowed:
                raise ValueError("Unknown Responses text format field.")
            if format_type == "json_schema" and (
                not isinstance(output_format.get("name"), str)
                or not isinstance(output_format.get("schema"), dict)
            ):
                raise ValueError("Responses json_schema format requires name and schema.")
        if isinstance(self.input, list):
            for item in self.input:
                self._validate_input_item(item)
        for tool in self.tools or []:
            if not isinstance(tool, dict):
                raise ValueError("Responses tools must be objects.")
            if tool.get("type") != "function":
                continue
            _reject_unknown_input_keys(
                tool,
                {"type", "name", "description", "parameters"},
                "Responses function tool",
            )
            if not isinstance(tool.get("name"), str):
                raise ValueError("Responses function tools require a name.")
            if "parameters" in tool and not isinstance(tool["parameters"], dict):
                raise ValueError("Responses function tool parameters must be an object.")
        if isinstance(self.tool_choice, dict):
            _reject_unknown_input_keys(self.tool_choice, {"type", "name"}, "Responses tool_choice")
            if self.tool_choice.get("type") != "function" or not isinstance(
                self.tool_choice.get("name"), str
            ):
                raise ValueError("Responses object tool_choice must select a named function.")
        elif self.tool_choice not in {None, "none", "auto", "required"}:
            raise ValueError(f"Unsupported Responses tool_choice: {self.tool_choice}.")
        return self

    @staticmethod
    def _validate_input_item(item: Dict[str, Any]) -> None:
        if not isinstance(item, dict):
            raise ValueError("Responses input items must be objects.")
        item_type = item.get("type")
        if item_type in {None, "message"} and item.get("role") in {
            "developer",
            "system",
            "user",
            "assistant",
        }:
            _reject_unknown_input_keys(item, {"type", "role", "content"}, "Responses message")
            content = item.get("content", "")
            if isinstance(content, str):
                return
            if not isinstance(content, list):
                raise ValueError("Responses message content must be text or a list of parts.")
            for part in content:
                if not isinstance(part, dict):
                    raise ValueError("Responses content parts must be objects.")
                part_type = part.get("type")
                if part_type in {"input_text", "output_text", "text"}:
                    if set(part) - {"type", "text"} or not isinstance(part.get("text"), str):
                        raise ValueError("Invalid Responses text content part.")
                    continue
                if part_type == "input_image":
                    if set(part) - {"type", "image_url", "detail"}:
                        raise ValueError("Unknown Responses input_image field.")
                    _validate_image_data_url(part.get("image_url"), "Responses image input")
                    continue
                raise ValueError(f"Unsupported Responses content type: {part_type}.")
            return
        if item_type == "function_call":
            _reject_unknown_input_keys(
                item,
                {"type", "id", "call_id", "name", "arguments"},
                "Responses function_call",
            )
            if not item.get("name") or not isinstance(item.get("arguments"), str):
                raise ValueError("Responses function_call requires name and JSON arguments.")
            return
        if item_type == "function_call_output":
            _reject_unknown_input_keys(
                item,
                {"type", "call_id", "output"},
                "Responses function_call_output",
            )
            if not item.get("call_id") or "output" not in item:
                raise ValueError("Responses function_call_output requires call_id and output.")
            return
        raise ValueError(f"Unsupported Responses input item type: {item_type}.")

    model_config = ConfigDict(extra="allow")


class OpenAIChatCompletionChoice(BaseModel):
    index: int
    message: OpenAIChatMessage
    finish_reason: Optional[str] = None
    logprobs: Optional[Dict[str, Any]] = None


class OpenAIChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[OpenAIChatCompletionChoice]
    usage: Optional[Dict[str, Any]] = None
    system_fingerprint: Optional[str] = None


class OpenAIDelta(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None
    reasoning_content: Optional[str] = None


class OpenAIChatCompletionStreamChoice(BaseModel):
    index: int
    delta: OpenAIDelta
    finish_reason: Optional[str] = None
    logprobs: Optional[Dict[str, Any]] = None


class OpenAIChatCompletionStreamResponse(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[OpenAIChatCompletionStreamChoice]
    system_fingerprint: Optional[str] = None


# Gemini Models
class GeminiPart(BaseModel):
    text: Optional[str] = None
    inlineData: Optional[Dict[str, Any]] = None
    fileData: Optional[Dict[str, Any]] = None
    thought: Optional[bool] = None
    thoughtSignature: SkipJsonSchema[Optional[str]] = None
    functionCall: SkipJsonSchema[Optional[Dict[str, Any]]] = None
    functionResponse: SkipJsonSchema[Optional[Dict[str, Any]]] = None
    executableCode: SkipJsonSchema[Optional[Dict[str, Any]]] = None
    codeExecutionResult: SkipJsonSchema[Optional[Dict[str, Any]]] = None

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_fields(cls, value: Any) -> Any:
        return _reject_unknown_input_keys(
            value,
            {
                "text",
                "inlineData",
                "fileData",
                "thought",
                "thoughtSignature",
                "functionCall",
                "functionResponse",
                "executableCode",
                "codeExecutionResult",
            },
            "Gemini part",
        )

    model_config = ConfigDict(extra="allow")


class GeminiContent(BaseModel):
    role: str
    parts: List[GeminiPart]

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_fields(cls, value: Any) -> Any:
        return _reject_unknown_input_keys(value, {"role", "parts"}, "Gemini content")


class GeminiSystemInstruction(BaseModel):
    role: SkipJsonSchema[Optional[str]] = None
    parts: List[GeminiPart]

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_fields(cls, value: Any) -> Any:
        return _reject_unknown_input_keys(value, {"role", "parts"}, "Gemini system instruction")


class GeminiImageConfig(BaseModel):
    aspect_ratio: Optional[str] = (
        None  # "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"
    )
    image_size: Optional[str] = None  # "1K", "2K", "4K"
    aspectRatio: SkipJsonSchema[Optional[str]] = None
    imageSize: SkipJsonSchema[Optional[str]] = None

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_fields(cls, value: Any) -> Any:
        return _reject_unknown_input_keys(
            value,
            {"aspect_ratio", "image_size", "aspectRatio", "imageSize"},
            "Gemini image config",
        )


class GeminiGenerationConfig(BaseModel):
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    topP: Optional[float] = Field(None, ge=0.0, le=1.0)
    topK: Optional[int] = Field(None, ge=1)
    maxOutputTokens: Optional[int] = Field(None, ge=1)
    stopSequences: Optional[List[str]] = None
    responseMimeType: Optional[str] = None
    responseSchema: Optional[Dict[str, Any]] = None
    candidateCount: Optional[int] = Field(None, ge=1, le=8)
    seed: Optional[int] = None
    frequencyPenalty: Optional[float] = Field(None, ge=-2.0, le=2.0)
    presencePenalty: Optional[float] = Field(None, ge=-2.0, le=2.0)
    thinkingConfig: Optional[Dict[str, Any]] = None

    response_modalities: Optional[List[str]] = None  # ["TEXT", "IMAGE"]
    image_config: Optional[GeminiImageConfig] = None
    responseModalities: SkipJsonSchema[Optional[List[str]]] = None
    imageConfig: SkipJsonSchema[Optional[GeminiImageConfig]] = None

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_fields(cls, value: Any) -> Any:
        return _reject_unknown_input_keys(
            value,
            {
                "temperature",
                "topP",
                "topK",
                "candidateCount",
                "maxOutputTokens",
                "stopSequences",
                "responseMimeType",
                "responseSchema",
                "seed",
                "frequencyPenalty",
                "presencePenalty",
                "thinkingConfig",
                "response_modalities",
                "image_config",
                "responseModalities",
                "imageConfig",
            },
            "Gemini generation config",
        )


class GeminiSafetySetting(BaseModel):
    category: str
    threshold: str

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_fields(cls, value: Any) -> Any:
        return _reject_unknown_input_keys(value, {"category", "threshold"}, "Gemini safety")


class GeminiRequest(BaseModel):
    contents: List[GeminiContent]
    systemInstruction: Optional[GeminiSystemInstruction] = None
    generationConfig: Optional[GeminiGenerationConfig] = None
    safetySettings: Optional[List[GeminiSafetySetting]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    toolConfig: Optional[Dict[str, Any]] = None
    cachedContent: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_fields(cls, value: Any) -> Any:
        return _reject_unknown_input_keys(
            value,
            {
                "contents",
                "systemInstruction",
                "generationConfig",
                "safetySettings",
                "tools",
                "toolConfig",
                "cachedContent",
            },
            "Gemini request",
        )

    model_config = ConfigDict(extra="allow")


class GeminiCandidate(BaseModel):
    content: GeminiContent
    finishReason: Optional[str] = None
    index: int = 0
    safetyRatings: Optional[List[Dict[str, Any]]] = None
    citationMetadata: Optional[Dict[str, Any]] = None
    tokenCount: Optional[int] = None


class GeminiUsageMetadata(BaseModel):
    promptTokenCount: Optional[int] = None
    candidatesTokenCount: Optional[int] = None
    totalTokenCount: Optional[int] = None
    cachedContentTokenCount: Optional[int] = None
    thoughtsTokenCount: Optional[int] = None


class GeminiResponse(BaseModel):
    candidates: List[GeminiCandidate]
    usageMetadata: Optional[GeminiUsageMetadata] = None
    modelVersion: Optional[str] = None


# Claude Models
class ClaudeContentBlock(BaseModel):
    type: str  # "text", "image", "tool_use", "tool_result"
    text: Optional[str] = None
    source: Optional[Dict[str, Any]] = None  # for image type
    id: Optional[str] = None  # for tool_use
    name: Optional[str] = None  # for tool_use
    input: Optional[Dict[str, Any]] = None  # for tool_use
    tool_use_id: Optional[str] = None  # for tool_result
    content: Optional[Union[str, List[Dict[str, Any]]]] = None  # for tool_result
    thinking: SkipJsonSchema[Optional[str]] = None
    signature: SkipJsonSchema[Optional[str]] = None
    thoughtSignature: SkipJsonSchema[Optional[str]] = None
    data: SkipJsonSchema[Optional[str]] = None

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_fields(cls, value: Any) -> Any:
        return _reject_unknown_input_keys(
            value,
            {
                "type",
                "text",
                "source",
                "id",
                "name",
                "input",
                "tool_use_id",
                "content",
                "thinking",
                "signature",
                "thoughtSignature",
                "data",
            },
            "Anthropic content block",
        )

    @model_validator(mode="after")
    def validate_translatable_block(self) -> "ClaudeContentBlock":
        if self.type == "text":
            if self.text is None:
                raise ValueError("Anthropic text blocks require text.")
            return self
        if self.type == "image":
            source = self.source
            if not isinstance(source, dict) or set(source) - {"type", "media_type", "data"}:
                raise ValueError("Invalid Anthropic image source.")
            if source.get("type") != "base64" or not isinstance(source.get("data"), str):
                raise ValueError("Only base64 Anthropic image inputs are supported.")
            return self
        if self.type == "tool_use":
            if not self.id or not self.name or not isinstance(self.input, dict):
                raise ValueError("Anthropic tool_use blocks require id, name, and input.")
            return self
        if self.type == "tool_result":
            if not self.tool_use_id:
                raise ValueError("Anthropic tool_result blocks require tool_use_id.")
            if isinstance(self.content, list):
                for part in self.content:
                    if (
                        not isinstance(part, dict)
                        or set(part) - {"type", "text"}
                        or part.get("type") != "text"
                        or not isinstance(part.get("text"), str)
                    ):
                        raise ValueError("Anthropic tool_result lists support text blocks only.")
            return self
        if self.type == "thinking":
            signature = self.signature or self.thoughtSignature
            if self.thinking is None or not signature:
                raise ValueError("Anthropic thinking blocks require thinking and signature.")
            return self
        if self.type == "redacted_thinking":
            raise ValueError(
                "Anthropic redacted_thinking request blocks cannot be translated safely."
            )
        raise ValueError(f"Unsupported Anthropic content block type: {self.type}.")


class ClaudeMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: Union[str, List[ClaudeContentBlock]]

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_fields(cls, value: Any) -> Any:
        return _reject_unknown_input_keys(value, {"role", "content"}, "Anthropic message")


class ClaudeTool(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    strict: SkipJsonSchema[Optional[bool]] = None

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_fields(cls, value: Any) -> Any:
        value = _reject_unknown_input_keys(
            value,
            {"name", "description", "input_schema"},
            "Anthropic tool",
        )
        return value


class ClaudeMetadata(BaseModel):
    user_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_fields(cls, value: Any) -> Any:
        return _reject_unknown_input_keys(value, {"user_id"}, "Anthropic metadata")


class ClaudeRequest(BaseModel):
    model: str
    messages: List[ClaudeMessage]
    max_tokens: int = Field(..., ge=1)
    system: Optional[Union[str, List[Dict[str, Any]]]] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    top_k: Optional[int] = Field(None, ge=1)
    stop_sequences: Optional[List[str]] = None
    stream: bool = False
    metadata: Optional[ClaudeMetadata] = None
    tools: Optional[List[ClaudeTool]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    thinking: SkipJsonSchema[Optional[Dict[str, Any]]] = None
    output_config: SkipJsonSchema[Optional[Dict[str, Any]]] = None
    size: SkipJsonSchema[Optional[str]] = None

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_fields(cls, value: Any) -> Any:
        return _reject_unknown_input_keys(
            value,
            {
                "model",
                "messages",
                "max_tokens",
                "system",
                "temperature",
                "top_p",
                "top_k",
                "stop_sequences",
                "stream",
                "metadata",
                "tools",
                "tool_choice",
                "thinking",
                "output_config",
                "size",
            },
            "Anthropic request",
        )

    @model_validator(mode="after")
    def validate_translatable_options(self) -> "ClaudeRequest":
        if isinstance(self.system, list):
            for block in self.system:
                _reject_unknown_input_keys(block, {"type", "text"}, "Anthropic system block")
                if block.get("type") != "text" or not isinstance(block.get("text"), str):
                    raise ValueError("Anthropic system lists support text blocks only.")
        if self.thinking is not None:
            _reject_unknown_input_keys(
                self.thinking, {"type", "budget_tokens"}, "Anthropic thinking config"
            )
            thinking_type = self.thinking.get("type")
            budget = self.thinking.get("budget_tokens")
            if thinking_type not in {"enabled", "disabled"}:
                raise ValueError(f"Unsupported Anthropic thinking type: {thinking_type}.")
            if budget is not None and (type(budget) is not int or budget < 1):
                raise ValueError("Anthropic thinking budget_tokens must be a positive integer.")
        if self.output_config is not None:
            _reject_unknown_input_keys(self.output_config, {"format"}, "Anthropic output_config")
            output_format = self.output_config.get("format")
            if not isinstance(output_format, dict):
                raise ValueError("Anthropic output_config requires a format object.")
            _reject_unknown_input_keys(output_format, {"type", "schema"}, "Anthropic output format")
            if output_format.get("type") != "json_schema" or not isinstance(
                output_format.get("schema"), dict
            ):
                raise ValueError("Only Anthropic json_schema output format is supported.")
        if isinstance(self.tool_choice, dict):
            choice_type = self.tool_choice.get("type")
            allowed = {"type", "name"} if choice_type == "tool" else {"type"}
            _reject_unknown_input_keys(self.tool_choice, allowed, "Anthropic tool_choice")
            if choice_type not in {"auto", "any", "tool"}:
                raise ValueError(f"Unsupported Anthropic tool_choice type: {choice_type}.")
            if choice_type == "tool" and not isinstance(self.tool_choice.get("name"), str):
                raise ValueError("Anthropic tool_choice type tool requires a name.")
        elif self.tool_choice is not None:
            raise ValueError("Anthropic tool_choice must be an object.")
        return self

    model_config = ConfigDict(extra="allow")


class ClaudeUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: Optional[int] = None
    cache_read_input_tokens: Optional[int] = None


class ClaudeResponse(BaseModel):
    id: str
    type: str = "message"
    role: str = "assistant"
    content: List[ClaudeContentBlock]
    model: str
    stop_reason: Optional[str] = None
    stop_sequence: Optional[str] = None
    usage: ClaudeUsage


class ClaudeStreamEvent(BaseModel):
    type: str  # "message_start", "content_block_start", "content_block_delta", "content_block_stop", "message_delta", "message_stop"
    message: Optional[ClaudeResponse] = None
    index: Optional[int] = None
    content_block: Optional[ClaudeContentBlock] = None
    delta: Optional[Dict[str, Any]] = None
    usage: Optional[ClaudeUsage] = None

    model_config = ConfigDict(extra="allow")


# Error Models
class APIError(BaseModel):
    message: str
    type: str = "api_error"
    code: Optional[int] = None


class ErrorResponse(BaseModel):
    error: APIError


# Control Panel Models
class SystemStatus(BaseModel):
    status: str
    timestamp: str
    credentials: Dict[str, int]
    config: Dict[str, Any]
    current_credential: str


class CredentialInfo(BaseModel):
    filename: str
    project_id: Optional[str] = None
    status: Dict[str, Any]
    size: Optional[int] = None
    modified_time: Optional[str] = None
    error: Optional[str] = None


class LogEntry(BaseModel):
    timestamp: str
    level: str
    message: str
    module: Optional[str] = None


class ConfigValue(BaseModel):
    key: str
    value: Any
    env_locked: bool = False
    description: Optional[str] = None


# Authentication Models
class AuthRequest(BaseModel):
    project_id: Optional[str] = None
    user_session: Optional[str] = None


class AuthResponse(BaseModel):
    success: bool
    auth_url: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None
    credentials: Optional[Dict[str, Any]] = None
    file_path: Optional[str] = None
    credential_saved: Optional[bool] = None
    credential_action: Optional[str] = None
    credential_message: Optional[str] = None
    email: Optional[str] = None
    existing_expiry: Optional[str] = None
    incoming_expiry: Optional[str] = None
    deleted_duplicates: Optional[List[str]] = None
    requires_manual_project_id: Optional[bool] = None
    requires_project_selection: Optional[bool] = None
    available_projects: Optional[List[Dict[str, str]]] = None


class CredentialStatus(BaseModel):
    disabled: bool = False
    error_codes: List[int] = []
    last_success: Optional[str] = None


# Web Routes Models
class LoginRequest(BaseModel):
    password: str


class RecoveryRequest(BaseModel):
    password: SecretStr


_SetupSecret = Annotated[SecretStr, WithJsonSchema({"type": "string"})]


class SetupRequest(BaseModel):
    # r1-v1 exposed plain JSON strings here. Keep that wire schema while retaining
    # SecretStr's redacted representation inside the process.
    password: _SetupSecret
    confirm_password: Optional[_SetupSecret] = None
    setup_token: Optional[_SetupSecret] = None


class SetupPreflightRequest(BaseModel):
    setup_token: Optional[SecretStr] = None


class AuthStartRequest(BaseModel):
    project_id: Optional[str] = None
    mode: Optional[str] = "code_assist"


class AuthCallbackRequest(BaseModel):
    project_id: Optional[str] = None
    mode: Optional[str] = "code_assist"


class AuthCallbackUrlRequest(BaseModel):
    callback_url: str = Field(min_length=8, max_length=8192)
    project_id: Optional[str] = None
    mode: Optional[str] = "code_assist"


class GoogleAIStudioCredentialRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=4096)


class XaiCredentialRequest(BaseModel):
    api_key: str = Field(min_length=16, max_length=1024)


class XaiOAuthCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=4096)
    state: str = Field(min_length=1, max_length=512)


class OpenAIPlatformCredentialRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=1024)


class ClaudePlatformCredentialRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=1024)


class ClaudeOAuthCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=4096)
    state: str = Field(min_length=1, max_length=512)


class GeminiCliOAuthCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=4096)
    state: Optional[str] = Field(default="", max_length=512)


class OllamaCredentialRequest(BaseModel):
    base_url: str = Field(min_length=1, max_length=2048)
    api_key: str = Field(default="", max_length=4096)


class CodexOAuthCompleteRequest(BaseModel):
    flow_id: str = Field(min_length=1, max_length=256)


class CredentialModelTestRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)


class CredentialUpdateRequest(BaseModel):
    credential_label: Optional[str] = Field(default=None, min_length=1, max_length=128)
    api_key: Optional[SecretStr] = Field(default=None, min_length=1, max_length=4096)
    base_url: Optional[str] = Field(default=None, min_length=1, max_length=2048)

    @model_validator(mode="after")
    def require_at_least_one_change(self) -> "CredentialUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Provide at least one credential field to update.")
        return self


class CredFileActionRequest(BaseModel):
    filename: str
    action: str  # enable, disable, delete


class CredFileBatchActionRequest(BaseModel):
    action: Literal[
        "enable",
        "disable",
        "delete",
        "enable_credit",
        "disable_credit",
    ]
    filenames: List[str] = Field(default_factory=list, max_length=100)
    selection_token: Optional[str] = Field(default=None, min_length=16, max_length=256)
    preview: bool = False
    preview_token: Optional[str] = Field(default=None, min_length=16, max_length=256)
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=128)


class CredentialBatchItemResult(BaseModel):
    target_index: int = Field(ge=0, le=99)
    filename: Optional[str] = None
    variant_id: str
    operation: str
    status: Literal[
        "eligible",
        "succeeded",
        "unsupported",
        "not_found",
        "invalid",
        "duplicate",
        "timed_out",
        "failed",
    ]
    code: str


class CredentialBatchOperationResponse(BaseModel):
    success: bool
    preview: bool
    action: str
    operation: str
    requires_preview: bool
    requested_count: int = Field(ge=1, le=100)
    success_count: int = Field(ge=0, le=100)
    total_count: int = Field(ge=1, le=100)
    outcome_counts: Dict[str, int]
    results: List[CredentialBatchItemResult]
    errors: List[str]
    message: str
    preview_token: Optional[str] = None
    preview_expires_in_seconds: Optional[int] = None
    history_retained_anonymously: Optional[bool] = None


class ConfigSaveRequest(BaseModel):
    config: dict


class AccessCredentialsUpdateRequest(BaseModel):
    current_password: str
    panel_password: Optional[str] = None
    panel_password_confirm: Optional[str] = None


class VirtualModelPoolUpdateRequest(BaseModel):
    selected_models: List[str] = Field(default_factory=list, max_length=64)
    enabled: bool = True
