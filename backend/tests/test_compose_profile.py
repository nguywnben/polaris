"""Contracts for the canonical production Docker Compose profile."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = ROOT / "deploy" / "docker-compose.yml"
ADVANCED_PATH = ROOT / "deploy" / "compose.advanced.yml"

CORE_ENVIRONMENT = {
    "API_KEY",
    "PANEL_PASSWORD",
    "SETUP_TOKEN",
    "HOST",
    "PORT",
    "WORKERS",
    "OMNI_RUNTIME_MODE",
    "OMNI_REPLICA_COUNT",
    "LOG_LEVEL",
}

ADVANCED_ENVIRONMENT = {
    "CORS_ORIGINS",
    "CORS_ORIGIN_REGEX",
    "PANEL_COOKIE_SECURE",
    "TRUST_PROXY_HEADERS",
    "PROXY",
    "MONGODB_URI",
    "MONGODB_DATABASE",
    "POSTGRESQL_URI",
    "OIDC_ENABLED",
    "PROMETHEUS_EXPORT_ENABLED",
    "METRICS_TOKEN",
    "OTEL_EXPORT_ENABLED",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class CanonicalComposeTests(unittest.TestCase):
    def test_default_profile_exposes_only_common_production_controls(self):
        service = _load(COMPOSE_PATH)["services"]["app"]
        environment = service["environment"]

        self.assertIsInstance(environment, dict)
        self.assertEqual(set(environment), CORE_ENVIRONMENT)
        self.assertEqual(environment["HOST"], "0.0.0.0")
        self.assertEqual(str(environment["PORT"]), "4283")
        self.assertEqual(str(environment["WORKERS"]), "1")
        self.assertEqual(environment["OMNI_RUNTIME_MODE"], "standalone")
        self.assertEqual(str(environment["OMNI_REPLICA_COUNT"]), "1")
        for optional in ADVANCED_ENVIRONMENT:
            self.assertNotIn(optional, environment)

    def test_default_profile_uses_one_cross_platform_durable_volume(self):
        compose = _load(COMPOSE_PATH)
        service = compose["services"]["app"]
        mounts = service["volumes"]

        self.assertEqual(
            mounts,
            [{"type": "volume", "source": "data", "target": "/app/backend/data"}],
        )
        self.assertEqual(compose["volumes"]["data"]["name"], "${DATA_VOLUME:-polaris-data}")
        self.assertNotIn("container_name", service)

    def test_default_profile_preserves_container_safety_and_lifecycle_controls(self):
        service = _load(COMPOSE_PATH)["services"]["app"]

        self.assertTrue(service["read_only"])
        self.assertTrue(service["init"])
        self.assertIn("no-new-privileges:true", service["security_opt"])
        self.assertEqual(service["restart"], "unless-stopped")
        self.assertEqual(service["stop_grace_period"], "45s")
        self.assertEqual(service["pull_policy"], "missing")
        self.assertEqual(service["ports"], ["${HOST_PORT:-4283}:4283"])
        self.assertIn("/ready", " ".join(service["healthcheck"]["test"]))

    def test_advanced_options_are_an_explicit_override_not_default_services(self):
        advanced = _load(ADVANCED_PATH)
        self.assertEqual(set(advanced["services"]), {"app"})
        environment = advanced["services"]["app"]["environment"]

        self.assertIsInstance(environment, dict)
        self.assertTrue(ADVANCED_ENVIRONMENT <= set(environment))
        self.assertFalse(CORE_ENVIRONMENT & set(environment))
        self.assertNotIn("REDIS_URL", environment)
        self.assertNotIn("OMNI_EXPERIMENTAL_COORDINATION", environment)

    def test_image_build_does_not_copy_or_define_runtime_secrets(self):
        dockerfile = (ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

        self.assertNotRegex(dockerfile, r"(?im)^\s*(?:ARG|ENV)\s+.*(?:PASSWORD|SECRET|API_KEY)")
        self.assertNotRegex(dockerfile, r"(?im)^\s*COPY\s+.*\s\.env(?:\s|$)")
        self.assertRegex(dockerignore, r"(?m)^\.env$")

    def test_required_ci_smoke_uses_compose_and_proves_recreate_persistence(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        job = workflow.split("  container-smoke:", 1)[1].split("  publish-container:", 1)[0]

        self.assertIn("docker compose -f deploy/docker-compose.yml up", job)
        self.assertIn("--force-recreate", job)
        self.assertGreaterEqual(job.count("backend/tests/runtime_smoke.py"), 2)
        self.assertIn("docker compose -f deploy/docker-compose.yml down --volumes", job)
        self.assertNotRegex(job, re.compile(r"\bdocker run\b"))


if __name__ == "__main__":
    unittest.main()
