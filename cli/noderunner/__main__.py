"""CLI entry point: python -m noderunner"""

from __future__ import annotations

import logging
import subprocess
import sys

import click

from noderunner import __version__
from noderunner.cluster import ClusterConfig
from noderunner.mounts import parse_mount
from noderunner.run import run_workflow
from noderunner.utils import parse_output_spec

log = logging.getLogger("noderunner")


@click.group()
@click.version_option(version=__version__, prog_name="noderunner")
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    help="Logging verbosity.",
)
def cli(log_level: str) -> None:
    """noderunner -- run Docker containers on ephemeral Dataproc single-node clusters."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )


@cli.command()
@click.option("--project", required=True, help="GCP project ID.")
@click.option("--region", required=True, help="GCP region.")
@click.option("--image", required=True, help="Docker image to run (Artifact Registry or GCR).")
@click.option("--mount", "mount_specs", multiple=True, help="GCS bucket to mount. Repeat for multiple.")
@click.option("--arg", "container_args", multiple=True, help="Argument passed to the Docker container. Repeat for multiple.")
@click.option("--machine-type", default="n2-highmem-8", show_default=True, help="Master machine type.")
@click.option("--boot-disk-size", default=500, type=int, show_default=True, help="Boot disk size in GB.")
@click.option("--boot-disk-type", default="pd-ssd", show_default=True, help="Boot disk type.")
@click.option("--local-ssd", default=0, type=int, show_default=True, help="Number of local NVMe SSDs.")
@click.option("--subnet", default=None, help="Subnetwork URI.")
@click.option("--no-external-ip/--external-ip", default=True, show_default=True, help="Disable external IP (private subnet safe).")
@click.option("--max-age", default=120, type=int, show_default=True, help="Cluster max age in minutes.")
@click.option("--cluster-name", default=None, help="Override auto-generated cluster name.")
@click.option("--image-version", default="2.2-debian12", show_default=True, help="Dataproc image version.")
@click.option("--custom-image", default=None, help="Full URI of a pre-baked Dataproc custom image.")
@click.option("--env", "env_vars", multiple=True, help="Environment variable for docker run (-e KEY=VALUE). Repeat for multiple.")
@click.option("--output", "output_specs", multiple=True, help="Output copy spec: gs://src/path:local_dest. Repeat for multiple.")
@click.option("--staging-bucket", default=None, help="GCS bucket for staging init script. Auto-created if omitted.")
@click.option("--dry-run", is_flag=True, default=False, help="Print gcloud commands without executing.")
def run(
    project: str,
    region: str,
    image: str,
    mount_specs: tuple[str, ...],
    container_args: tuple[str, ...],
    machine_type: str,
    boot_disk_size: int,
    boot_disk_type: str,
    local_ssd: int,
    subnet: str | None,
    no_external_ip: bool,
    max_age: int,
    cluster_name: str | None,
    image_version: str,
    custom_image: str | None,
    env_vars: tuple[str, ...],
    output_specs: tuple[str, ...],
    staging_bucket: str | None,
    dry_run: bool,
) -> None:
    """Create a Dataproc cluster, run a Docker container, then destroy the cluster."""
    # Parse mounts
    mounts = [parse_mount(m) for m in mount_specs]

    # Parse outputs
    outputs = [parse_output_spec(o) for o in output_specs]

    # Build config
    config = ClusterConfig(
        project=project,
        region=region,
        machine_type=machine_type,
        boot_disk_size_gb=boot_disk_size,
        boot_disk_type=boot_disk_type,
        local_ssds=local_ssd,
        subnet=subnet,
        no_external_ip=no_external_ip,
        max_age_minutes=max_age,
        cluster_name=cluster_name,
        image_version=image_version,
        custom_image=custom_image,
        staging_bucket=staging_bucket,
    )

    try:
        run_workflow(
            config=config,
            image=image,
            mounts=mounts,
            args=list(container_args),
            env_vars=list(env_vars),
            outputs=outputs,
            dry_run=dry_run,
        )
    except subprocess.CalledProcessError as e:
        log.error("Command failed (exit %d): %s", e.returncode, " ".join(e.cmd))
        if e.stderr:
            for line in e.stderr.strip().splitlines()[-20:]:
                log.error("  %s", line)
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        log.warning("Interrupted.")
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as e:
        log.exception("Fatal error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    cli()
