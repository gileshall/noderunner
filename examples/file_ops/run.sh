#!/bin/bash
# file_ops — simplest possible noderunner demonstration.
#
# Expects:
#   - An input bucket mounted at /mnt/gcs/<INPUT_BUCKET> (read-only is fine)
#   - An output bucket mounted at /mnt/gcs/<OUTPUT_BUCKET> (must be writable)
#
# Environment variables:
#   INPUT_BUCKET   — name of the input bucket (required)
#   OUTPUT_BUCKET  — name of the output bucket (required)
#   INPUT_FILE     — optional: specific file to stat within the input bucket
#
# Produces:
#   /mnt/gcs/<OUTPUT_BUCKET>/noderunner-probe.json
#
# Usage:
#   noderunner run \
#     --project "$PROJECT" \
#     --region "$REGION" \
#     --image "$IMAGE" \
#     --mount "$INPUT_BUCKET" \
#     --mount "$OUTPUT_BUCKET" \
#     --env "INPUT_BUCKET=$INPUT_BUCKET" \
#     --env "OUTPUT_BUCKET=$OUTPUT_BUCKET"
set -euo pipefail

INPUT_DIR="/mnt/gcs/${INPUT_BUCKET:?INPUT_BUCKET must be set}"
OUTPUT_DIR="/mnt/gcs/${OUTPUT_BUCKET:?OUTPUT_BUCKET must be set}"

echo "=== noderunner file_ops probe ==="

# 1. List the input bucket and count files
echo "Listing ${INPUT_DIR}..."
FILE_COUNT=$(find "$INPUT_DIR" -maxdepth 1 -type f 2>/dev/null | wc -l)
echo "Files in input bucket: ${FILE_COUNT}"

# 2. Stat a specific file if requested
if [ -n "${INPUT_FILE:-}" ]; then
    TARGET="${INPUT_DIR}/${INPUT_FILE}"
    echo "Stat: ${TARGET}"
    stat "$TARGET" || echo "WARNING: could not stat ${TARGET}"
fi

# 3. Write a probe JSON to the output bucket
PROBE_FILE="${OUTPUT_DIR}/noderunner-probe.json"
echo "Writing probe to ${PROBE_FILE}..."
jq -n \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg host "$(hostname)" \
    --arg disk "$(df -h / | tail -1)" \
    --argjson files "$FILE_COUNT" \
    '{timestamp: $ts, hostname: $host, disk_info: $disk, input_file_count: $files}' \
    > "$PROBE_FILE"

echo "Probe written successfully."
cat "$PROBE_FILE"
echo "=== done ==="
