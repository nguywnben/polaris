"""Composition and availability tests for the lazy browser OIDC runtime."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity import (  # noqa: E402
    OidcAuthorizationRequest,
    OidcLoginDisabled,
    OidcLoginError,
    OidcLoginService,
    load_oidc_configuration,
)
from core.state_store import InMemoryStateStore  # noqa: E402
from core.storage.identity_sqlite import SQLiteIdentityRepository  # noqa: E402
from tests.support import workspace_temp_directory  # noqa: E402


class OidcLoginServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = workspace_temp_directory()
        temp_path = self.temp_dir.__enter__()
        self.addCleanup(self.temp_dir.__exit__, None, None, None)
        self.repository = SQLiteIdentityRepository(Path(temp_path) / "identity.db")
        await self.repository.initialize()
        revision = await self.repository.get_oidc_policy_revision()
        self.enabled_configuration = load_oidc_configuration(
            revision,
            environ={
                "OIDC_ENABLED": "true",
                "OIDC_ISSUER": "https://identity.example.com/tenant",
                "OIDC_CLIENT_ID": "polaris",
                "OIDC_CLIENT_SECRET": "enterprise-client-secret",
                "OIDC_REDIRECT_URI": ("https://gateway.example.com/api/identity/oidc/callback"),
                "OIDC_ROLE_MAPPINGS": '{"operators":"operator"}',
            },
        )

    async def test_disabled_service_never_attempts_provider_discovery(self):
        revision = await self.repository.get_oidc_policy_revision()
        disabled = load_oidc_configuration(revision, environ={})
        service = OidcLoginService(
            disabled,
            self.repository,
            SimpleNamespace(),
            hmac_key=None,
        )

        with (
            patch("core.identity.oidc_login.discover_oidc", new=AsyncMock()) as discovery,
            self.assertRaises(OidcLoginDisabled),
        ):
            await service.begin()

        discovery.assert_not_awaited()

    async def test_components_are_lazy_reused_and_provider_tokens_never_leave_the_flow(self):
        authorization = OidcAuthorizationRequest(
            authorization_url="https://identity.example.com/authorize?state=opaque",
            browser_token="B" * 43,
            expires_in_seconds=300,
        )
        transactions = SimpleNamespace(begin=AsyncMock(return_value=authorization))
        verified = object()
        resolved = object()
        flow = SimpleNamespace(complete=AsyncMock(return_value=verified))
        resolver = SimpleNamespace(resolve=AsyncMock(return_value=resolved))
        issued = SimpleNamespace(token="ogs_" + "S" * 43)
        session_service = SimpleNamespace(issue_oidc=AsyncMock(return_value=issued))
        coordination = InMemoryStateStore()
        service = OidcLoginService(
            self.enabled_configuration,
            self.repository,
            session_service,
            hmac_key=b"h" * 32,
            transaction_coordination=coordination,
            transaction_fencing_epoch=7,
        )

        with (
            patch("core.identity.oidc_login.OidcHttpClient", return_value=MagicMock()),
            patch(
                "core.identity.oidc_login.discover_oidc",
                new=AsyncMock(return_value=object()),
            ) as discovery,
            patch(
                "core.identity.oidc_login.OidcAuthorizationTransactionService",
                return_value=transactions,
            ) as transaction_factory,
            patch("core.identity.oidc_login.OidcJwksCache", return_value=MagicMock()),
            patch("core.identity.oidc_login.OidcIdTokenVerifier", return_value=MagicMock()),
            patch("core.identity.oidc_login.OidcAuthorizationCodeFlow", return_value=flow),
            patch("core.identity.oidc_login.OidcIdentityResolver", return_value=resolver),
        ):
            self.assertNotIn("enterprise-client-secret", repr(service))
            self.assertEqual(await service.begin(), authorization)
            self.assertEqual(await service.begin(), authorization)
            result = await service.complete(
                b"code=provider-code&state=opaque",
                browser_token="B" * 43,
                now=1_000.0,
            )

        self.assertIs(result, issued)
        discovery.assert_awaited_once()
        self.assertIs(
            transaction_factory.call_args.kwargs["coordination"],
            coordination,
        )
        self.assertEqual(transaction_factory.call_args.kwargs["fencing_epoch"], 7)
        flow.complete.assert_awaited_once_with(
            b"code=provider-code&state=opaque", browser_token="B" * 43
        )
        resolver.resolve.assert_awaited_once_with(verified)
        session_service.issue_oidc.assert_awaited_once_with(resolved, now=1_000.0)

    async def test_policy_revision_change_blocks_new_transactions_before_network(self):
        service = OidcLoginService(
            self.enabled_configuration,
            self.repository,
            SimpleNamespace(),
            hmac_key=b"h" * 32,
        )
        await self.repository.advance_oidc_policy_revision(expected_revision=1)

        with (
            patch("core.identity.oidc_login.discover_oidc", new=AsyncMock()) as discovery,
            self.assertRaises(OidcLoginError),
        ):
            await service.begin()

        discovery.assert_not_awaited()

    async def test_discovery_failure_is_shared_and_waiters_are_bounded(self):
        discovery_started = asyncio.Event()
        release_discovery = asyncio.Event()

        async def failed_discovery(_policy, _client):
            discovery_started.set()
            await release_discovery.wait()
            raise RuntimeError("provider unavailable")

        service = OidcLoginService(
            self.enabled_configuration,
            self.repository,
            SimpleNamespace(),
            hmac_key=b"h" * 32,
            max_component_waiters=2,
            discovery_failure_backoff_seconds=30.0,
        )

        with (
            patch("core.identity.oidc_login.OidcHttpClient", return_value=MagicMock()),
            patch(
                "core.identity.oidc_login.discover_oidc",
                new=AsyncMock(side_effect=failed_discovery),
            ) as discovery,
        ):
            requests = [asyncio.create_task(service.begin()) for _ in range(6)]
            await discovery_started.wait()
            await asyncio.sleep(0)
            release_discovery.set()
            results = await asyncio.gather(*requests, return_exceptions=True)

            with self.assertRaises(OidcLoginError):
                await service.begin()

        self.assertTrue(all(type(result) is OidcLoginError for result in results))
        discovery.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
