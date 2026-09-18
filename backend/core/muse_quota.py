"""Persist fresh Muse response observations without replacing credential state."""

import hmac
import time
from collections.abc import Awaitable, Callable

from core.credential_pool_mutation import CredentialPoolMutation, CredentialPoolWrite
from core.muse_oauth import subscription_usage
from core.storage_adapter import get_storage_adapter


def subscription_observer(
    filename: str, credential: dict, *, mode: str = "primary"
) -> Callable[[dict], Awaitable[None]] | None:
    """Bind observations to the account/session that actually made the request."""
    if credential.get("provider") != "muse_code" or mode != "primary":
        return None
    account_id = credential.get("account_id")
    access_token = credential.get("access_token")
    if not all(isinstance(value, str) and value for value in (account_id, access_token)):
        return None

    async def observe(observation: dict) -> None:
        usage = subscription_usage(observation)
        observed_at = observation.get("observed_at") if isinstance(observation, dict) else None
        if usage is None or type(observed_at) is not int or not 0 <= observed_at <= time.time():
            return
        usage["observed_at"] = observed_at

        def patch_current(records):
            unchanged = CredentialPoolMutation((), (), {"updated": False})
            for record in records:
                if record.filename != filename:
                    continue
                current = record.credential_data
                current_token = current.get("access_token")
                if (
                    current.get("provider") != "muse_code"
                    or current.get("account_id") != account_id
                    or not isinstance(current_token, str)
                    or not hmac.compare_digest(current_token.encode(), access_token.encode())
                ):
                    return unchanged
                previous = current.get("subscription_usage")
                previous_at = previous.get("observed_at") if isinstance(previous, dict) else None
                if type(previous_at) is int and observed_at < previous_at:
                    return unchanged
                return CredentialPoolMutation(
                    (
                        CredentialPoolWrite(
                            filename, {**current, "subscription_usage": usage}, record.user_email
                        ),
                    ),
                    (),
                    {"updated": True},
                )
            return unchanged

        storage = await get_storage_adapter()
        await storage.mutate_credential_pool(mode, patch_current)

    return observe
