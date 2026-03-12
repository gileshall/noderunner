"""Tests for noderunner.job — docker command and SSH command construction."""

from noderunner.job import build_docker_command, build_ssh_command
from noderunner.mounts import MountSpec


class TestBuildDockerCommand:
    def test_basic(self):
        cmd = build_docker_command(
            image="my-image:latest",
            mounts=[],
            args=[],
            env_vars=[],
        )
        assert "docker run --rm" in cmd
        assert "--device=/dev/fuse" in cmd
        assert "--cap-add SYS_ADMIN" in cmd
        assert "my-image:latest" in cmd

    def test_with_mounts(self):
        mounts = [MountSpec(bucket="my-bucket")]
        cmd = build_docker_command(
            image="img:latest",
            mounts=mounts,
            args=[],
            env_vars=[],
        )
        assert "-v /mnt/gcs/my-bucket:/mnt/gcs/my-bucket" in cmd

    def test_with_env_vars(self):
        cmd = build_docker_command(
            image="img:latest",
            mounts=[],
            args=[],
            env_vars=["FOO=bar", "BAZ=qux"],
        )
        assert "-e FOO=bar" in cmd
        assert "-e BAZ=qux" in cmd

    def test_with_args(self):
        cmd = build_docker_command(
            image="img:latest",
            mounts=[],
            args=["--input", "/data/file.txt"],
            env_vars=[],
        )
        # Args come after the image name
        parts = cmd.split("img:latest")
        assert "--input" in parts[1]
        assert "/data/file.txt" in parts[1]

    def test_args_after_image(self):
        cmd = build_docker_command(
            image="my-image:v1",
            mounts=[],
            args=["arg1", "arg2"],
            env_vars=[],
        )
        idx_image = cmd.index("my-image:v1")
        idx_arg1 = cmd.index("arg1")
        assert idx_arg1 > idx_image


class TestBuildSshCommand:
    def test_basic(self):
        cmd = build_ssh_command(
            cluster_name="noderunner-abc12345-1234567890",
            zone="us-central1-a",
            project="my-project",
            remote_command="echo hello",
        )
        assert cmd[0] == "gcloud"
        assert "compute" in cmd
        assert "ssh" in cmd
        assert "noderunner-abc12345-1234567890-m" in cmd
        assert "--zone=us-central1-a" in cmd
        assert "--project=my-project" in cmd
        assert "--strict-host-key-checking=no" in cmd
        assert "--command=echo hello" in cmd
