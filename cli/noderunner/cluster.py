"""Dataproc cluster lifecycle: create, describe, delete."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from noderunner.mounts import MountSpec, build_metadata_string
from noderunner.utils import generate_cluster_name, run_cmd

log = logging.getLogger("noderunner")

# Init script path inside the orchestrator Docker image.
# Falls back to a path relative to this file for local development.
_DOCKER_INIT_PATH = "/opt/noderunner/init/gcsfuse.sh"
_LOCAL_INIT_PATH = Path(__file__).resolve().parent.parent.parent / "init" / "gcsfuse.sh"


def _find_init_script() -> str:
    """Locate the gcsfuse.sh init script."""
    if os.path.isfile(_DOCKER_INIT_PATH):
        return _DOCKER_INIT_PATH
    if _LOCAL_INIT_PATH.is_file():
        return str(_LOCAL_INIT_PATH)
    raise FileNotFoundError(
        f"gcsfuse.sh not found at {_DOCKER_INIT_PATH} or {_LOCAL_INIT_PATH}"
    )


@dataclass
class ClusterConfig:
    """Configuration for a noderunner Dataproc cluster."""

    project: str
    region: str
    staging_bucket: str
    machine_type: str = "n2-highmem-8"
    boot_disk_size_gb: int = 500
    boot_disk_type: str = "pd-ssd"
    local_ssds: int = 0
    subnet: Optional[str] = None
    no_external_ip: bool = True
    max_age_minutes: int = 120
    cluster_name: Optional[str] = None
    image_version: str = "2.2-debian12"
    custom_image: Optional[str] = None


class ClusterState(Enum):
    UNBORN = "unborn"
    CREATING = "creating"
    RUNNING = "running"
    EXECUTING = "executing"
    DESTROYING = "destroying"
    DESTROYED = "destroyed"
    FAILED = "failed"


class NoderunnerCluster:
    """Manages the lifecycle of an ephemeral single-node Dataproc cluster.

    Use as a context manager for guaranteed cleanup:

        with NoderunnerCluster(config, mounts) as cluster:
            zone = cluster.get_master_zone()
            # run docker on cluster...
    """

    def __init__(
        self,
        config: ClusterConfig,
        mounts: list[MountSpec],
        dry_run: bool = False,
    ):
        self.config = config
        self.mounts = mounts
        self.dry_run = dry_run
        self.name = config.cluster_name or generate_cluster_name()
        self.state = ClusterState.UNBORN
        self._start_time: Optional[float] = None
        self._init_gcs: Optional[str] = None

    def __enter__(self) -> NoderunnerCluster:
        self._start_time = time.time()
        self._stage_init_script()
        self.create()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.time() - (self._start_time or time.time())
        self.destroy()
        if exc_type:
            log.error(
                "Session failed after %.0fs: %s: %s",
                elapsed, exc_type.__name__, exc_val,
            )
        else:
            log.info("Session completed in %.0fs", elapsed)
        return False  # don't suppress exceptions

    def _elapsed(self) -> float:
        return time.time() - (self._start_time or time.time())

    def _log(self, msg: str, *args, level: int = logging.INFO) -> None:
        prefix = f"[{self.name}] [{self.state.value}] [{self._elapsed():.0f}s]"
        log.log(level, f"{prefix} {msg}", *args)

    # ------------------------------------------------------------------
    # staging
    # ------------------------------------------------------------------

    def _resolve_staging_bucket(self) -> str:
        """Return the staging bucket URI (gs://...)."""
        bucket = self.config.staging_bucket
        if not bucket.startswith("gs://"):
            bucket = f"gs://{bucket}"
        return bucket

    def _stage_init_script(self) -> None:
        """Upload gcsfuse.sh to the staging bucket if not already present."""
        if self.dry_run:
            self._init_gcs = "gs://DRY-RUN-BUCKET/noderunner/init/gcsfuse.sh"
            return

        bucket_uri = self._resolve_staging_bucket()
        gcs_path = f"{bucket_uri}/noderunner/init/gcsfuse.sh"

        # Check if already staged
        try:
            run_cmd(["gsutil", "stat", gcs_path], "check-init-script", timeout=30)
            self._log("Init script already staged: %s", gcs_path)
            self._init_gcs = gcs_path
            return
        except Exception:
            pass

        local_path = _find_init_script()
        self._log("Staging init script: %s -> %s", local_path, gcs_path)
        run_cmd(["gsutil", "cp", local_path, gcs_path], "stage-init-script")
        self._init_gcs = gcs_path

    # ------------------------------------------------------------------
    # create
    # ------------------------------------------------------------------

    def build_create_command(self) -> list[str]:
        """Build the gcloud dataproc clusters create command."""
        if not self._init_gcs:
            raise RuntimeError("Init script not staged — call _stage_init_script() first")

        cmd = [
            "gcloud", "dataproc", "clusters", "create", self.name,
            "--single-node",
            "--optional-components=DOCKER",
            f"--initialization-actions={self._init_gcs}",
            "--initialization-action-timeout=10m",
            f"--region={self.config.region}",
            f"--project={self.config.project}",
            f"--master-machine-type={self.config.machine_type}",
            f"--master-boot-disk-size={self.config.boot_disk_size_gb}",
            f"--master-boot-disk-type={self.config.boot_disk_type}",
            f"--max-age={self.config.max_age_minutes}m",
        ]

        if self.mounts:
            metadata = build_metadata_string(self.mounts)
            cmd.append(f"--metadata=gcsfuse_buckets={metadata}")

        if self.config.local_ssds > 0:
            cmd.append(f"--num-master-local-ssds={self.config.local_ssds}")
            cmd.append("--master-local-ssd-interface=NVME")

        if self.config.no_external_ip:
            cmd.append("--no-address")

        if self.config.custom_image:
            cmd.append(f"--image={self.config.custom_image}")
        else:
            cmd.append(f"--image-version={self.config.image_version}")

        if self.config.subnet:
            cmd.append(f"--subnet={self.config.subnet}")

        return cmd

    def create(self) -> None:
        """Create the Dataproc cluster."""
        if self.state != ClusterState.UNBORN:
            raise RuntimeError(f"Cannot create cluster in state {self.state.value}")

        self.state = ClusterState.CREATING
        self._log("Creating single-node Dataproc cluster...")
        self._log(
            "  machine=%s disk=%dGB/%s ssds=%d",
            self.config.machine_type,
            self.config.boot_disk_size_gb,
            self.config.boot_disk_type,
            self.config.local_ssds,
        )

        cmd = self.build_create_command()

        if self.dry_run:
            self._log("DRY RUN — would execute:\n  %s", " \\\n    ".join(cmd))
            self.state = ClusterState.RUNNING
            return

        try:
            run_cmd(cmd, "cluster-create")
        except Exception:
            self.state = ClusterState.FAILED
            self._log("Cluster creation FAILED", level=logging.ERROR)
            raise

        self.state = ClusterState.RUNNING
        self._log("Cluster is running.")

    # ------------------------------------------------------------------
    # describe
    # ------------------------------------------------------------------

    def get_master_zone(self) -> str:
        """Query the cluster and return the master node's zone."""
        if self.dry_run:
            return "us-central1-a"

        out = run_cmd(
            [
                "gcloud", "dataproc", "clusters", "describe", self.name,
                f"--region={self.config.region}",
                f"--project={self.config.project}",
                "--format=json",
            ],
            "cluster-describe",
            timeout=60,
        )
        info = json.loads(out)
        zone_uri = info["config"]["gceClusterConfig"]["zoneUri"]
        # zone_uri is like "projects/<proj>/zones/us-central1-a"
        zone = zone_uri.rsplit("/", 1)[-1]
        self._log("Master zone: %s", zone)
        return zone

    # ------------------------------------------------------------------
    # destroy
    # ------------------------------------------------------------------

    def destroy(self) -> None:
        """Delete the cluster (async). Safe to call multiple times."""
        if self.state in (ClusterState.DESTROYED, ClusterState.UNBORN):
            return

        prev = self.state
        self.state = ClusterState.DESTROYING
        self._log("Destroying cluster...")

        if self.dry_run:
            self._log("DRY RUN — would delete cluster %s", self.name)
            self.state = ClusterState.DESTROYED
            return

        try:
            run_cmd(
                [
                    "gcloud", "dataproc", "clusters", "delete", "--quiet", "--async",
                    f"--project={self.config.project}",
                    f"--region={self.config.region}",
                    self.name,
                ],
                "cluster-destroy",
                timeout=60,
            )
        except Exception as e:
            log.warning("Cluster destroy failed (was %s): %s", prev.value, e)
            self.state = ClusterState.FAILED
            return

        self.state = ClusterState.DESTROYED
        self._log("Cluster delete initiated (async).")
