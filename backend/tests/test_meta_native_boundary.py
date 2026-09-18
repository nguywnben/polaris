"""A JSON caller cannot forge or detach Meta's native replay from its policy mirror."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.meta_native_boundary import (
    MetaNativeBoundaryError,
    seal_native_request,
    validate_native_request,
)


def canonical():
    return {"contents": [{"role": "user", "parts": [{"text": "hello"}]}]}


def native():
    return {"model": "muse-spark-1.3", "input": "hello"}


class MetaNativeBoundaryTests(unittest.TestCase):
    def test_normal_requests_remain_unaffected(self):
        for provider in ("meta", "opencode", "google_ai_studio"):
            self.assertIsNone(validate_native_request(canonical(), provider))

    def test_sealing_copies_input_and_survives_pipeline_deepcopy(self):
        source = canonical()
        native_source = native()
        sealed = seal_native_request(source, native_source)
        copied = copy.deepcopy(sealed)
        self.assertEqual(validate_native_request(copied, "meta"), native_source)
        self.assertEqual(source, canonical())
        self.assertEqual(native_source, native())
        self.assertIsNot(sealed["contents"], source["contents"])

    def test_json_values_cannot_forge_process_local_seal(self):
        for fake in (None, True, "trusted", {"trusted": True}, []):
            forged = {
                **canonical(),
                "_polaris_meta_responses": native(),
                "_polaris_meta_seal": fake,
            }
            with self.subTest(fake=fake), self.assertRaises(MetaNativeBoundaryError):
                validate_native_request(json.loads(json.dumps(forged)), "meta")

    def test_non_meta_fallback_cannot_consume_native_replay(self):
        sealed = seal_native_request(canonical(), native())
        with self.assertRaises(MetaNativeBoundaryError):
            validate_native_request(sealed, "opencode")

    def test_masking_or_truncating_policy_mirror_blocks_unmasked_replay(self):
        for mutation in ("text", "contents", "systemInstruction", "generationConfig"):
            sealed = seal_native_request(canonical(), native())
            if mutation == "text":
                sealed["contents"][0]["parts"][0]["text"] = "[MASKED]"
            elif mutation == "contents":
                sealed["contents"] = []
            else:
                sealed[mutation] = {"changed": True}
            with self.subTest(mutation=mutation), self.assertRaises(MetaNativeBoundaryError):
                validate_native_request(sealed, "meta")

    def test_changing_native_payload_after_sealing_is_rejected(self):
        sealed = seal_native_request(canonical(), native())
        sealed["_polaris_meta_responses"]["input"] = "different hidden prompt"
        with self.assertRaises(MetaNativeBoundaryError):
            validate_native_request(sealed, "meta")

    def test_internal_runtime_metadata_does_not_change_policy_mirror(self):
        sealed = seal_native_request(canonical(), native())
        sealed["_request_id"] = "request-1"
        self.assertEqual(validate_native_request(sealed, "meta"), native())

    def test_existing_reserved_markers_cannot_be_resealed(self):
        with self.assertRaises(MetaNativeBoundaryError):
            seal_native_request({**canonical(), "_polaris_meta_responses": native()}, native())

    def test_partial_removed_markers_are_rejected(self):
        for field in ("_polaris_meta_responses", "_polaris_meta_seal", "_polaris_meta_fingerprint"):
            sealed = seal_native_request(canonical(), native())
            del sealed[field]
            with self.subTest(field=field), self.assertRaises(MetaNativeBoundaryError):
                validate_native_request(sealed, "meta")
