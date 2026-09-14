import dataclasses
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity.oidc_policy import (  # noqa: E402
    OIDC_POLICY_SCHEMA_VERSION,
    OidcConfigurationError,
    load_oidc_configuration,
)
from core.identity.repository import OidcPolicyRevisionRecord  # noqa: E402
from tests.support import workspace_temp_directory  # noqa: E402


def _revision() -> OidcPolicyRevisionRecord:
    return OidcPolicyRevisionRecord.initial(now=datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc))


def _enabled_environment() -> dict[str, str]:
    return {
        "OIDC_ENABLED": "true",
        "OIDC_ISSUER": "https://identity.example.com/tenant",
        "OIDC_CLIENT_ID": "polaris",
        "OIDC_CLIENT_SECRET": "enterprise-client-secret",
        "OIDC_REDIRECT_URI": "https://gateway.example.com/api/identity/oidc/callback",
    }


class OidcPolicyTests(unittest.TestCase):
    def test_policy_is_versioned_and_disabled_without_configuration(self):
        configuration = load_oidc_configuration(_revision(), environ={})

        self.assertEqual(configuration.policy.schema_version, OIDC_POLICY_SCHEMA_VERSION)
        self.assertEqual(configuration.policy.revision, 1)
        self.assertEqual(configuration.policy.authorization_epoch, 1)
        self.assertFalse(configuration.policy.enabled)
        self.assertFalse(configuration.secret_configured)
        self.assertIsNone(configuration.policy.issuer)

    def test_enabled_policy_has_bounded_secure_defaults(self):
        configuration = load_oidc_configuration(_revision(), environ=_enabled_environment())

        self.assertTrue(configuration.policy.enabled)
        self.assertEqual(configuration.policy.scopes, ("openid", "profile", "email"))
        self.assertEqual(configuration.policy.id_token_signing_algorithms, ("RS256",))
        self.assertEqual(configuration.policy.claims.subject, "sub")
        self.assertEqual(configuration.policy.claims.groups, "groups")
        self.assertEqual(configuration.policy.role_mappings, ())
        self.assertEqual(configuration.policy.clock_skew_seconds, 60)
        self.assertEqual(configuration.policy.max_id_token_age_seconds, 300)
        self.assertEqual(
            configuration.policy.allowed_endpoint_origins,
            ("https://identity.example.com",),
        )
        self.assertTrue(configuration.secret_configured)

    def test_role_mappings_are_explicit_bounded_and_never_assign_owner(self):
        configuration = load_oidc_configuration(
            _revision(),
            environ=_enabled_environment()
            | {
                "OIDC_ROLE_MAPPINGS": (
                    '{"gateway-viewers":"viewer",'
                    '"gateway-operators":"operator",'
                    '"gateway-security":"security_admin"}'
                )
            },
        )

        self.assertEqual(
            configuration.policy.role_mappings,
            (
                ("gateway-operators", "operator"),
                ("gateway-security", "security_admin"),
                ("gateway-viewers", "viewer"),
            ),
        )

        invalid_mappings = (
            '{"gateway-owner":"owner"}',
            '{"gateway-viewers":"viewer","gateway-viewers":"operator"}',
            '{"":"viewer"}',
            '{" bad":"viewer"}',
            '{"gateway":"administrator"}',
            "[]",
            "{broken",
            "{" + ",".join(f'"group-{index}":"viewer"' for index in range(65)) + "}",
        )
        for mappings in invalid_mappings:
            with self.subTest(mappings=mappings[:80]):
                with self.assertRaisesRegex(OidcConfigurationError, "role mapping"):
                    load_oidc_configuration(
                        _revision(),
                        environ=_enabled_environment() | {"OIDC_ROLE_MAPPINGS": mappings},
                    )

    def test_callback_path_is_fixed_to_the_registered_gateway_route(self):
        for redirect_uri in (
            "https://gateway.example.com/auth/oidc/callback",
            "https://gateway.example.com/api/identity/oidc/callback/",
            "https://gateway.example.com/api/identity/other",
        ):
            with self.subTest(redirect_uri=redirect_uri):
                with self.assertRaisesRegex(OidcConfigurationError, "callback"):
                    load_oidc_configuration(
                        _revision(),
                        environ=_enabled_environment() | {"OIDC_REDIRECT_URI": redirect_uri},
                    )

    def test_secret_is_never_in_repr_str_or_serialized_policy(self):
        secret = "secret-value-that-must-not-leak"
        environment = _enabled_environment() | {"OIDC_CLIENT_SECRET": secret}

        configuration = load_oidc_configuration(_revision(), environ=environment)

        self.assertNotIn(secret, repr(configuration))
        self.assertNotIn(secret, str(configuration))
        self.assertNotIn(secret, repr(dataclasses.asdict(configuration.policy)))
        self.assertEqual(configuration.reveal_client_secret(), secret)
        with self.assertRaises(AttributeError):
            configuration.policy = load_oidc_configuration(_revision(), environ={}).policy
        with self.assertRaises(AttributeError):
            configuration._client_secret = None

    def test_exactly_one_environment_locked_secret_source_is_required(self):
        environment = _enabled_environment()
        environment.pop("OIDC_CLIENT_SECRET")
        with self.assertRaisesRegex(OidcConfigurationError, "client secret"):
            load_oidc_configuration(_revision(), environ=environment)

        with workspace_temp_directory() as directory:
            secret_file = Path(directory) / "oidc-secret"
            secret_file.write_text("file-client-secret\n", encoding="utf-8")
            file_environment = environment | {"OIDC_CLIENT_SECRET_FILE": str(secret_file)}
            configuration = load_oidc_configuration(_revision(), environ=file_environment)
            self.assertEqual(configuration.reveal_client_secret(), "file-client-secret")

            with self.assertRaisesRegex(OidcConfigurationError, "exactly one"):
                load_oidc_configuration(
                    _revision(),
                    environ=file_environment | {"OIDC_CLIENT_SECRET": "duplicate-secret"},
                )

    def test_relative_symlink_oversized_and_malformed_secret_files_fail_closed(self):
        environment = _enabled_environment()
        environment.pop("OIDC_CLIENT_SECRET")
        with self.assertRaisesRegex(OidcConfigurationError, "absolute"):
            load_oidc_configuration(
                _revision(), environ=environment | {"OIDC_CLIENT_SECRET_FILE": "secret.txt"}
            )

        with workspace_temp_directory() as directory:
            root = Path(directory)
            oversized = root / "oversized"
            oversized.write_bytes(b"x" * 4097)
            with self.assertRaisesRegex(OidcConfigurationError, "invalid"):
                load_oidc_configuration(
                    _revision(),
                    environ=environment | {"OIDC_CLIENT_SECRET_FILE": str(oversized)},
                )

            malformed = root / "malformed"
            malformed.write_bytes(b"\xff\xfe")
            with self.assertRaisesRegex(OidcConfigurationError, "invalid"):
                load_oidc_configuration(
                    _revision(),
                    environ=environment | {"OIDC_CLIENT_SECRET_FILE": str(malformed)},
                )

            target = root / "target"
            target.write_text("linked-client-secret", encoding="utf-8")
            link = root / "link"
            try:
                link.symlink_to(target)
            except OSError:
                pass
            else:
                with self.assertRaisesRegex(OidcConfigurationError, "symbolic link"):
                    load_oidc_configuration(
                        _revision(),
                        environ=environment | {"OIDC_CLIENT_SECRET_FILE": str(link)},
                    )

    def test_invalid_boolean_and_incomplete_activation_fail_closed(self):
        with self.assertRaisesRegex(OidcConfigurationError, "OIDC_ENABLED"):
            load_oidc_configuration(_revision(), environ={"OIDC_ENABLED": "sometimes"})

        with self.assertRaisesRegex(OidcConfigurationError, "OIDC_ISSUER"):
            load_oidc_configuration(
                _revision(), environ={"OIDC_ENABLED": "true", "OIDC_CLIENT_ID": "client"}
            )

    def test_issuer_and_redirect_require_exact_safe_https_urls(self):
        root_issuer = load_oidc_configuration(
            _revision(),
            environ=_enabled_environment() | {"OIDC_ISSUER": "https://identity.example.com"},
        ).policy
        self.assertEqual(root_issuer.issuer, "https://identity.example.com")

        invalid_issuers = (
            "http://identity.example.com",
            "https://user@identity.example.com",
            "https://identity.example.com/tenant?query=yes",
            "https://identity.example.com/tenant#fragment",
            " https://identity.example.com/tenant",
            "https://identity.example.com/ténant",
        )
        for issuer in invalid_issuers:
            with self.subTest(issuer=issuer):
                with self.assertRaisesRegex(OidcConfigurationError, "OIDC_ISSUER"):
                    load_oidc_configuration(
                        _revision(), environ=_enabled_environment() | {"OIDC_ISSUER": issuer}
                    )

        invalid_redirects = (
            "http://gateway.example.com/api/identity/oidc/callback",
            "https://gateway.example.com",
            "https://gateway.example.com/api/identity/oidc/callback?next=/admin",
            "https://gateway.example.com/api/identity/oidc/callback#fragment",
            "https://gateway.example.com/auth/oidc/cállback",
        )
        for redirect in invalid_redirects:
            with self.subTest(redirect=redirect):
                with self.assertRaisesRegex(OidcConfigurationError, "OIDC_REDIRECT_URI"):
                    load_oidc_configuration(
                        _revision(),
                        environ=_enabled_environment() | {"OIDC_REDIRECT_URI": redirect},
                    )

    def test_algorithms_are_explicit_unique_and_asymmetric_only(self):
        for algorithms in ("HS256", "none", "RS256,RS256", "RS512", ""):
            with self.subTest(algorithms=algorithms):
                with self.assertRaisesRegex(OidcConfigurationError, "algorithm"):
                    load_oidc_configuration(
                        _revision(),
                        environ=_enabled_environment()
                        | {"OIDC_ID_TOKEN_SIGNING_ALGORITHMS": algorithms},
                    )

        policy = load_oidc_configuration(
            _revision(),
            environ=_enabled_environment()
            | {"OIDC_ID_TOKEN_SIGNING_ALGORITHMS": "RS256,PS256,ES256"},
        ).policy
        self.assertEqual(policy.id_token_signing_algorithms, ("RS256", "PS256", "ES256"))

    def test_scopes_require_openid_and_claim_names_are_bounded(self):
        for scopes in ("profile email", "openid openid", 'openid bad"scope'):
            with self.subTest(scopes=scopes):
                with self.assertRaisesRegex(OidcConfigurationError, "scope"):
                    load_oidc_configuration(
                        _revision(), environ=_enabled_environment() | {"OIDC_SCOPES": scopes}
                    )

        for claim in ("", "bad claim", "x" * 65, "1starts_with_number"):
            with self.subTest(claim=claim):
                with self.assertRaisesRegex(OidcConfigurationError, "claim"):
                    load_oidc_configuration(
                        _revision(),
                        environ=_enabled_environment() | {"OIDC_GROUPS_CLAIM": claim},
                    )

        for claims in (
            {"OIDC_GROUPS_CLAIM": "sub"},
            {"OIDC_GROUPS_CLAIM": "iss"},
            {
                "OIDC_USERNAME_CLAIM": "profile",
                "OIDC_DISPLAY_NAME_CLAIM": "profile",
            },
        ):
            with self.subTest(claims=claims):
                with self.assertRaisesRegex(OidcConfigurationError, "claim"):
                    load_oidc_configuration(_revision(), environ=_enabled_environment() | claims)

    def test_endpoint_origins_and_private_hosts_reject_wildcards_and_urls(self):
        environment = _enabled_environment() | {
            "OIDC_ALLOWED_ENDPOINT_ORIGINS": (
                "https://keys.example.net:8443,https://identity.example.com"
            ),
            "OIDC_ALLOWED_PRIVATE_HOSTS": "idp.internal.example,10.20.30.40",
        }
        policy = load_oidc_configuration(_revision(), environ=environment).policy
        self.assertEqual(
            policy.allowed_endpoint_origins,
            ("https://identity.example.com", "https://keys.example.net:8443"),
        )
        self.assertEqual(policy.allowed_private_hosts, ("10.20.30.40", "idp.internal.example"))

        for origins in (
            "https://*.example.com",
            "http://keys.example.com",
            "https://keys.example.com/path",
        ):
            with self.subTest(origins=origins):
                with self.assertRaisesRegex(OidcConfigurationError, "endpoint origin"):
                    load_oidc_configuration(
                        _revision(),
                        environ=_enabled_environment() | {"OIDC_ALLOWED_ENDPOINT_ORIGINS": origins},
                    )

        for hosts in ("*.internal.example", "https://idp.internal.example", "localhost:8443"):
            with self.subTest(hosts=hosts):
                with self.assertRaisesRegex(OidcConfigurationError, "private host"):
                    load_oidc_configuration(
                        _revision(),
                        environ=_enabled_environment() | {"OIDC_ALLOWED_PRIVATE_HOSTS": hosts},
                    )

    def test_numeric_network_limits_are_bounded(self):
        invalid_values = {
            "OIDC_CONNECT_TIMEOUT_SECONDS": "0",
            "OIDC_READ_TIMEOUT_SECONDS": "61",
            "OIDC_MAX_RESPONSE_BYTES": "100",
            "OIDC_JWKS_TTL_SECONDS": "3601",
            "OIDC_CLOCK_SKEW_SECONDS": "301",
            "OIDC_MAX_ID_TOKEN_AGE_SECONDS": "3601",
        }
        for name, value in invalid_values.items():
            with self.subTest(name=name):
                with self.assertRaisesRegex(OidcConfigurationError, name):
                    load_oidc_configuration(
                        _revision(), environ=_enabled_environment() | {name: value}
                    )

        policy = load_oidc_configuration(
            _revision(),
            environ=_enabled_environment()
            | {
                "OIDC_CLOCK_SKEW_SECONDS": "0",
                "OIDC_MAX_ID_TOKEN_AGE_SECONDS": "60",
            },
        ).policy
        self.assertEqual(policy.clock_skew_seconds, 0)
        self.assertEqual(policy.max_id_token_age_seconds, 60)

    def test_revision_record_type_is_mandatory(self):
        with self.assertRaisesRegex(OidcConfigurationError, "revision"):
            load_oidc_configuration(object(), environ={})

    def test_policy_cannot_be_forged_by_direct_dataclass_construction(self):
        disabled = load_oidc_configuration(_revision(), environ={}).policy
        enabled = load_oidc_configuration(_revision(), environ=_enabled_environment()).policy

        invalid_changes = (
            (disabled, {"schema_version": True}),
            (disabled, {"issuer": "https://identity.example.com"}),
            (enabled, {"connect_timeout_seconds": 0}),
            (enabled, {"clock_skew_seconds": True}),
            (enabled, {"max_id_token_age_seconds": 59}),
            (enabled, {"allowed_endpoint_origins": ("http://identity.example.com",)}),
            (enabled, {"id_token_signing_algorithms": ("HS256",)}),
        )
        for policy, changes in invalid_changes:
            with self.subTest(changes=changes):
                with self.assertRaises(OidcConfigurationError):
                    dataclasses.replace(policy, **changes)


if __name__ == "__main__":
    unittest.main()
