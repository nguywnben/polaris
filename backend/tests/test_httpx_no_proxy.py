"""Explicit NO_PROXY routing contracts, with no external requests or DNS."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core import httpx_client as outbound

PROXY = "http://proxy.example.test:8080"


class NoProxyTests(unittest.IsolatedAsyncioTestCase):
    async def _proxy_for(self, url, environment):
        with (
            patch.object(os, "environ", environment),
            patch.object(outbound, "get_proxy_config", AsyncMock(return_value=PROXY)),
        ):
            options = await outbound.HttpxClientManager().get_client_kwargs(destination_url=url)
        self.assertFalse(options["trust_env"])
        self.assertNotIn("destination_url", options)
        return options.get("proxy")

    async def test_explicit_no_proxy_matches_host_domain_port_and_literal_networks(self):
        cases = (
            ("localhost", "http://localhost:11434/api/tags"),
            ("EXAMPLE.TEST", "https://api.example.test/models"),
            (".example.test", "https://example.test/models"),
            ("example.test:443", "https://example.test/models"),
            ("localhost:11434", "http://localhost:11434/api/tags"),
            ("127.0.0.1", "http://127.0.0.1:11434/api/tags"),
            ("127.0.0.0/8", "http://127.0.0.1:11434/api/tags"),
            ("[::1]:11434", "http://[::1]:11434/api/tags"),
            ("::1", "http://[::1]:11434/api/tags"),
            ("[::1]", "http://[::1]:11434/api/tags"),
            ("fd00::/8", "http://[fd12::42]:11434/api/tags"),
            ("*", "https://api.example.test/models"),
            ("other.test, localhost , example.test", "http://localhost:11434/api/tags"),
        )
        for rule, url in cases:
            with self.subTest(rule=rule, url=url):
                self.assertIsNone(await self._proxy_for(url, {"NO_PROXY": rule}))

    async def test_nonmatching_and_invalid_rules_keep_proxy_without_dns(self):
        cases = (
            ("example.test", "https://notexample.test/models"),
            ("example.test", "https://example.test.attacker.test/models"),
            ("localhost:1234", "http://localhost:11434/api/tags"),
            ("127.0.0.0/8", "http://localhost:11434/api/tags"),
            ("fd00::/8", "http://[::1]:11434/api/tags"),
            ("[::1]:1234", "http://[::1]:11434/api/tags"),
            ("http://localhost", "http://localhost:11434/api/tags"),
            ("localhost:invalid", "http://localhost:11434/api/tags"),
            ("*.example.test", "http://api.example.test/models"),
            ("bad/invalid, [invalid]", "http://localhost:11434/api/tags"),
            ("[localhost]", "http://localhost:11434/api/tags"),
            ("localhost:" + "9" * 5000, "http://localhost:11434/api/tags"),
            ("localhost:80", "http://localhost:0/api/tags"),
        )
        with patch("socket.getaddrinfo", side_effect=AssertionError("DNS is forbidden")):
            for rule, url in cases:
                with self.subTest(rule=rule, url=url):
                    self.assertEqual(await self._proxy_for(url, {"NO_PROXY": rule}), PROXY)

    async def test_no_automatic_local_bypass_and_lowercase_environment_precedence(self):
        url = "http://localhost:11434/api/tags"
        self.assertEqual(await self._proxy_for(url, {}), PROXY)
        self.assertIsNone(await self._proxy_for(url, {"no_proxy": "localhost"}))
        self.assertEqual(await self._proxy_for(url, {"NO_PROXY": "*", "no_proxy": ""}), PROXY)
        self.assertEqual(await self._proxy_for(None, {"NO_PROXY": "*"}), PROXY)

    async def test_get_post_and_stream_use_separate_reusable_direct_and_proxy_pools(self):
        manager = outbound.HttpxClientManager()
        real_client = httpx.AsyncClient
        created = []

        def create_client(**options):
            created.append(options.copy())
            options.pop("proxy", None)
            return real_client(
                **options,
                transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"ok\n")),
            )

        try:
            with (
                patch.object(os, "environ", {"NO_PROXY": "localhost"}),
                patch.object(outbound, "get_proxy_config", AsyncMock(return_value=PROXY)),
                patch.object(outbound, "http_client", manager),
                patch.object(outbound.httpx, "AsyncClient", side_effect=create_client),
            ):
                self.assertEqual(
                    (await outbound.get_async("http://localhost:11434/tags")).status_code, 200
                )
                await outbound.post_async("http://localhost:11434/api/chat", json={}, timeout=30.0)
                lines = [
                    line
                    async for line in outbound.stream_post_async(
                        "http://localhost:11434/api/chat", {}, timeout=30.0
                    )
                ]
                self.assertEqual(lines, ["ok"])
                await outbound.get_async("https://api.example.test/models")
                await outbound.get_async("https://other.example.test/models")
            self.assertEqual(len(created), 2)
            self.assertIsNone(created[0].get("proxy"))
            self.assertEqual(created[1]["proxy"], PROXY)
        finally:
            await manager.close()


if __name__ == "__main__":
    unittest.main()
