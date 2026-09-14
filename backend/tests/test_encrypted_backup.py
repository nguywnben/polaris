"""Authenticated-encryption contracts for portable backups."""

from __future__ import annotations

import base64
import json
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.encrypted_backup import (
    BackupDecryptionError,
    BackupEnvelopeError,
    decrypt_bytes,
    decrypt_payload,
    encrypt_bytes,
    encrypt_payload,
)


class EncryptedBackupTests(unittest.TestCase):
    def test_encrypt_decrypt_roundtrip(self) -> None:
        sample_data = {
            "credentials": [{"filename": "acc1.json", "provider": "openai_codex"}],
            "virtual_models": {"gpt-test": ["acc1.json"]},
            "settings": {"routing_policy": "smart"},
        }
        password = "strong-master-password-123!"

        bundle = encrypt_payload(sample_data, password)
        self.assertEqual(bundle["format"], "polaris-encrypted-backup")
        self.assertEqual(bundle["version"], 1)
        self.assertEqual(bundle["kdf"], "scrypt")
        self.assertEqual(bundle["cipher"], "aes-256-gcm")
        self.assertIn("salt", bundle)
        self.assertIn("nonce", bundle)
        self.assertIn("ciphertext", bundle)
        self.assertNotIn(password, json.dumps(bundle))

        restored = decrypt_payload(bundle, password)
        self.assertEqual(restored, sample_data)

    def test_decrypt_with_wrong_password_fails(self) -> None:
        sample_data = {"secret": "api-key-123"}
        bundle = encrypt_payload(sample_data, "correct-password")

        with self.assertRaisesRegex(BackupDecryptionError, "passphrase or archive"):
            decrypt_payload(bundle, "wrong-password")

    def test_binary_roundtrip_authenticates_metadata(self) -> None:
        plaintext = b"SQLite format 3\\x00" + bytes(range(256))
        encrypted = encrypt_bytes(plaintext, "correct horse battery staple")

        self.assertEqual(decrypt_bytes(encrypted, "correct horse battery staple"), plaintext)

        envelope = json.loads(encrypted)
        envelope["cipher"] = "aes-128-gcm"
        with self.assertRaises(BackupEnvelopeError):
            decrypt_bytes(
                json.dumps(envelope, separators=(",", ":")).encode(),
                "correct horse battery staple",
            )

    def test_ciphertext_tampering_fails_closed(self) -> None:
        envelope = json.loads(encrypt_bytes(b"secret", "correct horse battery staple"))
        ciphertext = bytearray(base64.b64decode(envelope["ciphertext"]))
        ciphertext[-1] ^= 1
        envelope["ciphertext"] = base64.b64encode(ciphertext).decode("ascii")

        with self.assertRaisesRegex(BackupDecryptionError, "passphrase or archive"):
            decrypt_bytes(
                json.dumps(envelope, separators=(",", ":")).encode(),
                "correct horse battery staple",
            )

    def test_rejects_unknown_missing_and_noncanonical_envelope_fields(self) -> None:
        encrypted = encrypt_bytes(b"secret", "correct horse battery staple")
        envelope = json.loads(encrypted)

        malformed = dict(envelope, unexpected=True)
        with self.assertRaises(BackupEnvelopeError):
            decrypt_bytes(json.dumps(malformed).encode(), "correct horse battery staple")

        del envelope["nonce"]
        with self.assertRaises(BackupEnvelopeError):
            decrypt_bytes(json.dumps(envelope).encode(), "correct horse battery staple")

    def test_rejects_unbounded_or_invalid_inputs(self) -> None:
        with self.assertRaises(BackupEnvelopeError):
            encrypt_bytes(b"secret", "short")
        with self.assertRaises(BackupEnvelopeError):
            encrypt_bytes("not-bytes", "correct horse battery staple")  # type: ignore[arg-type]
        with self.assertRaises(BackupEnvelopeError):
            decrypt_bytes(b"not-json", "correct horse battery staple")


if __name__ == "__main__":
    unittest.main()
