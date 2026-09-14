"""Closed, immutable contract for atomic credential-pool mutations."""

from __future__ import annotations

import os
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, TypeAlias


class CredentialPoolMutationError(RuntimeError):
    """The durable backend could not safely apply a pool mutation."""


def normalize_pool_mode(mode: object) -> str:
    if mode in {"primary", "provider"}:
        return "primary"
    if mode == "code_assist":
        return "code_assist"
    raise CredentialPoolMutationError("Credential pool mode is invalid.")


def normalize_pool_filename(filename: object) -> str:
    if type(filename) is not str:
        raise CredentialPoolMutationError("Credential filename is invalid.")
    stripped = filename.strip()
    normalized = os.path.basename(stripped)
    if (
        not normalized
        or normalized != stripped
        or "/" in stripped
        or "\\" in stripped
        or len(normalized) > 255
        or any(ord(character) < 32 for character in normalized)
    ):
        raise CredentialPoolMutationError("Credential filename is invalid.")
    return normalized


@dataclass(frozen=True, slots=True)
class CredentialPoolRecord:
    filename: str
    credential_data: dict[str, Any]
    user_email: str | None
    rotation_order: int

    def __post_init__(self) -> None:
        normalize_pool_filename(self.filename)
        if type(self.credential_data) is not dict:
            raise CredentialPoolMutationError("Credential payload is invalid.")
        if self.user_email is not None and (
            type(self.user_email) is not str or len(self.user_email) > 320
        ):
            raise CredentialPoolMutationError("Credential email is invalid.")
        if type(self.rotation_order) is not int or self.rotation_order < 0:
            raise CredentialPoolMutationError("Credential rotation order is invalid.")


@dataclass(frozen=True, slots=True)
class CredentialPoolWrite:
    filename: str
    credential_data: dict[str, Any]
    user_email: str | None

    def __post_init__(self) -> None:
        normalize_pool_filename(self.filename)
        if type(self.credential_data) is not dict:
            raise CredentialPoolMutationError("Credential payload is invalid.")
        if self.user_email is not None and (
            type(self.user_email) is not str or len(self.user_email) > 320
        ):
            raise CredentialPoolMutationError("Credential email is invalid.")


@dataclass(frozen=True, slots=True)
class CredentialPoolMutation:
    writes: tuple[CredentialPoolWrite, ...]
    deletes: tuple[str, ...]
    result: dict[str, Any]

    def __post_init__(self) -> None:
        if type(self.writes) is not tuple or type(self.deletes) is not tuple:
            raise CredentialPoolMutationError("Credential pool mutation is invalid.")
        if type(self.result) is not dict:
            raise CredentialPoolMutationError("Credential pool result is invalid.")


CredentialPoolPlanner: TypeAlias = Callable[
    [tuple[CredentialPoolRecord, ...]], CredentialPoolMutation
]


def validate_credential_pool_mutation(mutation: object) -> CredentialPoolMutation:
    if type(mutation) is not CredentialPoolMutation:
        raise CredentialPoolMutationError("Credential pool mutation is invalid.")
    write_names = tuple(normalize_pool_filename(item.filename) for item in mutation.writes)
    delete_names = tuple(normalize_pool_filename(item) for item in mutation.deletes)
    if (
        len(set(write_names)) != len(write_names)
        or len(set(delete_names)) != len(delete_names)
        or set(write_names).intersection(delete_names)
    ):
        raise CredentialPoolMutationError("Credential pool mutation targets are invalid.")
    # Copy mutable caller data before it crosses the durable boundary.
    return CredentialPoolMutation(
        writes=tuple(
            CredentialPoolWrite(item.filename, deepcopy(item.credential_data), item.user_email)
            for item in mutation.writes
        ),
        deletes=delete_names,
        result=deepcopy(mutation.result),
    )
