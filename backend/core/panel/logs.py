import asyncio
import datetime
import os
from urllib.parse import urlsplit

from core.i18n import LocalizedJSONResponse as JSONResponse
from core.identity import (
    AuthorizationDenied,
    ManagementPrincipal,
    ManagementRouteTransport,
    UnclassifiedManagementRoute,
    require_management_route,
)
from core.utils import PANEL_SESSION_COOKIE, verify_panel_token, verify_panel_token_value
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from log import log, redact_text
from paths import DEFAULT_LOG_FILE
from starlette.websockets import WebSocketState

from .utils import ConnectionManager, internal_server_error

router = APIRouter(prefix="/api/logs", tags=["logs"])

MAX_LOG_DOWNLOAD_BYTES = 16 * 1024 * 1024


manager = ConnectionManager()


def _websocket_origin_matches_host(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin", "").strip()
    host = websocket.headers.get("host", "").strip().lower()
    if not origin or not host:
        return False
    parsed_origin = urlsplit(origin)
    return parsed_origin.scheme in {"http", "https"} and parsed_origin.netloc.lower() == host


def _log_file_size(path: str) -> int | None:
    try:
        return os.path.getsize(path)
    except FileNotFoundError:
        return None


def _clear_log_file(path: str) -> bool:
    if not os.path.exists(path):
        return False
    with open(path, "w", encoding="utf-8"):
        pass
    return True


def _read_recent_log_lines(path: str, limit: int) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as file:
            return file.readlines()[-limit:]
    except FileNotFoundError:
        return []


def _read_log_chunk(path: str, offset: int, size: int) -> tuple[str, int]:
    try:
        with open(path, "rb") as file:
            file.seek(offset)
            content = file.read(size)
    except FileNotFoundError:
        return "", 0
    return content.decode("utf-8", errors="replace"), len(content)


def _read_bounded_log_export(path: str, *, max_bytes: int) -> tuple[bytes, bool]:
    """Return the newest complete redacted log lines within a fixed byte ceiling."""
    if max_bytes < 1:
        raise ValueError("Log export limit must be positive.")
    file_size = os.path.getsize(path)
    offset = max(0, file_size - max_bytes)
    with open(path, "rb") as file:
        if offset:
            file.seek(offset - 1)
            previous = file.read(1)
            file.seek(offset)
            if previous not in (b"\r", b"\n"):
                file.readline()
            elif previous == b"\r" and file.read(1) == b"\n":
                file.seek(offset)
                file.readline()
            else:
                file.seek(offset)
        raw = file.read(max_bytes)

    lines = raw.splitlines(keepends=True)
    selected: list[bytes] = []
    byte_count = 0
    for line in reversed(lines):
        redacted = redact_text(line.decode("utf-8", errors="replace")).encode("utf-8")
        if byte_count + len(redacted) > max_bytes:
            break
        selected.append(redacted)
        byte_count += len(redacted)
    selected.reverse()
    return b"".join(selected), offset > 0 or len(selected) < len(lines)


@router.post("/clear")
async def clear_logs(token: str = Depends(verify_panel_token)):
    try:
        log_file_path = os.getenv("LOG_FILE", str(DEFAULT_LOG_FILE))

        if await asyncio.to_thread(_clear_log_file, log_file_path):
            try:
                log.info(f"Log file cleared: {log_file_path}")

                await manager.broadcast("--- Log file cleared. ---")

                return JSONResponse(
                    content={"message": f"Log file cleared: {os.path.basename(log_file_path)}."}
                )
            except Exception as e:
                log.error(f"Failed to clear log file: {e}")
                raise internal_server_error() from e
        else:
            return JSONResponse(content={"message": "Log file does not exist."})

    except Exception as e:
        log.error(f"Failed to clear log file: {e}")
        raise internal_server_error() from e


@router.get("/download")
async def download_logs(token: str = Depends(verify_panel_token)):
    try:
        log_file_path = os.getenv("LOG_FILE", str(DEFAULT_LOG_FILE))

        file_size = await asyncio.to_thread(_log_file_size, log_file_path)
        if file_size is None:
            raise HTTPException(status_code=404, detail="Log file does not exist.")

        if file_size == 0:
            raise HTTPException(status_code=404, detail="Log file is empty.")

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"logs_{timestamp}.txt"

        log.info(f"Downloading bounded log file: {os.path.basename(log_file_path)}")
        export, truncated = await asyncio.to_thread(
            _read_bounded_log_export,
            log_file_path,
            max_bytes=MAX_LOG_DOWNLOAD_BYTES,
        )

        return StreamingResponse(
            iter((export,)),
            media_type="text/plain",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Log-Byte-Count": str(len(export)),
                "X-Log-Max-Bytes": str(MAX_LOG_DOWNLOAD_BYTES),
                "X-Log-Truncated": str(truncated).lower(),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to download log file: {e}")
        raise internal_server_error() from e


@router.websocket("/stream")
async def websocket_logs(websocket: WebSocket):
    if not _websocket_origin_matches_host(websocket):
        await websocket.close(code=4403, reason="Origin not allowed")
        log.warning("WebSocket connection denied: origin not allowed.")
        return

    token = websocket.cookies.get(PANEL_SESSION_COOKIE)

    if not token:
        await websocket.close(code=4401, reason="Authentication required")
        log.warning("WebSocket connection denied: authentication required.")
        return

    try:
        verified_token = await verify_panel_token_value(token)
        principal = getattr(verified_token, "principal", None)
        if type(principal) is not ManagementPrincipal:
            raise HTTPException(status_code=503, detail="Session service is unavailable.")
    except HTTPException as e:
        close_code = 4401 if e.status_code in {401, 428} else 4403
        await websocket.close(code=close_code, reason=str(e.detail))
        log.warning("WebSocket connection denied: token verification failed.")
        return
    except Exception as e:
        await websocket.close(code=1011, reason="Authentication error")
        log.error(f"WebSocket authentication failed ({type(e).__name__}).")
        return

    try:
        require_management_route(
            principal,
            transport=ManagementRouteTransport.WEBSOCKET,
            method="WEBSOCKET",
            path="/api/logs/stream",
        )
    except AuthorizationDenied:
        await websocket.close(code=4403, reason="Management permission denied")
        log.warning("WebSocket connection denied: management permission denied.")
        return
    except UnclassifiedManagementRoute:
        await websocket.close(code=4403, reason="Management permission denied")
        log.error("Protected management WebSocket is not classified.")
        return
    websocket.state.management_principal = principal

    if not await manager.connect(websocket):
        return

    try:
        log_file_path = os.getenv("LOG_FILE", str(DEFAULT_LOG_FILE))

        try:
            lines = await asyncio.to_thread(_read_recent_log_lines, log_file_path, 50)
            for line in lines:
                if line.strip():
                    await websocket.send_text(redact_text(line.strip()))
        except Exception as e:
            await websocket.send_text("Error reading log file.")
            log.error(f"WebSocket initial log read failed ({type(e).__name__}).")

        last_size = await asyncio.to_thread(_log_file_size, log_file_path) or 0
        max_read_size = 8192
        check_interval = 2

        async def listen_for_disconnect():
            try:
                while True:
                    await websocket.receive_text()
            except Exception:
                pass

        listener_task = asyncio.create_task(listen_for_disconnect())

        try:
            while websocket.client_state == WebSocketState.CONNECTED:
                done, pending = await asyncio.wait(
                    [listener_task], timeout=check_interval, return_when=asyncio.FIRST_COMPLETED
                )

                if listener_task in done:
                    break

                current_size = await asyncio.to_thread(_log_file_size, log_file_path)
                if current_size is not None:
                    if current_size > last_size:
                        read_size = min(current_size - last_size, max_read_size)

                        try:
                            new_content, bytes_read = await asyncio.to_thread(
                                _read_log_chunk,
                                log_file_path,
                                last_size,
                                read_size,
                            )

                            if not new_content:
                                last_size = current_size
                                continue

                            lines = new_content.splitlines(keepends=True)
                            if lines and not lines[-1].endswith(("\n", "\r")) and len(lines) > 1:
                                complete_lines = lines[:-1]
                                trailing_bytes = len(lines[-1].encode("utf-8"))
                            else:
                                complete_lines = lines
                                trailing_bytes = 0

                            for line in complete_lines:
                                if line.strip():
                                    await websocket.send_text(redact_text(line.rstrip()))
                            last_size += max(0, bytes_read - trailing_bytes)
                        except Exception as e:
                            await websocket.send_text("Error reading new log content.")
                            log.error(
                                f"WebSocket incremental log read failed ({type(e).__name__})."
                            )

                            last_size = current_size

                    elif current_size < last_size:
                        last_size = 0
                        await websocket.send_text("--- Log file cleared. ---")

        finally:
            if not listener_task.done():
                listener_task.cancel()
                try:
                    await listener_task
                except asyncio.CancelledError:
                    pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error(f"WebSocket logs failed ({type(e).__name__}).")
    finally:
        manager.disconnect(websocket)
