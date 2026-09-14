"""Side-effect-free policy for the supported single-process runtime."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from core.coordination import MAX_COORDINATION_INTEGER

_RETIRED_COORDINATION_FIELDS = (
    "REDIS_URL",
    "POLARIS_COORDINATION_NAMESPACE",
    "POLARIS_DEPLOYMENT_ID",
    "POLARIS_COORDINATION_KEY",
    "POLARIS_COORDINATION_EPOCH",
    "POLARIS_EXPERIMENTAL_COORDINATION",
)


class RuntimeMode(StrEnum):
    STANDALONE = "standalone"


def _value(environment: Mapping[str, str], name: str, default: str = "") -> str:
    raw = environment.get(name, default)
    if not isinstance(raw, str):
        raise RuntimeError(f"{name} must be text.")
    return raw.strip()


def _positive_integer(environment: Mapping[str, str], name: str, default: str) -> int:
    raw = _value(environment, name, default)
    if not raw.isascii() or not raw.isdigit() or raw.startswith("0"):
        raise RuntimeError(f"{name} must be a positive integer.")
    value = int(raw)
    if not 1 <= value <= MAX_COORDINATION_INTEGER:
        raise RuntimeError(f"{name} is outside the supported range.")
    return value


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    mode: RuntimeMode
    workers: int
    replicas: int
    durable_backend: str

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> RuntimePolicy:
        selected = os.environ if environment is None else environment
        mode = _value(selected, "POLARIS_RUNTIME_MODE", RuntimeMode.STANDALONE.value)
        if mode != RuntimeMode.STANDALONE:
            raise RuntimeError("POLARIS_RUNTIME_MODE must be standalone.")

        workers = _positive_integer(selected, "WORKERS", "1")
        if workers != 1:
            raise RuntimeError("WORKERS must remain 1 for the supported standalone runtime.")
        replicas = _positive_integer(selected, "POLARIS_REPLICA_COUNT", "1")
        if replicas != 1:
            raise RuntimeError(
                "POLARIS_REPLICA_COUNT must remain 1 for the supported standalone runtime."
            )

        retired = [name for name in _RETIRED_COORDINATION_FIELDS if _value(selected, name)]
        if retired:
            raise RuntimeError(
                f"{retired[0]} belongs to the retired coordinated runtime and must be removed."
            )

        postgresql_uri = _value(selected, "POSTGRESQL_URI")
        mongodb_uri = _value(selected, "MONGODB_URI")
        if postgresql_uri and mongodb_uri:
            raise RuntimeError("Configure only one external durable backend.")
        durable_backend = "postgresql" if postgresql_uri else "mongodb" if mongodb_uri else "sqlite"
        return cls(RuntimeMode.STANDALONE, workers, replicas, durable_backend)

    def safe_summary(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "workers": self.workers,
            "replicas": self.replicas,
            "durable_backend": self.durable_backend,
        }
