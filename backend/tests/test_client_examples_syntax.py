"""Syntax contracts for every generated SDK client example."""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACCESS_SCRIPT = ROOT / "frontend/js/features/virtual-keys.js"
PLAYGROUND_SCRIPT = ROOT / "frontend/js/features/playground.js"


class ClientExampleSyntaxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.node = shutil.which("node")
        if cls.node is None:
            raise unittest.SkipTest("Node.js is required for generated client syntax checks.")

    def _generate(self, source_path: Path, body: str) -> list[dict[str, str]]:
        harness = f"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync({json.dumps(str(source_path))}, 'utf8');
vm.runInThisContext(source);
{body}
"""
        result = subprocess.run(
            [self.node, "-e", harness],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        return json.loads(result.stdout)

    def _assert_node_syntax(self, examples: list[dict[str, str]]) -> None:
        for example in examples:
            result = subprocess.run(
                [self.node, "--check", "--input-type=module"],
                cwd=ROOT,
                input=example["source"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(
                result.returncode,
                0,
                f"{example['case']} generated invalid Node.js:\n{result.stderr}",
            )

    def test_access_sdk_examples_are_valid_python_and_node_syntax(self) -> None:
        examples = self._generate(
            ACCESS_SCRIPT,
            """
const examples = [];
for (const format of ['python', 'node']) {
    for (const protocol of ['openai_chat', 'openai_responses', 'anthropic', 'gemini']) {
        examples.push({
            case: `${format}/${protocol}`,
            format,
            source: buildAccessClientExample(protocol, 'http://127.0.0.1:4283', format)
        });
    }
}
console.log(JSON.stringify(examples));
""",
        )
        for example in (item for item in examples if item["format"] == "python"):
            try:
                ast.parse(example["source"])
            except SyntaxError as error:
                self.fail(f"{example['case']} generated invalid Python: {error}")
        self._assert_node_syntax([item for item in examples if item["format"] == "node"])

    def test_playground_sdk_matrix_is_valid_python_and_node_syntax(self) -> None:
        examples = self._generate(
            PLAYGROUND_SCRIPT,
            """
const examples = [];
const base = {
    model: 'omway', timeoutSeconds: 30, system: "Answer the user's question.",
    messages: [{role: 'user', content: "What's new?"}],
    temperature: 0.4, topP: 0.8, maxTokens: 256
};
for (const format of ['python', 'node']) {
    for (const protocol of ['openai_chat', 'openai_responses', 'anthropic_messages', 'gemini']) {
        for (const stream of [false, true]) {
            examples.push({
                case: `${format}/${protocol}/stream=${stream}`,
                format,
                source: buildPlaygroundExample({...base, protocol, stream}, format, 'http://127.0.0.1:4283')
            });
        }
    }
}
console.log(JSON.stringify(examples));
""",
        )
        for example in (item for item in examples if item["format"] == "python"):
            try:
                ast.parse(example["source"])
            except SyntaxError as error:
                self.fail(f"{example['case']} generated invalid Python: {error}")
        self._assert_node_syntax([item for item in examples if item["format"] == "node"])


if __name__ == "__main__":
    unittest.main()
