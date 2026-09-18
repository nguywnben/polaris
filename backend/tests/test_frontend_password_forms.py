import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.panel.root import _assemble_console_html


class FormControlParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.form_stack = []
        self.controls = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "form":
            self.form_stack.append(attributes)
        if tag in {"input", "button"}:
            self.controls.append(
                {
                    "tag": tag,
                    "attributes": attributes,
                    "form": self.form_stack[-1] if self.form_stack else None,
                }
            )

    def handle_endtag(self, tag):
        if tag == "form" and self.form_stack:
            self.form_stack.pop()


class FrontendPasswordFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parser = FormControlParser()
        parser.feed(_assemble_console_html())
        cls.controls = parser.controls

    def find_control(self, control_id):
        return next(
            control for control in self.controls if control["attributes"].get("id") == control_id
        )

    def test_console_password_fields_are_scoped_to_the_admin_form(self):
        for control_id in (
            "currentConsolePassword",
            "newPanelPassword",
            "confirmPanelPassword",
            "updateAccessCredentialsBtn",
        ):
            control = self.find_control(control_id)
            self.assertIsNotNone(control["form"])
            self.assertIn("access-password-form", control["form"].get("class", "").split())

        self.assertEqual(
            self.find_control("updateAccessCredentialsBtn")["attributes"].get("type"),
            "submit",
        )

    def test_password_only_forms_do_not_invent_a_username(self):
        for control in self.controls:
            form = control["form"] or {}
            if form.get("id") not in {"loginForm", "setupForm", "accessPasswordForm"}:
                continue
            attrs = control["attributes"]
            with self.subTest(form=form.get("id"), control=attrs.get("id")):
                self.assertNotEqual(attrs.get("autocomplete"), "username")
                self.assertNotEqual(attrs.get("name"), "username")
                self.assertNotEqual(attrs.get("value"), "admin")

    def test_password_fields_keep_their_password_manager_purpose(self):
        for control_id, purpose in (
            ("loginPassword", "current-password"),
            ("setupPassword", "new-password"),
            ("setupPasswordConfirm", "new-password"),
            ("currentConsolePassword", "current-password"),
            ("newPanelPassword", "new-password"),
            ("confirmPanelPassword", "new-password"),
        ):
            with self.subTest(control=control_id):
                control = self.find_control(control_id)
                self.assertEqual(control["attributes"].get("autocomplete"), purpose)
                self.assertTrue(control["attributes"].get("name"))
                self.assertEqual(control["form"].get("autocomplete"), "on")

    def test_provider_user_agents_are_excluded_from_autofill(self):
        for control_id in ("antigravityUserAgent", "antigravityPayloadUserAgent"):
            control = self.find_control(control_id)
            self.assertEqual(control["attributes"].get("autocomplete"), "off")
            self.assertIsNone(control["form"])


if __name__ == "__main__":
    unittest.main()
