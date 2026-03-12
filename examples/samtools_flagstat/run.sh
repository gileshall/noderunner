#!/bin/bash
# samtools_flagstat — run samtools flagstat on a BAM in GCS via gcsfuse.
#
# This example demonstrates the CORRECT pattern for multi-threaded bioinformatics
# tools: copy the input from the gcsfuse mount to local disk first, then operate.
#
# WHY? samtools with -@ threads does concurrent random-read seeks into a BAM.
# gcsfuse handles single-threaded sequential reads well, but concurrent multi-thread
# random reads can degrade catastrophically (up to 100x slower than sequential).
# Copying to local disk first avoids this entirely.
#
# Expects:
#   - An input bucket mounted at /mnt/gcs/<INPUT_BUCKET>
#   - An output bucket mounted at /mnt/gcs/<OUTPUT_BUCKET> (must be writable)
#
# Environment variables:
#   INPUT_BUCKET  — name of the input bucket (required)
#   OUTPUT_BUCKET — name of the output bucket (required)
#   BAM_PATH      — path to BAM file within the input bucket (required)
#   THREADS       — number of samtools threads (default: 4)
#
# Produces:
#   /mnt/gcs/<OUTPUT_BUCKET>/flagstat.txt
#
# Usage:
#   noderunner run \
#     --project "$PROJECT" \
#     --region "$REGION" \
#     --image "$IMAGE" \
#     --mount "$INPUT_BUCKET" \
#     --mount "hns:$OUTPUT_BUCKET" \
#     --env "INPUT_BUCKET=$INPUT_BUCKET" \
#     --env "OUTPUT_BUCKET=$OUTPUT_BUCKET" \
#     --env "BAM_PATH=path/to/sample.bam"
set -euo pipefail

INPUT_DIR="/mnt/gcs/${INPUT_BUCKET:?INPUT_BUCKET must be set}"
OUTPUT_DIR="/mnt/gcs/${OUTPUT_BUCKET:?OUTPUT_BUCKET must be set}"
BAM="${INPUT_DIR}/${BAM_PATH:?BAM_PATH must be set}"
THREADS="${THREADS:-4}"

echo "=== noderunner samtools_flagstat ==="
echo "BAM:     ${BAM}"
echo "Threads: ${THREADS}"

# Step 1: Copy BAM from gcsfuse mount to local disk.
# This is critical for performance with multi-threaded samtools.
echo "Copying BAM to local disk..."
LOCAL_BAM="/tmp/$(basename "$BAM")"
cp "$BAM" "$LOCAL_BAM"
echo "Copy complete: $(stat -c %s "$LOCAL_BAM") bytes"

# Step 2: Run samtools flagstat on the local copy.
echo "Running samtools flagstat..."
samtools flagstat -@ "$THREADS" "$LOCAL_BAM" | tee /tmp/flagstat.txt

# Step 3: Write output back to the gcsfuse mount.
OUTPUT_FILE="${OUTPUT_DIR}/flagstat.txt"
cp /tmp/flagstat.txt "$OUTPUT_FILE"
echo "Output written to ${OUTPUT_FILE}"

# Cleanup local copy
rm -f "$LOCAL_BAM" /tmp/flagstat.txt

echo "=== done ==="
