#!/bin/bash
# md5sum — compute MD5 checksums of files in a GCS bucket via gcsfuse.
#
# Expects:
#   - An input bucket mounted at /mnt/gcs/<INPUT_BUCKET>
#   - An output bucket mounted at /mnt/gcs/<OUTPUT_BUCKET> (must be writable)
#
# Environment variables:
#   INPUT_BUCKET   — name of the input bucket (required)
#   OUTPUT_BUCKET  — name of the output bucket (required)
#   INPUT_GLOB     — optional: glob pattern within the input bucket (default: *)
#
# Produces:
#   /mnt/gcs/<OUTPUT_BUCKET>/checksums.txt
#
# Usage:
#   noderunner run \
#     --project "$PROJECT" \
#     --region "$REGION" \
#     --image "$IMAGE" \
#     --mount "$INPUT_BUCKET" \
#     --mount "$OUTPUT_BUCKET" \
#     --env "INPUT_BUCKET=$INPUT_BUCKET" \
#     --env "OUTPUT_BUCKET=$OUTPUT_BUCKET" \
#     --env "INPUT_GLOB=*.fastq.gz"
set -euo pipefail

INPUT_DIR="/mnt/gcs/${INPUT_BUCKET:?INPUT_BUCKET must be set}"
OUTPUT_DIR="/mnt/gcs/${OUTPUT_BUCKET:?OUTPUT_BUCKET must be set}"
GLOB="${INPUT_GLOB:-*}"

echo "=== noderunner md5sum ==="
echo "Input:  ${INPUT_DIR}/${GLOB}"
echo "Output: ${OUTPUT_DIR}/checksums.txt"

# Find matching files and compute checksums
OUTPUT_FILE="${OUTPUT_DIR}/checksums.txt"
find "$INPUT_DIR" -maxdepth 1 -name "$GLOB" -type f -print0 \
    | xargs -0 md5sum \
    > "$OUTPUT_FILE"

COUNT=$(wc -l < "$OUTPUT_FILE")
echo "Computed ${COUNT} checksums."
cat "$OUTPUT_FILE"
echo "=== done ==="
