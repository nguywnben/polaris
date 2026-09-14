"""Report user-facing HTML copy that bypasses the translation contract."""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAGMENTS = ROOT / "frontend" / "fragments"
TRANSLATED_ATTRIBUTES = {
    "aria-label": "data-i18n-aria-label",
    "alt": "data-i18n-alt",
    "placeholder": "data-i18n-placeholder",
    "title": "data-i18n-title",
}
SKIPPED_TAGS = {"code", "pre", "script", "style"}
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
}
TECHNICAL_TEXT = re.compile(
    r"^(?:"
    r"[\d.,%/+:-]+|"
    r"https?://\S+|"
    r"(?:[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+)|"
    r"(?:req-.+|Prometheus|OpenTelemetry|openai|gpt-\d+)|"
    r"(?:OAuth|JSON|ZIP|API Key|Endpoint)|"
    r"(?:Polaris|Google Antigravity|Google AI Studio|Grok Build|SpaceXAI Console|"
    r"Codex|OpenAI Platform|Claude Code|Claude Platform|Ollama|Gemini CLI)|"
    r"(?:Client ID|Client secret|HTTP User-Agent|Payload user agent|Project ID)|"
    r"(?:GET|POST|PUT|DELETE|PATCH|HEAD|HTTP|WebSocket|PKCE)"
    r")$",
    re.IGNORECASE,
)


def _is_user_copy(value: str) -> bool:
    normalized = " ".join(value.split())
    return bool(
        normalized
        and re.search(r"[A-Za-z]", normalized)
        and not TECHNICAL_TEXT.fullmatch(normalized)
    )


class FragmentAuditParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[dict[str, str]] = []
        self.skipped_depth = 0
        self.auto_translated_depth = 0
        self.runtime_depth = 0
        self.technical_depth = 0
        self.issues: list[tuple[int, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value or "" for name, value in attrs}
        self.stack.append(attributes)
        if tag in SKIPPED_TAGS:
            self.skipped_depth += 1
        classes = set(attributes.get("class", "").split())
        if "provider-workspace" in classes or "data-i18n-auto" in attributes:
            self.auto_translated_depth += 1
        if "data-i18n-runtime" in attributes:
            self.runtime_depth += 1
        if "data-i18n-technical" in attributes:
            self.technical_depth += 1
        for attribute, translation_attribute in TRANSLATED_ATTRIBUTES.items():
            value = attributes.get(attribute, "").strip()
            if (
                not self.auto_translated_depth
                and not self.runtime_depth
                and not self.technical_depth
                and _is_user_copy(value)
                and translation_attribute not in attributes
            ):
                self.issues.append((self.getpos()[0], attribute, value))
        if tag in VOID_TAGS:
            self._pop_element(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def _pop_element(self, tag: str) -> None:
        if tag in SKIPPED_TAGS and self.skipped_depth:
            self.skipped_depth -= 1
        if self.stack:
            attributes = self.stack[-1]
            classes = set(attributes.get("class", "").split())
            if (
                "provider-workspace" in classes or "data-i18n-auto" in attributes
            ) and self.auto_translated_depth:
                self.auto_translated_depth -= 1
            if "data-i18n-runtime" in attributes and self.runtime_depth:
                self.runtime_depth -= 1
            if "data-i18n-technical" in attributes and self.technical_depth:
                self.technical_depth -= 1
        if self.stack:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        self._pop_element(tag)

    def handle_data(self, data: str) -> None:
        if (
            self.skipped_depth
            or self.auto_translated_depth
            or self.runtime_depth
            or self.technical_depth
            or not self.stack
            or not _is_user_copy(data)
        ):
            return
        if "data-i18n" not in self.stack[-1]:
            self.issues.append((self.getpos()[0], "text", " ".join(data.split())))


def main() -> int:
    issue_count = 0
    html_files = [ROOT / "frontend" / "index.html", *sorted(FRAGMENTS.rglob("*.html"))]
    for path in html_files:
        parser = FragmentAuditParser()
        parser.feed(path.read_text(encoding="utf-8"))
        if not parser.issues:
            continue
        relative = path.relative_to(ROOT)
        print(f"{relative}: {len(parser.issues)} untranslated value(s)")
        for line, kind, value in parser.issues:
            print(f"  {line}: [{kind}] {value}")
        issue_count += len(parser.issues)
    if issue_count:
        print(f"Found {issue_count} untranslated user-facing HTML value(s).", file=sys.stderr)
        return 1
    print("All user-facing HTML copy is connected to the translation catalog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
