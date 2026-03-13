# noderunner

Run Docker containers on ephemeral single-node Dataproc clusters with GCS buckets mounted as
local filesystems via gcsfuse. Your container sees ordinary directories — no GCS SDK, no
`gsutil`, no cloud-specific code needed.

## Quick start

Import `wdl/noderunner_run.wdl` from [Dockstore](https://dockstore.org) into your Terra
workspace, then submit with an inputs JSON like this:

```json
{
  "noderunner_run.project": "my-project",
  "noderunner_run.image": "us-docker.pkg.dev/my-project/noderunner/file-ops:latest",
  "noderunner_run.mounts": [
    "my-input-bucket",
    "my-output-bucket"
  ],
  "noderunner_run.env_vars": [
    "INPUT_BUCKET=my-input-bucket",
    "OUTPUT_BUCKET=my-output-bucket"
  ]
}
```

Your Docker image must be in Artifact Registry or GCR (not DockerHub) if running in a
private subnet.

## How it works

```
WDL task (Cromwell/Terra)
  └─ noderunner orchestrator (Docker container on task VM)
       └─ gcloud dataproc clusters create (single-node, with gcsfuse init action)
            └─ gcloud compute ssh → docker run (your container)
                 └─ gcsfuse mount → GCS bucket (transparent filesystem access)
```

1. **Creates** a single-node Dataproc cluster with Docker and gcsfuse
2. **Waits** for the cluster to reach RUNNING state
3. **Executes** your Docker image on the master node via SSH
4. **Streams** stdout/stderr back to the orchestrator
5. **Deletes** the cluster — even if step 3 failed

## Storage architecture

Three tiers of storage are available inside your container:

| Tier | Path | Speed | Persistence | Use case |
|------|------|-------|-------------|----------|
| gcsfuse/GCS | `/mnt/gcs/<bucket>` | Network-bound | Durable | Input/output data |
| Boot disk | `/tmp` | Fast (pd-ssd) | Ephemeral | Local scratch, BAM copies |
| Local SSD | `/mnt/ssd` | Fastest (NVMe) | Ephemeral | High-IOPS scratch |

**Rule of thumb:** Read inputs from gcsfuse, do heavy computation on local disk, write outputs
back to gcsfuse.

## Building your own workload

Your Docker image sees gcsfuse mounts as ordinary directories at `/mnt/gcs/<bucket>`.

### Sequential writes (streaming to GCS)

Writing files sequentially to a gcsfuse mount works well — gcsfuse v3 streams data directly
to GCS without staging to local disk:

```bash
my-tool --output /mnt/gcs/output-bucket/results.csv
```

### Multi-threaded tools with random reads

Tools that do concurrent random byte-range reads (samtools with `-@`, BWA-MEM, GATK) will
perform poorly directly on gcsfuse. **Copy input files to local disk first:**

```bash
cp /mnt/gcs/input-bucket/sample.bam /tmp/sample.bam
samtools flagstat -@ 4 /tmp/sample.bam > /mnt/gcs/output-bucket/flagstat.txt
```

### Tools that rename directories

Tools that write to a temp directory and then rename (checkpointing, many ML frameworks) need
an **HNS bucket** for the output. Flat GCS buckets do not support atomic directory rename.

If you cannot use HNS, do all intermediate work on local disk and copy final outputs to the
gcsfuse mount at the end.

## Bucket types: flat vs HNS

| | Flat buckets | HNS buckets |
|---|---|---|
| Directory rename | Rewrites every object (slow, non-atomic) | Atomic metadata operation |
| `--implicit-dirs` | Required | Not needed |
| Best for | Read-only inputs, archives | Output buckets, scratch |

Create an HNS bucket:
```bash
gcloud storage buckets create gs://my-output-bucket \
  --location=us-central1 \
  --enable-hierarchical-namespace
```

Signal HNS in mount specs with the `hns:` prefix: `--mount hns:my-output-bucket`

## Examples

- **[file_ops](examples/file_ops/)** — Simplest demo. Lists files, writes a probe JSON. Use to verify setup.
- **[md5sum](examples/md5sum/)** — Compute MD5 checksums of files in a GCS bucket. Standard Unix tools treating GCS as a filesystem.
- **[samtools_flagstat](examples/samtools_flagstat/)** — Run samtools on a BAM in GCS. Demonstrates the copy-to-local-disk pattern for multi-threaded tools.

## WDL reference

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `project` | String | required | GCP project |
| `image` | String | required | Docker image to run |
| `region` | String? | None | GCP region. Auto-detected from the task VM if omitted. |
| `mounts` | Array[String] | `[]` | GCS bucket mount specs |
| `args` | Array[String] | `[]` | Args passed to container |
| `output_specs` | Array[String] | `[]` | `gs://src:local_dst` output specs |
| `machine_type` | String | `"n2-highmem-8"` | Machine type |
| `boot_disk_gb` | Int | `500` | Boot disk size GB |
| `local_ssds` | Int | `0` | Number of local NVMe SSDs |
| `no_external_ip` | Boolean | `true` | Private subnet mode |
| `max_age_minutes` | Int | `120` | Max cluster age |
| `env_vars` | Array[String] | `[]` | `KEY=VALUE` env vars |
| `subnet` | String? | None | Subnetwork URI |
| `cluster_name` | String? | None | Cluster name override |
| `custom_image` | String? | None | Pre-baked Dataproc custom image URI |

## CLI reference

The CLI is used by the orchestrator container and can also be run directly for development/debugging.

```
noderunner run [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project` | str | required | GCP project ID |
| `--region` | str | auto-detected | GCP region. Detected from GCE metadata if omitted. |
| `--image` | str | required | Docker image (Artifact Registry or GCR) |
| `--mount` | str | (multi) | GCS bucket mount spec. Repeat for multiple. |
| `--arg` | str | (multi) | Container argument. Repeat for multiple. |
| `--machine-type` | str | `n2-highmem-8` | Machine type |
| `--boot-disk-size` | int | `500` | Boot disk size GB |
| `--boot-disk-type` | str | `pd-ssd` | Boot disk type |
| `--local-ssd` | int | `0` | Number of local NVMe SSDs |
| `--subnet` | str | | Subnetwork URI |
| `--no-external-ip` | flag | `true` | Disable external IP |
| `--max-age` | int | `120` | Cluster max age in minutes |
| `--cluster-name` | str | | Override auto-generated name |
| `--image-version` | str | `2.2-debian12` | Dataproc image version |
| `--custom-image` | str | | Pre-baked Dataproc custom image URI |
| `--env` | str | (multi) | Env var for container (`KEY=VALUE`) |
| `--output` | str | (multi) | Output copy spec (`gs://src:local_dst`) |
| `--staging-bucket` | str | | GCS bucket for init script staging |
| `--dry-run` | flag | | Print commands without executing |

## Permissions required

Two service account principals need the right permissions:

### 1. Task VM service account (runs the orchestrator)
- `roles/dataproc.editor` — create/delete Dataproc clusters
- `roles/compute.osLogin` or SSH access to cluster nodes
- `roles/storage.objectAdmin` on the staging bucket

### 2. Dataproc cluster service account (runs on the node)
- `roles/storage.objectViewer` on input buckets
- `roles/storage.objectAdmin` on output buckets
- Access to pull Docker images from Artifact Registry

These are **two different principals**. The task VM authenticates via its service account
(metadata server in Cromwell). The Dataproc node authenticates as the Compute Engine default
service account (or a custom SA if specified).
