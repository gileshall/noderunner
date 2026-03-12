"""The `noderunner run` orchestration: create cluster, run docker, destroy cluster."""

from __future__ import annotations

import logging
import sys

from noderunner.cluster import ClusterConfig, NoderunnerCluster
from noderunner.job import execute_docker
from noderunner.mounts import MountSpec
from noderunner.utils import OutputSpec, copy_outputs

log = logging.getLogger("noderunner")


def run_workflow(
    config: ClusterConfig,
    image: str,
    mounts: list[MountSpec],
    args: list[str],
    env_vars: list[str],
    outputs: list[OutputSpec],
    dry_run: bool = False,
) -> None:
    """Full lifecycle: create cluster -> run docker -> destroy cluster.

    Exits with the docker container's exit code.
    """
    exit_code = 0

    with NoderunnerCluster(config, mounts, dry_run=dry_run) as cluster:
        zone = cluster.get_master_zone()
        cluster.state = cluster.state  # stays RUNNING

        exit_code = execute_docker(
            cluster_name=cluster.name,
            zone=zone,
            project=config.project,
            image=image,
            mounts=mounts,
            args=args,
            env_vars=env_vars,
            dry_run=dry_run,
        )

        if exit_code != 0:
            log.error("Docker container exited with code %d", exit_code)

    # Copy outputs after cluster is destroyed (outputs are in GCS, not on the node)
    if outputs and exit_code == 0:
        copy_outputs(outputs)

    if exit_code != 0:
        sys.exit(exit_code)
