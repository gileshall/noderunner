"""Remote execution: SSH into Dataproc master and run a Docker container."""

from __future__ import annotations

import logging
import shlex
import subprocess

from noderunner.mounts import MountSpec, build_docker_volume_flags

log = logging.getLogger("noderunner")


def build_docker_command(
    image: str,
    mounts: list[MountSpec],
    args: list[str],
    env_vars: list[str],
) -> str:
    """Build the `docker run` command string that executes on the remote node."""
    parts = [
        "docker", "run", "--rm",
        "--device=/dev/fuse", "--cap-add", "SYS_ADMIN",
    ]

    # Volume mounts: -v /mnt/gcs/X:/mnt/gcs/X
    parts.extend(build_docker_volume_flags(mounts))

    # Environment variables: -e KEY=VALUE
    for env in env_vars:
        parts.extend(["-e", env])

    # Image
    parts.append(image)

    # Container arguments
    parts.extend(args)

    return " ".join(shlex.quote(p) for p in parts)


def build_ssh_command(
    cluster_name: str,
    zone: str,
    project: str,
    remote_command: str,
) -> list[str]:
    """Build the gcloud compute ssh command."""
    return [
        "gcloud", "compute", "ssh",
        f"{cluster_name}-m",
        f"--zone={zone}",
        f"--project={project}",
        "--strict-host-key-checking=no",
        f"--command={remote_command}",
    ]


def execute_docker(
    cluster_name: str,
    zone: str,
    project: str,
    image: str,
    mounts: list[MountSpec],
    args: list[str],
    env_vars: list[str],
    dry_run: bool = False,
) -> int:
    """SSH into the Dataproc master and run a Docker container.

    Returns the exit code of the remote docker run command.
    """
    docker_cmd = build_docker_command(image, mounts, args, env_vars)
    ssh_cmd = build_ssh_command(cluster_name, zone, project, docker_cmd)

    log.info("Executing on %s-m: %s", cluster_name, docker_cmd)

    if dry_run:
        log.info("DRY RUN — would execute:\n  %s", " \\\n    ".join(ssh_cmd))
        return 0

    # Direct passthrough: stdout/stderr flow through to the orchestrator
    # (and thus to Cromwell logs). No capture, no buffering.
    result = subprocess.run(ssh_cmd, stdout=None, stderr=None)
    return result.returncode
