"""Pinned model IDs, not a live entitlement or an invented demo catalog.

R9 paths are relative to the user-provided Downloads/repo snapshot. Only actual
upstream text model IDs are selected (not its virtual reasoning/image aliases).
"""

R9 = "9router-0.5.35/open-sse/providers/registry/"
CATALOG = {
    "cerebras": ("cerebras", ["gpt-oss-120b", "llama-3.3-70b", "qwen-3-32b"]),
    "claude_code": ("claude", ["claude-sonnet-5", "claude-opus-4-8", "claude-haiku-4-5-20251001"]),
    "claude_platform": ("anthropic", ["claude-sonnet-4-20250514", "claude-opus-4-20250514"]),
    "cloudflare": (
        "cloudflare-ai",
        ["@cf/meta/llama-3.2-1b-instruct", "@cf/meta/llama-3.3-70b-instruct-fp8-fast"],
    ),
    "codex": (
        "codex",
        ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5", "gpt-5.4", "gpt-5.4-mini"],
    ),
    "deepseek": (
        "deepseek",
        ["deepseek-v4-pro", "deepseek-v4-flash", "deepseek-chat", "deepseek-reasoner"],
    ),
    "google_ai_studio": (
        "gemini",
        ["gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-2.5-pro", "gemini-2.5-flash"],
    ),
    "google_antigravity": (
        "antigravity",
        [
            "gemini-3-flash-agent",
            "gemini-pro-agent",
            "claude-sonnet-4-6",
            "claude-opus-4-6-thinking",
        ],
    ),
    "grok": ("xai", ["grok-code-fast-1", "grok-4"]),
    "groq": ("groq", ["llama-3.3-70b-versatile", "qwen/qwen3-32b", "openai/gpt-oss-120b"]),
    "kimchi": ("kimchi", ["minimax-m3", "kimi-k2.7", "kimi-k2.6"]),
    "kimi": ("kimi", ["kimi-k2.6", "kimi-k2.5", "kimi-latest"]),
    "kiro": ("kiro", ["claude-opus-4.8", "claude-opus-4.7"]),
    "mistral": ("mistral", ["mistral-large-latest", "codestral-latest", "mistral-medium-latest"]),
    "nvidia": (
        "nvidia",
        ["minimaxai/minimax-m2.7", "moonshotai/kimi-k2.6", "deepseek-ai/deepseek-v4-pro"],
    ),
    "openai_platform": ("openai", ["gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.2"]),
    "opencode": ("opencode-go", ["glm-5.2", "kimi-k2.6", "deepseek-v4-pro"]),
    "xai_console": ("xai", ["grok-4", "grok-4-fast-reasoning", "grok-code-fast-1"]),
    "kilo": (
        "https://kilo.ai/docs/gateway/models-and-providers",
        ["anthropic/claude-sonnet-4.6", "openai/gpt-5.4", "google/gemini-2.5-flash"],
    ),
    "poolside": ("https://docs.poolside.ai/api/openai-api-examples", ["poolside/laguna-s-2.1"]),
    "ollama": ("https://ollama.com/library/llama3.2", ["llama3.2:latest", "llama3.2:1b"]),
    "meta": (
        "docs/providers/muse-code-research-2026-09-16.md",
        [
            "muse-spark-1.1",
            "muse-spark-1.2",
            "muse-spark-1.2-contributor",
            "muse-spark-1.3",
            "muse-spark-1.3-contributor",
        ],
    ),
}
CATALOG["muse_code"] = (CATALOG["meta"][0], ["muse-code/" + m for m in CATALOG["meta"][1]])


def catalog(variant):
    source, models = CATALOG[variant]
    return list(models), source if "/" in source else R9 + source + ".js"
