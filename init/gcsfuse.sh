#!/bin/bash
# Dataproc initialization action: install gcsfuse and mount GCS buckets.
# Runs as root on the master node before the cluster is marked RUNNING.
#
# Bucket specs are passed via cluster metadata:
#   --metadata=gcsfuse_buckets=bucket-one,bucket-two/subpath,hns:bucket-three
#
# The hns: prefix selects HNS-appropriate mount flags (no --implicit-dirs).
# A subpath after the bucket name triggers --only-dir mounting.
set -euo pipefail

ROLE=$(/usr/share/google/get_metadata_value attributes/dataproc-role)
if [ "$ROLE" != "Master" ]; then
    echo "Worker node — skipping gcsfuse setup."
    exit 0
fi

echo "=== Installing gcsfuse ==="

# Install gcsfuse from the Google Cloud apt repository
export GCSFUSE_REPO=gcsfuse-$(lsb_release -c -s)
echo "deb https://packages.cloud.google.com/apt ${GCSFUSE_REPO} main" \
    | tee /etc/apt/sources.list.d/gcsfuse.list
curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | apt-key add -
apt-get update -qq
apt-get install -y -qq gcsfuse

# Enable user_allow_other so Docker containers can access FUSE mounts
sed -i 's/#user_allow_other/user_allow_other/' /etc/fuse.conf

# Determine cache directory: local SSD if available, otherwise /tmp
if [ -d /mnt/ssd ]; then
    CACHE_DIR=/mnt/ssd/gcsfuse-cache
else
    CACHE_DIR=/tmp/gcsfuse-cache
fi
mkdir -p "$CACHE_DIR"

# Read bucket specs from cluster metadata
BUCKETS=$(/usr/share/google/get_metadata_value attributes/gcsfuse_buckets 2>/dev/null || true)
if [ -z "$BUCKETS" ]; then
    echo "No gcsfuse_buckets metadata found — nothing to mount."
    exit 0
fi

echo "Bucket specs: $BUCKETS"

IFS=',' read -ra SPECS <<< "$BUCKETS"
for SPEC in "${SPECS[@]}"; do
    IS_HNS=false
    ONLY_DIR=""

    # Strip hns: prefix
    if [[ "$SPEC" == hns:* ]]; then
        IS_HNS=true
        SPEC="${SPEC#hns:}"
    fi

    # Split bucket/subpath
    BUCKET="$SPEC"
    if [[ "$SPEC" == */* ]]; then
        BUCKET="${SPEC%%/*}"
        ONLY_DIR="${SPEC#*/}"
    fi

    # Build mount point
    MOUNT_POINT="/mnt/gcs/${SPEC}"
    mkdir -p "$MOUNT_POINT"

    # Idempotency check
    if mountpoint -q "$MOUNT_POINT"; then
        echo "Already mounted: $MOUNT_POINT"
        continue
    fi

    LOG_FILE="/var/log/gcsfuse-${BUCKET}.log"

    # Build gcsfuse command
    GCSFUSE_ARGS=(
        --allow-other
        --metadata-cache-ttl-secs=-1
        --stat-cache-max-size-mb=-1
        --type-cache-max-size-mb=-1
        --file-cache-cache-file-for-range-read
        "--cache-dir=${CACHE_DIR}"
        "--log-file=${LOG_FILE}"
    )

    # Flat buckets need --implicit-dirs; HNS buckets do not
    if [ "$IS_HNS" = false ]; then
        GCSFUSE_ARGS+=(--implicit-dirs)
    fi

    # Subpath mounting via --only-dir
    if [ -n "$ONLY_DIR" ]; then
        GCSFUSE_ARGS+=("--only-dir=${ONLY_DIR}")
    fi

    echo "Mounting ${BUCKET} at ${MOUNT_POINT} (hns=${IS_HNS}, only_dir=${ONLY_DIR:-none})"
    gcsfuse "${GCSFUSE_ARGS[@]}" "$BUCKET" "$MOUNT_POINT"
    echo "Mounted successfully: $MOUNT_POINT"
done

echo "=== gcsfuse setup complete ==="
