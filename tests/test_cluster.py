"""Tests for noderunner.cluster — cluster name, command construction."""

import pytest

from noderunner.cluster import ClusterConfig, NoderunnerCluster
from noderunner.mounts import MountSpec


class TestBuildCreateCommand:
    """Test gcloud command construction without executing anything."""

    def _make_cluster(self, **overrides) -> NoderunnerCluster:
        mounts = overrides.pop("mounts", [])
        defaults = dict(project="test-project", region="us-central1", staging_bucket="gs://test-bucket")
        defaults.update(overrides)
        config = ClusterConfig(**defaults)
        cluster = NoderunnerCluster(config, mounts, dry_run=True)
        cluster._init_gcs = "gs://test-bucket/noderunner/init/gcsfuse.sh"
        return cluster

    def test_required_flags(self):
        cluster = self._make_cluster()
        cmd = cluster.build_create_command()
        assert "gcloud" in cmd
        assert "dataproc" in cmd
        assert "clusters" in cmd
        assert "create" in cmd
        assert "--single-node" in cmd
        assert "--optional-components=DOCKER" in cmd
        assert "--properties=dataproc:dataproc.allow.zero.workers=true" in cmd
        assert "--initialization-action-timeout=10m" in cmd
        assert f"--region=us-central1" in cmd
        assert f"--project=test-project" in cmd

    def test_default_machine_flags(self):
        cluster = self._make_cluster()
        cmd = cluster.build_create_command()
        assert "--master-machine-type=n2-highmem-8" in cmd
        assert "--master-boot-disk-size=500" in cmd
        assert "--master-boot-disk-type=pd-ssd" in cmd

    def test_max_age(self):
        cluster = self._make_cluster(max_age_minutes=60)
        cmd = cluster.build_create_command()
        assert "--max-age=60m" in cmd

    def test_no_address_default(self):
        cluster = self._make_cluster()
        cmd = cluster.build_create_command()
        assert "--no-address" in cmd

    def test_external_ip(self):
        cluster = self._make_cluster(no_external_ip=False)
        cmd = cluster.build_create_command()
        assert "--no-address" not in cmd

    def test_custom_image_overrides_version(self):
        cluster = self._make_cluster(
            custom_image="projects/p/global/images/my-image"
        )
        cmd = cluster.build_create_command()
        assert "--image=projects/p/global/images/my-image" in cmd
        assert not any(c.startswith("--image-version=") for c in cmd)

    def test_image_version_default(self):
        cluster = self._make_cluster()
        cmd = cluster.build_create_command()
        assert "--image-version=2.2-debian12" in cmd

    def test_subnet(self):
        cluster = self._make_cluster(subnet="projects/p/regions/r/subnetworks/sub")
        cmd = cluster.build_create_command()
        assert "--subnet=projects/p/regions/r/subnetworks/sub" in cmd

    def test_local_ssds(self):
        cluster = self._make_cluster(local_ssds=2)
        cmd = cluster.build_create_command()
        assert "--num-master-local-ssds=2" in cmd
        assert "--master-local-ssd-interface=NVME" in cmd

    def test_no_local_ssds_by_default(self):
        cluster = self._make_cluster()
        cmd = cluster.build_create_command()
        assert not any("local-ssd" in c for c in cmd)

    def test_mounts_in_metadata(self):
        mounts = [
            MountSpec(bucket="bucket-a"),
            MountSpec(bucket="bucket-b", hns=True),
        ]
        cluster = self._make_cluster(mounts=mounts)
        cmd = cluster.build_create_command()
        assert "--metadata=gcsfuse_buckets=bucket-a,hns:bucket-b" in cmd

    def test_no_mounts_no_metadata(self):
        cluster = self._make_cluster()
        cmd = cluster.build_create_command()
        assert not any(c.startswith("--metadata=gcsfuse_buckets=") for c in cmd)

    def test_init_script_in_command(self):
        cluster = self._make_cluster()
        cmd = cluster.build_create_command()
        assert "--initialization-actions=gs://test-bucket/noderunner/init/gcsfuse.sh" in cmd
