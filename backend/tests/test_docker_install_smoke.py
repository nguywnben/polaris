"""Cleanup must never infer ownership from a generic installer label."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tools import docker_install_smoke as smoke


class DockerInstallSmokeCleanupTests(unittest.TestCase):
    def test_existing_target_fails_before_entering_cleanup(self):
        target = "polaris-install-smoke-aaaaaaaaaaaa"
        with (
            patch("sys.argv", ["docker_install_smoke.py"]),
            patch.object(smoke.uuid, "uuid4", return_value=SimpleNamespace(hex="a" * 32)),
            patch.object(smoke, "docker", side_effect=[b"image-id", target.encode()]) as docker,
            patch.object(smoke, "cleanup_resources") as cleanup,
        ):
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                smoke.main()
        self.assertEqual(docker.call_count, 2)
        cleanup.assert_not_called()

    def test_unrecorded_resources_are_never_inspected_or_deleted(self):
        with patch.object(smoke, "docker") as docker:
            self.assertEqual(smoke.cleanup_resources({}), 0)
        docker.assert_not_called()

    def test_replaced_container_is_preserved_despite_generic_guided_label(self):
        old = {"Id": "original-id", "Config": {"Labels": {"io.polaris.install": "guided"}}}
        with patch.object(smoke, "docker", return_value=b'[{"Id":"preexisting-id"}]') as docker:
            with self.assertRaisesRegex(RuntimeError, "identity changed"):
                smoke.cleanup_resources({("container", "test-container"): old})
        self.assertEqual(docker.call_count, 1)

    def test_replaced_volume_is_preserved(self):
        old = {"CreatedAt": "then", "Labels": {"io.polaris.install-id": "original"}}
        with patch.object(
            smoke,
            "docker",
            return_value=b'[{"CreatedAt":"now","Labels":{"io.polaris.install":"guided"}}]',
        ) as docker:
            with self.assertRaisesRegex(RuntimeError, "identity changed"):
                smoke.cleanup_resources({("volume", "test-data"): old})
        self.assertEqual(docker.call_count, 1)

    def test_matching_container_is_removed_by_immutable_id(self):
        item = {"Id": "original-id"}
        with patch.object(smoke, "docker", return_value=b'[{"Id":"original-id"}]') as docker:
            self.assertEqual(smoke.cleanup_resources({("container", "test-container"): item}), 1)
        self.assertEqual(docker.call_args.args, ("container", "rm", "--force", "original-id"))

    def test_clone_requires_exact_run_label_before_being_recorded(self):
        owned = {}
        with patch.object(
            smoke, "docker", return_value=b'[{"Labels":{"io.polaris.smoke":"another-run"}}]'
        ):
            with self.assertRaisesRegex(RuntimeError, "ownership"):
                smoke.record_resource(owned, "volume", "test-data", "run-id")
        self.assertEqual(owned, {})


if __name__ == "__main__":
    unittest.main()
