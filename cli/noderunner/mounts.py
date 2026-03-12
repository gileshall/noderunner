"""Mount spec parsing, validation, and command generation for gcsfuse mounts."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("noderunner")

# GCS bucket naming rules: 3-63 chars, lowercase letters/numbers/hyphens/dots/underscores
_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$")


@dataclass
class MountSpec:
    """Parsed mount specification for a GCS bucket."""

    bucket: str
    prefix: Optional[str] = None
    hns: bool = False

    @property
    def mount_path(self) -> str:
        """Mount point inside the node and container: /mnt/gcs/<bucket>[/<prefix>]."""
        if self.prefix:
            return f"/mnt/gcs/{self.bucket}/{self.prefix}"
        return f"/mnt/gcs/{self.bucket}"

    @property
    def metadata_entry(self) -> str:
        """Entry for the gcsfuse_buckets metadata value."""
        parts = []
        if self.hns:
            parts.append("hns:")
        parts.append(self.bucket)
        if self.prefix:
            parts.append(f"/{self.prefix}")
        return "".join(parts)


def validate_bucket_name(name: str) -> bool:
    """Check if a bucket name is plausible per GCS naming rules."""
    return bool(_BUCKET_RE.match(name))


def parse_mount(raw: str) -> MountSpec:
    """Parse a --mount value into a MountSpec.

    Accepted formats:
        my-bucket
        my-bucket/subpath
        hns:my-bucket
        hns:my-bucket/subpath
        gs://my-bucket          (stripped with warning)
        gs://hns:my-bucket      (stripped with warning)
    """
    spec = raw.strip()

    # Strip gs:// prefix if present
    if spec.startswith("gs://"):
        log.warning("Stripping gs:// prefix from mount spec: %s", raw)
        spec = spec[5:]

    # Detect and strip hns: prefix
    hns = False
    if spec.startswith("hns:"):
        hns = True
        spec = spec[4:]

    # Split bucket/prefix on first slash
    prefix = None
    if "/" in spec:
        bucket, prefix = spec.split("/", 1)
        # Strip trailing slashes from prefix
        prefix = prefix.rstrip("/")
        if not prefix:
            prefix = None
    else:
        bucket = spec

    if not validate_bucket_name(bucket):
        raise ValueError(f"Invalid bucket name: {bucket!r} (from mount spec {raw!r})")

    return MountSpec(bucket=bucket, prefix=prefix, hns=hns)


def build_metadata_string(mounts: list[MountSpec]) -> str:
    """Produce comma-separated string for --metadata=gcsfuse_buckets=..."""
    return ",".join(m.metadata_entry for m in mounts)


def build_docker_volume_flags(mounts: list[MountSpec]) -> list[str]:
    """Produce list of -v flags for docker run."""
    flags = []
    for m in mounts:
        path = m.mount_path
        flags.extend(["-v", f"{path}:{path}"])
    return flags
