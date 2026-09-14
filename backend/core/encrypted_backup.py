"""Strict authenticated-encryption envelope for Polaris backups.

The envelope intentionally has one algorithm suite. Unsupported versions and
parameters fail before key derivation, which prevents downgrade and resource-
exhaustion attacks. Callers own the archive payload and never need to persist
the passphrase.
"""

from __future__ import annotations

import base64
import binascii
import json
import secrets
import unicodedata
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

BACKUP_ENVELOPE_FORMAT = "polaris-encrypted-backup"
BACKUP_ENVELOPE_VERSION = 1
BACKUP_KDF = "scrypt"
BACKUP_CIPHER = "aes-256-gcm"
BACKUP_KDF_N = 2**15
BACKUP_KDF_R = 8
BACKUP_KDF_P = 1
BACKUP_SALT_BYTES = 16
BACKUP_NONCE_BYTES = 12
BACKUP_KEY_BYTES = 32
MIN_BACKUP_PASSPHRASE_LENGTH = 12
MAX_BACKUP_PASSPHRASE_LENGTH = 256
MAX_BACKUP_PLAINTEXT_BYTES = 128 * 1024 * 1024
MAX_BACKUP_ENVELOPE_BYTES = 180 * 1024 * 1024

_ENVELOPE_FIELDS = frozenset(
    {
        "format",
        "version",
        "kdf",
        "kdf_n",
        "kdf_r",
        "kdf_p",
        "salt",
        "cipher",
        "nonce",
        "ciphertext",
    }
)


class BackupEnvelopeError(ValueError):
    """Raised when an encrypted envelope is malformed or unsupported."""


class BackupDecryptionError(BackupEnvelopeError):
    """Raised when authentication fails without disclosing which input was wrong."""


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _normalize_passphrase(passphrase: object) -> bytes:
    if type(passphrase) is not str:
        raise BackupEnvelopeError("Backup passphrase is invalid.")
    normalized = unicodedata.normalize("NFKC", passphrase)
    if not MIN_BACKUP_PASSPHRASE_LENGTH <= len(normalized) <= MAX_BACKUP_PASSPHRASE_LENGTH:
        raise BackupEnvelopeError("Backup passphrase must contain between 12 and 256 characters.")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise BackupEnvelopeError("Backup passphrase contains unsupported control characters.")
    return normalized.encode("utf-8", errors="strict")


def _derive_key(passphrase: bytes, salt: bytes) -> bytes:
    return Scrypt(
        salt=salt,
        length=BACKUP_KEY_BYTES,
        n=BACKUP_KDF_N,
        r=BACKUP_KDF_R,
        p=BACKUP_KDF_P,
    ).derive(passphrase)


def _encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode(value: object, *, field: str, expected_length: int | None = None) -> bytes:
    if type(value) is not str or not value:
        raise BackupEnvelopeError(f"Backup {field} is invalid.")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise BackupEnvelopeError(f"Backup {field} is invalid.") from exc
    if _encode(decoded) != value or (
        expected_length is not None and len(decoded) != expected_length
    ):
        raise BackupEnvelopeError(f"Backup {field} is invalid.")
    return decoded


def _reject_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise BackupEnvelopeError("Backup envelope contains duplicate fields.")
        value[key] = item
    return value


def _parse_envelope(encrypted: object) -> tuple[dict[str, Any], bytes, bytes, bytes]:
    if type(encrypted) is not bytes or not encrypted or len(encrypted) > MAX_BACKUP_ENVELOPE_BYTES:
        raise BackupEnvelopeError("Backup envelope size is invalid.")
    try:
        envelope = json.loads(
            encrypted.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_fields,
        )
    except BackupEnvelopeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupEnvelopeError("Backup envelope is not valid JSON.") from exc
    if not isinstance(envelope, dict) or set(envelope) != _ENVELOPE_FIELDS:
        raise BackupEnvelopeError("Backup envelope fields are invalid.")
    expected = {
        "format": BACKUP_ENVELOPE_FORMAT,
        "version": BACKUP_ENVELOPE_VERSION,
        "kdf": BACKUP_KDF,
        "kdf_n": BACKUP_KDF_N,
        "kdf_r": BACKUP_KDF_R,
        "kdf_p": BACKUP_KDF_P,
        "cipher": BACKUP_CIPHER,
    }
    if any(
        type(envelope[key]) is not type(value) or envelope[key] != value
        for key, value in expected.items()
    ):
        raise BackupEnvelopeError("Backup envelope version or algorithm is unsupported.")
    salt = _decode(envelope["salt"], field="salt", expected_length=BACKUP_SALT_BYTES)
    nonce = _decode(envelope["nonce"], field="nonce", expected_length=BACKUP_NONCE_BYTES)
    ciphertext = _decode(envelope["ciphertext"], field="ciphertext")
    if len(ciphertext) < 16 or len(ciphertext) > MAX_BACKUP_PLAINTEXT_BYTES + 16:
        raise BackupEnvelopeError("Backup ciphertext size is invalid.")
    header = {key: envelope[key] for key in envelope if key != "ciphertext"}
    return header, salt, nonce, ciphertext


def encrypt_bytes(plaintext: bytes, passphrase: str) -> bytes:
    """Encrypt a bounded binary payload into the canonical JSON envelope."""

    if type(plaintext) is not bytes or len(plaintext) > MAX_BACKUP_PLAINTEXT_BYTES:
        raise BackupEnvelopeError("Backup plaintext size is invalid.")
    password_bytes = _normalize_passphrase(passphrase)
    salt = secrets.token_bytes(BACKUP_SALT_BYTES)
    nonce = secrets.token_bytes(BACKUP_NONCE_BYTES)
    header: dict[str, Any] = {
        "format": BACKUP_ENVELOPE_FORMAT,
        "version": BACKUP_ENVELOPE_VERSION,
        "kdf": BACKUP_KDF,
        "kdf_n": BACKUP_KDF_N,
        "kdf_r": BACKUP_KDF_R,
        "kdf_p": BACKUP_KDF_P,
        "salt": _encode(salt),
        "cipher": BACKUP_CIPHER,
        "nonce": _encode(nonce),
    }
    key = _derive_key(password_bytes, salt)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, _canonical_json(header))
    return _canonical_json({**header, "ciphertext": _encode(ciphertext)})


def decrypt_bytes(encrypted: bytes, passphrase: str) -> bytes:
    """Authenticate and decrypt a canonical envelope, failing closed on any mismatch."""

    password_bytes = _normalize_passphrase(passphrase)
    header, salt, nonce, ciphertext = _parse_envelope(encrypted)
    key = _derive_key(password_bytes, salt)
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, _canonical_json(header))
    except InvalidTag as exc:
        raise BackupDecryptionError(
            "Unable to decrypt backup: the passphrase or archive is invalid."
        ) from exc


def encrypt_payload(data: dict[str, Any], password: str) -> dict[str, Any]:
    """Compatibility wrapper for callers encrypting a JSON object."""

    if not isinstance(data, dict):
        raise BackupEnvelopeError("Backup payload must be an object.")
    serialized = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return json.loads(encrypt_bytes(serialized, password))


def decrypt_payload(encrypted_bundle: dict[str, Any], password: str) -> dict[str, Any]:
    """Compatibility wrapper that returns one authenticated JSON object."""

    if not isinstance(encrypted_bundle, dict):
        raise BackupEnvelopeError("Backup envelope must be an object.")
    decrypted = decrypt_bytes(_canonical_json(encrypted_bundle), password)
    try:
        payload = json.loads(decrypted.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupEnvelopeError("Backup payload is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise BackupEnvelopeError("Backup payload must be an object.")
    return payload
