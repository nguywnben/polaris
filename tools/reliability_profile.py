"""Run a production reliability profile against an exact Git candidate.

The runner exports ``HEAD`` into a disposable directory, starts one standalone
Polaris process with SQLite, and uses one loopback deterministic Ollama
fixture. The routine profile is release-blocking; the ten-minute soak is optional.
Neither mode reads ``.env`` or contacts a real provider.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import ctypes
import hashlib
import json
import math
import os
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "tools" / "reliability-profile.json"
PROFILE_PATHS = {
    "routine": PROFILE_PATH,
    "soak": ROOT / "tools" / "reliability-soak-profile.json",
}
MODEL_ID = "polaris-p55-deterministic"
OWNER_PASSWORD = "Polaris-Reliability-Synthetic-Owner-2026"
MIB = 2**20


@dataclass(frozen=True, slots=True)
class ReliabilityThresholds:
    gateway_p95_ms: float
    error_rate_exclusive: float
    max_rss_mib: float
    max_memory_growth_mib: float
    max_memory_slope_mib_per_minute: float
    max_schedule_lag_ms: float
    dashboard_usable_ms: float
    graceful_shutdown_seconds: float
    restart_ready_seconds: float


@dataclass(frozen=True, slots=True)
class ReliabilityProfile:
    schema_version: str
    duration_seconds: int
    offered_rps: int
    concurrency: int
    request_timeout_seconds: int
    memory_sample_interval_seconds: int
    memory_warmup_seconds: int
    max_client_queue_depth: int
    dashboard_viewport: tuple[int, int]
    thresholds: ReliabilityThresholds
    digest: str

    @property
    def expected_requests(self) -> int:
        return self.duration_seconds * self.offered_rps


@dataclass(frozen=True, slots=True)
class MemorySample:
    elapsed_seconds: float
    rss_bytes: int


@dataclass(frozen=True, slots=True)
class MemoryTrend:
    sample_count: int
    stable_sample_count: int
    initial_rss_mib: float
    final_rss_mib: float
    peak_rss_mib: float
    first_window_median_mib: float
    last_window_median_mib: float
    growth_mib: float
    slope_mib_per_minute: float
    monotonic_increase_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class WorkloadMetrics:
    attempted: int
    succeeded: int
    failed: int
    elapsed_seconds: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_in_flight: int
    max_queue_depth: int
    deadline_failures: int
    response_validation_failures: int
    max_schedule_lag_ms: float = 0.0
    status_counts: dict[str, int] = field(default_factory=dict)
    failure_counts: dict[str, int] = field(default_factory=dict)

    @property
    def error_rate(self) -> float:
        return self.failed / self.attempted if self.attempted else 1.0

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["error_rate"] = round(self.error_rate, 8)
        value["achieved_rps"] = round(self.succeeded / max(self.elapsed_seconds, 0.001), 4)
        return value


@dataclass(frozen=True, slots=True)
class ProfileCheck:
    id: str
    passed: bool
    observed: Any
    requirement: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(mapping: Mapping[str, Any], name: str, *, minimum: float = 0) -> float:
    value = mapping.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Profile field {name!r} must be numeric.")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise ValueError(f"Profile field {name!r} is outside its supported boundary.")
    return number


def _integer(mapping: Mapping[str, Any], name: str, *, minimum: int = 1) -> int:
    value = mapping.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"Profile field {name!r} must be an integer >= {minimum}.")
    return value


def load_profile(path: Path = PROFILE_PATH) -> ReliabilityProfile:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Reliability profile must be a JSON object.")
    threshold_raw = raw.get("thresholds")
    viewport = raw.get("dashboard_viewport")
    if not isinstance(threshold_raw, dict):
        raise ValueError("Reliability thresholds must be a JSON object.")
    if (
        not isinstance(viewport, list)
        or len(viewport) != 2
        or any(isinstance(value, bool) or not isinstance(value, int) for value in viewport)
        or any(value < 320 for value in viewport)
    ):
        raise ValueError("Dashboard viewport must contain two bounded integer dimensions.")
    schema_version = raw.get("schema_version")
    if schema_version != "polaris.reliability-profile.v1":
        raise ValueError("Reliability profile schema version is unsupported.")
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return ReliabilityProfile(
        schema_version=schema_version,
        duration_seconds=_integer(raw, "duration_seconds"),
        offered_rps=_integer(raw, "offered_rps"),
        concurrency=_integer(raw, "concurrency"),
        request_timeout_seconds=_integer(raw, "request_timeout_seconds"),
        memory_sample_interval_seconds=_integer(raw, "memory_sample_interval_seconds"),
        memory_warmup_seconds=_integer(raw, "memory_warmup_seconds", minimum=0),
        max_client_queue_depth=_integer(raw, "max_client_queue_depth"),
        dashboard_viewport=(viewport[0], viewport[1]),
        thresholds=ReliabilityThresholds(
            gateway_p95_ms=_number(threshold_raw, "gateway_p95_ms"),
            error_rate_exclusive=_number(threshold_raw, "error_rate_exclusive"),
            max_rss_mib=_number(threshold_raw, "max_rss_mib"),
            max_memory_growth_mib=_number(threshold_raw, "max_memory_growth_mib"),
            max_memory_slope_mib_per_minute=_number(
                threshold_raw, "max_memory_slope_mib_per_minute"
            ),
            max_schedule_lag_ms=_number(threshold_raw, "max_schedule_lag_ms"),
            dashboard_usable_ms=_number(threshold_raw, "dashboard_usable_ms"),
            graceful_shutdown_seconds=_number(threshold_raw, "graceful_shutdown_seconds"),
            restart_ready_seconds=_number(threshold_raw, "restart_ready_seconds"),
        ),
        digest=hashlib.sha256(canonical).hexdigest(),
    )


def percentile(values: Sequence[float], quantile: float) -> float:
    if not values or not 0 < quantile <= 1:
        raise ValueError("Percentile requires samples and a quantile in (0, 1].")
    ordered = sorted(float(value) for value in values)
    return ordered[max(0, math.ceil(len(ordered) * quantile) - 1)]


def descendant_process_ids(root_pid: int, pairs: Sequence[tuple[int, int]]) -> set[int]:
    """Return the transitive process tree rooted at ``root_pid``."""

    descendants = {root_pid}
    while True:
        expanded = descendants | {pid for pid, parent in pairs if parent in descendants}
        if expanded == descendants:
            return descendants
        descendants = expanded


def graceful_exit_completed(return_code: int | None) -> bool:
    """Use the portable process result when informational logging is disabled."""

    return return_code == 0


def analyze_memory(samples: Sequence[MemorySample], *, warmup_seconds: int) -> MemoryTrend:
    if len(samples) < 2:
        raise ValueError("Memory analysis requires at least two samples.")
    ordered = sorted(samples, key=lambda sample: sample.elapsed_seconds)
    stable = [sample for sample in ordered if sample.elapsed_seconds >= warmup_seconds]
    if len(stable) < 4:
        raise ValueError("Memory analysis requires at least four post-warmup samples.")
    stable_mib = [sample.rss_bytes / MIB for sample in stable]
    window_size = max(2, len(stable_mib) // 4)
    first_median = statistics.median(stable_mib[:window_size])
    last_median = statistics.median(stable_mib[-window_size:])
    mean_x = statistics.fmean(sample.elapsed_seconds for sample in stable)
    mean_y = statistics.fmean(stable_mib)
    denominator = sum((sample.elapsed_seconds - mean_x) ** 2 for sample in stable)
    slope_per_second = (
        sum(
            (sample.elapsed_seconds - mean_x) * (rss - mean_y)
            for sample, rss in zip(stable, stable_mib, strict=True)
        )
        / denominator
        if denominator
        else 0.0
    )
    increases = sum(right > left for left, right in zip(stable_mib, stable_mib[1:]))
    return MemoryTrend(
        sample_count=len(ordered),
        stable_sample_count=len(stable),
        initial_rss_mib=round(ordered[0].rss_bytes / MIB, 3),
        final_rss_mib=round(ordered[-1].rss_bytes / MIB, 3),
        peak_rss_mib=round(max(sample.rss_bytes for sample in ordered) / MIB, 3),
        first_window_median_mib=round(first_median, 3),
        last_window_median_mib=round(last_median, 3),
        growth_mib=round(last_median - first_median, 3),
        slope_mib_per_minute=round(slope_per_second * 60, 4),
        monotonic_increase_ratio=round(increases / max(1, len(stable_mib) - 1), 4),
    )


def evaluate_profile(
    profile: ReliabilityProfile,
    *,
    workload: WorkloadMetrics,
    memory: MemoryTrend,
    dashboard_usable_ms: float,
    graceful_shutdown_seconds: float,
    restart_ready_seconds: float,
    post_restart_status: int,
    exhaustion: Mapping[str, int],
    graceful_shutdown_complete: bool = True,
) -> tuple[ProfileCheck, ...]:
    thresholds = profile.thresholds
    exhaustion_total = sum(max(0, int(value)) for value in exhaustion.values())
    return (
        ProfileCheck(
            "workload.request_count",
            workload.attempted == profile.expected_requests,
            workload.attempted,
            f"exactly {profile.expected_requests} attempts",
        ),
        ProfileCheck(
            "workload.duration",
            profile.duration_seconds <= workload.elapsed_seconds <= profile.duration_seconds + 30,
            round(workload.elapsed_seconds, 3),
            f"{profile.duration_seconds} to {profile.duration_seconds + 30} seconds",
        ),
        ProfileCheck(
            "workload.error_rate",
            workload.error_rate < thresholds.error_rate_exclusive,
            round(workload.error_rate, 8),
            f"< {thresholds.error_rate_exclusive}",
        ),
        ProfileCheck(
            "workload.gateway_p95",
            workload.p95_ms <= thresholds.gateway_p95_ms,
            round(workload.p95_ms, 3),
            f"<= {thresholds.gateway_p95_ms} ms",
        ),
        ProfileCheck(
            "workload.concurrency",
            workload.max_in_flight <= profile.concurrency,
            workload.max_in_flight,
            f"<= {profile.concurrency}",
        ),
        ProfileCheck(
            "workload.client_queue",
            workload.max_queue_depth <= profile.max_client_queue_depth,
            workload.max_queue_depth,
            f"<= {profile.max_client_queue_depth}",
        ),
        ProfileCheck(
            "workload.schedule_lag",
            workload.max_schedule_lag_ms <= thresholds.max_schedule_lag_ms,
            round(workload.max_schedule_lag_ms, 3),
            f"<= {thresholds.max_schedule_lag_ms} ms",
        ),
        ProfileCheck(
            "gateway.exhaustion",
            exhaustion_total == 0,
            dict(sorted(exhaustion.items())),
            "zero quota/budget/rate-limit/cooldown/capacity events",
        ),
        ProfileCheck(
            "memory.peak",
            memory.peak_rss_mib <= thresholds.max_rss_mib,
            memory.peak_rss_mib,
            f"<= {thresholds.max_rss_mib} MiB",
        ),
        ProfileCheck(
            "memory.growth",
            memory.growth_mib <= thresholds.max_memory_growth_mib,
            memory.growth_mib,
            f"<= {thresholds.max_memory_growth_mib} MiB after warmup",
        ),
        ProfileCheck(
            "memory.slope",
            memory.slope_mib_per_minute <= thresholds.max_memory_slope_mib_per_minute,
            memory.slope_mib_per_minute,
            f"<= {thresholds.max_memory_slope_mib_per_minute} MiB/min after warmup",
        ),
        ProfileCheck(
            "dashboard.usable",
            dashboard_usable_ms <= thresholds.dashboard_usable_ms,
            round(dashboard_usable_ms, 3),
            f"<= {thresholds.dashboard_usable_ms} ms",
        ),
        ProfileCheck(
            "restart.graceful_shutdown",
            graceful_shutdown_complete
            and graceful_shutdown_seconds <= thresholds.graceful_shutdown_seconds,
            {
                "seconds": round(graceful_shutdown_seconds, 3),
                "lifecycle_complete": graceful_shutdown_complete,
            },
            f"complete lifecycle in <= {thresholds.graceful_shutdown_seconds} seconds",
        ),
        ProfileCheck(
            "restart.ready",
            restart_ready_seconds <= thresholds.restart_ready_seconds,
            round(restart_ready_seconds, 3),
            f"<= {thresholds.restart_ready_seconds} seconds",
        ),
        ProfileCheck(
            "restart.post_request",
            post_restart_status == 200,
            post_restart_status,
            "HTTP 200 with the persisted route and virtual key",
        ),
    )


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class _ProviderHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "PolarisP55Fixture/1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _respond(self, status: int, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if urlsplit(self.path).path in {"/health", "/api/tags"}:
            self._respond(200, {"models": [{"name": MODEL_ID}]})
            return
        self._respond(404, {"error": "fixture_route_not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if path != "/api/chat" or not 0 <= length <= MIB:
            self._respond(404, {"error": "fixture_route_not_found"})
            return
        try:
            request = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._respond(400, {"error": "invalid_fixture_request"})
            return
        if not isinstance(request, dict) or request.get("model") != MODEL_ID:
            self._respond(400, {"error": "invalid_fixture_model"})
            return
        digest = hashlib.sha256(
            json.dumps(request, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        with self.server.counter_lock:  # type: ignore[attr-defined]
            self.server.request_count += 1  # type: ignore[attr-defined]
        self._respond(
            200,
            {
                "model": MODEL_ID,
                "created_at": "2026-01-01T00:00:00Z",
                "message": {"role": "assistant", "content": f"p55-{digest}"},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 8,
                "eval_count": 4,
            },
        )


class _ProviderServer(ThreadingHTTPServer):
    daemon_threads = True
    request_count: int
    counter_lock: threading.Lock


@contextlib.contextmanager
def deterministic_provider() -> Iterator[tuple[str, _ProviderServer]]:
    server = _ProviderServer(("127.0.0.1", 0), _ProviderHandler)
    server.request_count = 0
    server.counter_lock = threading.Lock()
    thread = threading.Thread(target=server.serve_forever, name="p55-provider", daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}", server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _git_output(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout.strip()


@contextlib.contextmanager
def candidate_checkout(commit: str) -> Iterator[Path]:
    scratch = ROOT / "temp" / "reliability-profile"
    scratch.mkdir(parents=True, exist_ok=True)
    run_root = Path(tempfile.mkdtemp(prefix="candidate-", dir=scratch))
    archive = run_root / "candidate.tar"
    checkout = run_root / "source"
    checkout.mkdir()
    try:
        subprocess.run(
            ["git", "archive", "--format=tar", "-o", str(archive), commit],
            cwd=ROOT,
            check=True,
            capture_output=True,
            timeout=60,
        )
        with tarfile.open(archive, "r") as bundle:
            bundle.extractall(checkout, filter="data")
        yield checkout
    finally:
        shutil.rmtree(run_root, ignore_errors=True)


def _wait_ready(base_url: str, process: subprocess.Popen[str], timeout: float) -> float:
    started = time.perf_counter()
    deadline = started + timeout
    while time.perf_counter() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Candidate runtime exited early with code {process.returncode}.")
        try:
            response = httpx.get(f"{base_url}/ready", timeout=1, trust_env=False)
            if response.status_code == 200:
                return time.perf_counter() - started
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"Candidate runtime was not ready within {timeout} seconds.")


class CandidateRuntime:
    def __init__(self, source: Path, state: Path, port: int) -> None:
        self.source = source
        self.state = state
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.log_path = state / "server-output.log"
        self.process: subprocess.Popen[str] | None = None
        self._log_handle: Any = None

    def start(self, *, ready_timeout: float) -> float:
        if self.process is not None:
            raise RuntimeError("Candidate runtime is already started.")
        inherited_names = {
            "COMSPEC",
            "LANG",
            "LC_ALL",
            "LOCALAPPDATA",
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "WINDIR",
        }
        environment = {
            name: value for name, value in os.environ.items() if name.upper() in inherited_names
        }
        environment.update(
            PYTHON_DOTENV_DISABLED="1",
            CREDENTIALS_DIR=str(self.state / "credentials"),
            LOG_FILE=str(self.state / "runtime.log"),
            POSTGRESQL_URI="",
            MONGODB_URI="",
            HOST="127.0.0.1",
            PORT=str(self.port),
            WORKERS="1",
            PANEL_PASSWORD="",
            SETUP_TOKEN="",
            POLARIS_RUNTIME_MODE="standalone",
            ENABLE_LOG="0",
            ENABLE_METRICS="0",
            OTEL_EXPORTER_OTLP_ENDPOINT="",
            PYTHONUTF8="1",
        )
        self._log_handle = self.log_path.open("a", encoding="utf-8")
        kwargs: dict[str, Any] = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        self.process = subprocess.Popen(
            [sys.executable, "backend/main.py"],
            cwd=self.source,
            env=environment,
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            **kwargs,
        )
        return _wait_ready(self.base_url, self.process, ready_timeout)

    def stop(self, *, timeout: float) -> tuple[float, bool, int | None]:
        process = self.process
        if process is None:
            return 0.0, False, None
        started = time.perf_counter()
        if process.poll() is None:
            try:
                if os.name == "nt":
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.terminate()
                process.wait(timeout=timeout)
            except (OSError, subprocess.TimeoutExpired):
                self.kill()
        elapsed = time.perf_counter() - started
        return_code = process.poll()
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None
        complete = graceful_exit_completed(return_code)
        self.process = None
        return elapsed, complete, return_code

    def kill(self) -> None:
        process = self.process
        if process is None or process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                capture_output=True,
                timeout=10,
            )
        else:
            process.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=5)


def _bootstrap(base_url: str, provider_url: str) -> tuple[str, dict[str, str]]:
    with httpx.Client(base_url=base_url, timeout=15, trust_env=False) as client:
        setup_status = client.get("/api/auth/setup/status")
        setup_status.raise_for_status()
        if setup_status.json().get("setup_required") is not True:
            raise RuntimeError("Candidate checkout did not start with fresh setup state.")
        setup = client.post(
            "/api/auth/setup",
            json={"password": OWNER_PASSWORD, "confirm_password": OWNER_PASSWORD},
        )
        setup.raise_for_status()
        provider = client.post(
            "/api/providers/ollama/credentials",
            json={"base_url": provider_url, "api_key": ""},
        )
        provider.raise_for_status()
        catalog = client.get("/api/model-catalog", params={"refresh": "true"})
        catalog.raise_for_status()
        if MODEL_ID not in {entry.get("model_id") for entry in catalog.json().get("catalog", [])}:
            raise RuntimeError("Deterministic model was not discovered through the gateway.")
        route = client.post(
            "/api/model-routes/polaris",
            json={"selected_models": [MODEL_ID], "enabled": True},
        )
        route.raise_for_status()
        key_response = client.post(
            "/api/virtual-keys",
            json={
                "name": "Reliability profile",
                "allowed_models": ["polaris"],
                "scopes": ["inference:openai"],
            },
        )
        key_response.raise_for_status()
        key = str(key_response.json().get("key") or "")
        if not key.startswith("sk-polaris-"):
            raise RuntimeError("Virtual key bootstrap did not return the one-time secret.")
        cookies = {cookie.name: cookie.value for cookie in client.cookies.jar}
    return key, cookies


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


class _ProcessEntry32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_ulong),
        ("cntUsage", ctypes.c_ulong),
        ("th32ProcessID", ctypes.c_ulong),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", ctypes.c_ulong),
        ("cntThreads", ctypes.c_ulong),
        ("th32ParentProcessID", ctypes.c_ulong),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", ctypes.c_ulong),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


def _windows_process_pairs() -> tuple[tuple[int, int], ...]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_snapshot = kernel32.CreateToolhelp32Snapshot
    create_snapshot.argtypes = (ctypes.c_ulong, ctypes.c_ulong)
    create_snapshot.restype = ctypes.c_void_p
    first = kernel32.Process32FirstW
    first.argtypes = (ctypes.c_void_p, ctypes.POINTER(_ProcessEntry32W))
    first.restype = ctypes.c_int
    next_entry = kernel32.Process32NextW
    next_entry.argtypes = (ctypes.c_void_p, ctypes.POINTER(_ProcessEntry32W))
    next_entry.restype = ctypes.c_int
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (ctypes.c_void_p,)
    close_handle.restype = ctypes.c_int
    snapshot = create_snapshot(0x00000002, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise OSError("Unable to enumerate the candidate process tree.")
    pairs: list[tuple[int, int]] = []
    entry = _ProcessEntry32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        available = bool(first(snapshot, ctypes.byref(entry)))
        while available:
            pairs.append((int(entry.th32ProcessID), int(entry.th32ParentProcessID)))
            available = bool(next_entry(snapshot, ctypes.byref(entry)))
    finally:
        close_handle(snapshot)
    return tuple(pairs)


def _unix_process_pairs() -> tuple[tuple[int, int], ...]:
    proc = Path("/proc")
    if not proc.is_dir():
        return ()
    pairs: list[tuple[int, int]] = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text(encoding="ascii").rsplit(")", 1)[1].split()
            pairs.append((int(entry.name), int(fields[1])))
        except (IndexError, OSError, ValueError):
            continue
    return tuple(pairs)


def _single_process_rss_bytes(pid: int) -> int:
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
        open_process.restype = ctypes.c_void_p
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (ctypes.c_void_p,)
        close_handle.restype = ctypes.c_int
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        get_memory = psapi.GetProcessMemoryInfo
        get_memory.argtypes = (
            ctypes.c_void_p,
            ctypes.POINTER(_ProcessMemoryCounters),
            ctypes.c_ulong,
        )
        get_memory.restype = ctypes.c_int
        handle = open_process(0x0400 | 0x0010, False, pid)
        if not handle:
            raise OSError("Unable to inspect candidate process memory.")
        counters = _ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        try:
            if not get_memory(handle, ctypes.byref(counters), counters.cb):
                raise OSError("Unable to read candidate process memory.")
            return int(counters.WorkingSetSize)
        finally:
            close_handle(handle)
    status = Path(f"/proc/{pid}/status")
    if status.is_file():
        for line in status.read_text(encoding="ascii", errors="replace").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    completed = subprocess.run(
        ["ps", "-o", "rss=", "-p", str(pid)],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return int(completed.stdout.strip()) * 1024


def _process_tree_rss_bytes(root_pid: int) -> int:
    pairs = _windows_process_pairs() if os.name == "nt" else _unix_process_pairs()
    total = 0
    for pid in descendant_process_ids(root_pid, pairs):
        with contextlib.suppress(OSError, subprocess.SubprocessError, ValueError):
            total += _single_process_rss_bytes(pid)
    if total <= 0:
        raise OSError("Candidate process-tree memory is unavailable.")
    return total


async def _run_workload(
    profile: ReliabilityProfile, base_url: str, api_key: str, pid: int
) -> tuple[WorkloadMetrics, list[MemorySample]]:
    started = time.perf_counter()
    latencies: list[float] = []
    memory_samples: list[MemorySample] = []
    status_counts: dict[str, int] = {}
    failure_counts: dict[str, int] = {}
    pending: set[asyncio.Task[None]] = set()
    semaphore = asyncio.Semaphore(profile.concurrency)
    state = {"in_flight": 0, "max_in_flight": 0, "max_queue": 0, "max_lag": 0.0}

    async def sample_memory() -> None:
        while True:
            elapsed = time.perf_counter() - started
            rss_bytes = await asyncio.to_thread(_process_tree_rss_bytes, pid)
            memory_samples.append(MemorySample(elapsed, rss_bytes))
            if elapsed >= profile.duration_seconds:
                return
            await asyncio.sleep(
                min(profile.memory_sample_interval_seconds, profile.duration_seconds - elapsed)
            )

    limits = httpx.Limits(
        max_connections=profile.concurrency,
        max_keepalive_connections=profile.concurrency,
        keepalive_expiry=4,
    )
    timeout = httpx.Timeout(profile.request_timeout_seconds)
    headers = {"Authorization": f"Bearer {api_key}"}
    memory_task = asyncio.create_task(sample_memory())
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        limits=limits,
        trust_env=False,
        follow_redirects=False,
    ) as client:

        async def one(sequence: int) -> None:
            async with semaphore:
                state["in_flight"] += 1
                state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
                request_started = time.perf_counter()
                status_key = "transport"
                failure = ""
                try:
                    response = await client.post(
                        "/v1/chat/completions",
                        headers={**headers, "X-Request-ID": f"p55-{sequence:08d}"},
                        json={
                            "model": "polaris",
                            "messages": [
                                {
                                    "role": "user",
                                    "content": f"deterministic-profile-{sequence:08d}",
                                }
                            ],
                            "max_tokens": 4,
                            "temperature": 0,
                            "stream": False,
                        },
                    )
                    status_key = str(response.status_code)
                    if response.status_code != 200:
                        failure = f"http_{response.status_code}"
                    else:
                        try:
                            payload = response.json()
                            content = payload["choices"][0]["message"]["content"]
                            if not isinstance(content, str) or not content.startswith("p55-"):
                                failure = "response_contract"
                        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
                            failure = "response_contract"
                except httpx.TimeoutException:
                    failure = "deadline"
                except httpx.HTTPError:
                    failure = "transport"
                finally:
                    latencies.append((time.perf_counter() - request_started) * 1000)
                    status_counts[status_key] = status_counts.get(status_key, 0) + 1
                    if failure:
                        failure_counts[failure] = failure_counts.get(failure, 0) + 1
                    state["in_flight"] -= 1

        for sequence in range(profile.expected_requests):
            due = started + (sequence + 1) / profile.offered_rps
            delay = due - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            lag = max(0.0, (time.perf_counter() - due) * 1000)
            state["max_lag"] = max(state["max_lag"], lag)
            while len(pending) >= profile.concurrency + profile.max_client_queue_depth:
                done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                pending.difference_update(done)
            task = asyncio.create_task(one(sequence))
            pending.add(task)
            task.add_done_callback(pending.discard)
            state["max_queue"] = max(state["max_queue"], max(0, len(pending) - profile.concurrency))
        if pending:
            await asyncio.gather(*pending)
    await memory_task
    elapsed = time.perf_counter() - started
    failures = sum(failure_counts.values())
    successes = profile.expected_requests - failures
    return (
        WorkloadMetrics(
            attempted=profile.expected_requests,
            succeeded=successes,
            failed=failures,
            elapsed_seconds=elapsed,
            p50_ms=percentile(latencies, 0.50),
            p95_ms=percentile(latencies, 0.95),
            p99_ms=percentile(latencies, 0.99),
            max_in_flight=int(state["max_in_flight"]),
            max_queue_depth=int(state["max_queue"]),
            deadline_failures=failure_counts.get("deadline", 0),
            response_validation_failures=failure_counts.get("response_contract", 0),
            max_schedule_lag_ms=float(state["max_lag"]),
            status_counts=dict(sorted(status_counts.items())),
            failure_counts=dict(sorted(failure_counts.items())),
        ),
        memory_samples,
    )


def _operational_exhaustion(base_url: str) -> dict[str, int]:
    with httpx.Client(base_url=base_url, timeout=30, trust_env=False) as client:
        login = client.post("/api/auth/login", json={"password": OWNER_PASSWORD})
        login.raise_for_status()
        response = client.get("/api/observability/health", params={"window_seconds": 900})
        response.raise_for_status()
        raw = response.json().get("exhaustion") or {}
    return {
        name: max(0, int(raw.get(name) or 0))
        for name in ("quota", "budget", "rate_limit", "cooldown", "capacity")
    }


def _measure_dashboard(base_url: str, profile: ReliabilityProfile) -> float:
    try:
        from playwright.sync_api import expect, sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required; install requirements-browser.txt and Chromium."
        ) from exc
    page_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={
                "width": profile.dashboard_viewport[0],
                "height": profile.dashboard_viewport[1],
            }
        )
        page = context.new_page()
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")
        expect(page.locator("#loginPassword")).to_be_visible(timeout=10_000)
        page.locator("#loginPassword").fill(OWNER_PASSWORD)
        page.locator('#loginForm button[type="submit"]').click()
        expect(page.locator("#dashboardTab")).to_be_visible(timeout=10_000)
        expect(page.locator("#dashboardStats")).to_have_attribute(
            "aria-busy", "false", timeout=10_000
        )
        page.wait_for_load_state("networkidle", timeout=10_000)
        started = time.perf_counter()
        page.reload(wait_until="domcontentloaded")
        expect(page.locator("#dashboardStats")).to_have_attribute(
            "aria-busy", "false", timeout=10_000
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        browser.close()
    if page_errors:
        raise RuntimeError(f"Dashboard raised a browser error: {page_errors[0]}")
    return elapsed_ms


def _post_restart_request(base_url: str, api_key: str) -> int:
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "polaris",
                "messages": [{"role": "user", "content": "post-restart-check"}],
                "max_tokens": 4,
                "stream": False,
            },
        )
    return response.status_code


def run_profile(profile: ReliabilityProfile) -> dict[str, Any]:
    candidate = _git_output("rev-parse", "HEAD")
    started_at = datetime.now(timezone.utc)
    scratch = ROOT / "temp" / "reliability-profile"
    scratch.mkdir(parents=True, exist_ok=True)
    state = Path(tempfile.mkdtemp(prefix="state-", dir=scratch))
    runtime: CandidateRuntime | None = None
    try:
        with (
            candidate_checkout(candidate) as source,
            deterministic_provider() as (
                provider_url,
                provider,
            ),
        ):
            runtime = CandidateRuntime(source, state, _free_port())
            initial_ready_seconds = runtime.start(
                ready_timeout=profile.thresholds.restart_ready_seconds
            )
            if runtime.process is None:
                raise RuntimeError("Candidate runtime process is unavailable.")
            api_key, _cookies = _bootstrap(runtime.base_url, provider_url)
            print(
                f"[reliability] running {profile.expected_requests} requests for "
                f"{profile.duration_seconds} seconds at {profile.offered_rps} RPS / "
                f"{profile.concurrency} concurrency",
                flush=True,
            )
            workload, memory_samples = asyncio.run(
                _run_workload(
                    profile,
                    runtime.base_url,
                    api_key,
                    runtime.process.pid,
                )
            )
            memory = analyze_memory(memory_samples, warmup_seconds=profile.memory_warmup_seconds)
            exhaustion = _operational_exhaustion(runtime.base_url)
            dashboard_ms = _measure_dashboard(runtime.base_url, profile)
            shutdown_seconds, shutdown_complete, shutdown_exit_code = runtime.stop(
                timeout=profile.thresholds.graceful_shutdown_seconds
            )
            restart_ready_seconds = runtime.start(
                ready_timeout=profile.thresholds.restart_ready_seconds
            )
            post_restart_status = _post_restart_request(runtime.base_url, api_key)
            final_shutdown_seconds, final_shutdown_complete, _ = runtime.stop(
                timeout=profile.thresholds.graceful_shutdown_seconds
            )
            checks = evaluate_profile(
                profile,
                workload=workload,
                memory=memory,
                dashboard_usable_ms=dashboard_ms,
                graceful_shutdown_seconds=shutdown_seconds,
                restart_ready_seconds=restart_ready_seconds,
                post_restart_status=post_restart_status,
                exhaustion=exhaustion,
                graceful_shutdown_complete=shutdown_complete,
            )
            return {
                "schema_version": "polaris.reliability-result.v1",
                "candidate_commit": candidate,
                "source_checkout": "git-archive",
                "profile": {
                    "schema_version": profile.schema_version,
                    "sha256": profile.digest,
                    "duration_seconds": profile.duration_seconds,
                    "offered_rps": profile.offered_rps,
                    "concurrency": profile.concurrency,
                    "expected_requests": profile.expected_requests,
                },
                "environment": {
                    "runtime": "standalone",
                    "workers": 1,
                    "replicas": 1,
                    "storage": "sqlite",
                    "provider": "deterministic-loopback-ollama",
                    "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                    "platform": sys.platform,
                },
                "started_at": started_at.isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "initial_ready_seconds": round(initial_ready_seconds, 3),
                "workload": workload.to_dict(),
                "memory": memory.to_dict(),
                "dashboard": {"usable_ms": round(dashboard_ms, 3)},
                "gateway": {
                    "exhaustion": exhaustion,
                    "deterministic_provider_requests": provider.request_count,
                },
                "restart": {
                    "graceful_shutdown_seconds": round(shutdown_seconds, 3),
                    "graceful_shutdown_complete": shutdown_complete,
                    "shutdown_exit_code": shutdown_exit_code,
                    "ready_seconds": round(restart_ready_seconds, 3),
                    "post_restart_status": post_restart_status,
                    "final_shutdown_seconds": round(final_shutdown_seconds, 3),
                    "final_shutdown_complete": final_shutdown_complete,
                },
                "checks": [check.to_dict() for check in checks],
                "passed": all(check.passed for check in checks),
            }
    finally:
        if runtime is not None:
            runtime.kill()
            if runtime._log_handle is not None:
                runtime._log_handle.close()
        shutil.rmtree(state, ignore_errors=True)


def _write_result(path: Path, result: Mapping[str, Any]) -> None:
    resolved = path if path.is_absolute() else ROOT / path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=tuple(PROFILE_PATHS),
        default="routine",
        help="Run the release-blocking routine profile or the optional ten-minute soak.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--verify",
        action="store_true",
        help="Run the fixed profile and return only its production verdict.",
    )
    mode.add_argument(
        "--output",
        type=Path,
        help="Run the fixed profile and write the complete versioned JSON result.",
    )
    options = parser.parse_args(arguments)
    try:
        profile = load_profile(PROFILE_PATHS[options.profile])
        result = run_profile(profile)
        result["profile"]["name"] = options.profile
        if options.output is not None:
            _write_result(options.output, result)
        failed = [check["id"] for check in result["checks"] if not check["passed"]]
        if failed:
            print(
                f"Reliability {options.profile} profile failed: {', '.join(failed)}",
                file=sys.stderr,
            )
            return 1
        workload = result["workload"]
        print(
            f"Reliability {options.profile} profile passed: "
            f"{workload['succeeded']}/{workload['attempted']} requests, "
            f"p95={workload['p95_ms']:.3f} ms, "
            f"dashboard={result['dashboard']['usable_ms']:.3f} ms.",
            flush=True,
        )
        return 0
    except Exception as exc:
        print(
            f"Reliability {options.profile} profile could not complete: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
