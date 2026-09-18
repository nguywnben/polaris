"""Additional authority for destructive operations on multiplexed credential routes."""

from core.identity import AuthorizationDenied, ManagementPermission, require_permission
from core.utils import verify_panel_token
from fastapi import Depends, HTTPException, Request


async def verify_credential_action_token(
    request: Request, token: str = Depends(verify_panel_token)
) -> str:
    # The route's OPERATE permission is insufficient for deletion. Check before
    # target resolution, preview/idempotency lookup, or any storage access.
    body = await request.json()
    if isinstance(body, dict) and body.get("action") == "delete":
        try:
            require_permission(
                getattr(request.state, "management_principal", None),
                ManagementPermission.CREDENTIALS_MANAGE,
            )
        except AuthorizationDenied as exc:
            raise HTTPException(status_code=403, detail="Management permission denied.") from exc
    return token
