"""Shared utilities: subprocess helpers, cluster name generation, output specs."""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("noderunner")


# ---------------------------------------------------------------------------
# subprocess helpers (ported from hailrunner)
# ---------------------------------------------------------------------------

def run_cmd(cmd: list[str], label: str, timeout: Optional[int] = None) -> str:
    """Run a short-lived subprocess. Captures output. Raises on failure."""
    flat = " ".join(cmd)
    log.info("[%s] %s", label, flat)
    t0 = time.time()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        log.error("[%s] TIMEOUT after %.0fs: %s", label, time.time() - t0, flat)
        raise
    elapsed = time.time() - t0
    if result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            log.info("[%s] stdout: %s", label, line)
    if result.stderr.strip():
        level = logging.WARNING if result.returncode != 0 else logging.DEBUG
        for line in result.stderr.strip().splitlines():
            log.log(level, "[%s] stderr: %s", label, line)
    if result.returncode != 0:
        log.error("[%s] FAILED (exit %d, %.0fs)", label, result.returncode, elapsed)
        raise subprocess.CalledProcessError(
            result.returncode, cmd, output=result.stdout, stderr=result.stderr,
        )
    log.info("[%s] OK (%.0fs)", label, elapsed)
    return result.stdout


def run_streaming(cmd: list[str], label: str) -> None:
    """Run a long-lived subprocess with live output streaming to the logger."""
    flat = " ".join(cmd)
    log.info("[%s] %s", label, flat)
    t0 = time.time()
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    def _stream():
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                log.info("[%s] %s", label, line)

    thread = threading.Thread(target=_stream, daemon=True)
    thread.start()
    proc.wait()
    thread.join(timeout=10)
    elapsed = time.time() - t0

    if proc.returncode != 0:
        log.error("[%s] FAILED (exit %d, %.0fs)", label, proc.returncode, elapsed)
        raise subprocess.CalledProcessError(proc.returncode, cmd)
    log.info("[%s] OK (%.0fs)", label, elapsed)


# ---------------------------------------------------------------------------
# cluster name generation
# ---------------------------------------------------------------------------

def generate_cluster_name() -> str:
    """Generate a unique cluster name: noderunner-<8hex>-<timestamp>."""
    return f"noderunner-{uuid.uuid4().hex[:8]}-{int(time.time())}"


# ---------------------------------------------------------------------------
# project detection (ported from hailrunner)
# ---------------------------------------------------------------------------

def detect_project() -> Optional[str]:
    """Auto-detect GCP project from metadata server or gcloud config."""
    # GCE metadata server — works inside any GCE VM / Cromwell container
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/project/project-id",
            headers={"Metadata-Flavor": "Google"},
        )
        resp = urllib.request.urlopen(req, timeout=2)
        val = resp.read().decode().strip()
        if val:
            log.info("Detected project from GCE metadata: %s", val)
            return val
    except Exception:
        pass
    # gcloud config as last resort
    try:
        out = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True, text=True, timeout=10,
        )
        val = out.stdout.strip()
        if val and val != "(unset)":
            return val
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# output specs (ported from hailrunner)
# ---------------------------------------------------------------------------

@dataclass
class OutputSpec:
    """Parsed output copy specification: gs://source -> local destination."""
    src: str
    dst: str


def parse_output_spec(raw: str) -> OutputSpec:
    """Parse 'gs://bucket/path/file.ext:./local_name' into an OutputSpec."""
    if not raw.startswith("gs://"):
        raise ValueError(f"Output src must start with gs://, got: {raw}")
    rest = raw[5:]
    idx = rest.rfind(":")
    if idx == -1:
        raise ValueError(f"Output spec must be 'gs://src:dst', got: {raw}")
    return OutputSpec(src="gs://" + rest[:idx], dst=rest[idx + 1:])


def copy_outputs(specs: list[OutputSpec]) -> None:
    """Copy output files from GCS to local paths."""
    for spec in specs:
        log.info("Copying output: %s -> %s", spec.src, spec.dst)
        dst_dir = os.path.dirname(spec.dst)
        if dst_dir:
            os.makedirs(dst_dir, exist_ok=True)
        run_cmd(["gsutil", "-m", "cp", spec.src, spec.dst], "copy-output")
