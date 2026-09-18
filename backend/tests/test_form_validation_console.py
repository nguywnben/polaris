"""Contracts for Polaris-owned validation copy, independent of browser messages."""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class FormValidationConsoleTests(unittest.TestCase):
    def test_localized_constraint_messages_never_echo_native_copy_or_field_values(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required for the console contract")
        locales = (ROOT / "frontend/js/core/locales.js").read_text(encoding="utf-8")
        navigation = (ROOT / "frontend/js/features/navigation.js").read_text(encoding="utf-8")
        function = (
            "function controlValidationMessage"
            + navigation.split("function controlValidationMessage", 1)[1].split(
                "function initControlValidationFeedback", 1
            )[0]
        )
        assertions = r"""
function assert(ok, message) { if (!ok) throw new Error(message); }
for (const locale of Object.keys(SUPPORTED_LOCALES)) {
    const row = FORM_VALIDATION_MESSAGES[locale];
    assert(row?.length === FORM_VALIDATION_KEYS.length, `Incomplete locale: ${locale}`);
    assert(row.every(value => typeof value === 'string' && value.length), locale);
    assert(row[1].includes('{limit}') && row[5].includes('{step}'), locale);
}
function t(key, values = {}) {
    let message = SUPPORTED_LOCALES.en.messages[key];
    assert(!!message, key);
    for (const [name, value] of Object.entries(values)) message = message.replaceAll(`{${name}}`, value);
    return message;
}
for (const flag of ['valueMissing', 'tooShort', 'tooLong', 'rangeUnderflow',
                    'rangeOverflow', 'stepMismatch', 'typeMismatch', 'patternMismatch', 'badInput']) {
    const field = {validity: {[flag]: true}, minLength: 12, maxLength: 256,
        min: '1', max: '10', step: '0.5', labels: [], getAttribute: () => 'Field',
        value: 'DO_NOT_ECHO_SECRET', validationMessage: 'DO_NOT_USE_BROWSER_MESSAGE'};
    const message = controlValidationMessage(field);
    assert(message.startsWith('Field: '), flag);
    assert(!message.includes('DO_NOT_'), flag);
    assert(!message.includes('undefined'), flag);
}
assert(controlValidationMessage({validity: {customError: true}, labels: [],
    getAttribute: () => '', validationMessage: 'Application-defined error'}) === 'Application-defined error',
    'Explicit application errors must remain intact');
"""
        result = subprocess.run(
            [node],
            input=locales + "\n" + function + "\n" + assertions,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
