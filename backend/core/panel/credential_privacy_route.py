"""Final JSON projection for console routes carrying credential inventory references."""

import json

from core.credential_privacy import project_credential_references
from core.credential_references import credential_reference_key
from fastapi import HTTPException, Request
from fastapi.routing import APIRoute


async def _project(content):
    # No storage lookup for the overwhelmingly common non-email IDs.
    try:
        return project_credential_references(content, b"")
    except ValueError:
        return project_credential_references(content, await credential_reference_key())


class CredentialPrivacyRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def private_response(request: Request):
            try:
                response = await handler(request)
            except HTTPException as exc:
                safe = await _project({"detail": exc.detail})
                raise HTTPException(
                    status_code=exc.status_code, detail=safe["detail"], headers=exc.headers
                ) from None
            # These are explicit export-permission operations. Payloads and ZIP
            # exports must retain original values for a faithful restore.
            if (
                self.endpoint.__name__
                in {
                    "get_cred_detail",
                    "reveal_credential_email",
                    "download_cred_file",
                }
                or "content-disposition" in response.headers
            ):
                return response
            if not response.headers.get("content-type", "").startswith("application/json"):
                return response
            if not hasattr(response, "body"):
                return response
            content = json.loads(response.body)
            # OAuth's explicit credential retrieval is an existing sensitive
            # workflow. Preserve its importable payload, not its summary labels.
            oauth_payload = None
            has_oauth_payload = (
                self.endpoint.__name__ in {"auth_callback", "auth_callback_url"}
                and "credentials" in content
            )
            if has_oauth_payload:
                oauth_payload = content.pop("credentials")
            projected = await _project(content)
            if has_oauth_payload:
                projected["credentials"] = oauth_payload
            response.body = json.dumps(
                projected, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ).encode("utf-8")
            response.headers["content-length"] = str(len(response.body))
            response.headers["cache-control"] = "no-store"
            return response

        return private_response
