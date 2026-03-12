"""Tests for noderunner.mounts — mount spec parsing, validation, and command generation."""

import logging

import pytest

from noderunner.mounts import (
    MountSpec,
    build_docker_volume_flags,
    build_metadata_string,
    parse_mount,
    validate_bucket_name,
)


class TestValidateBucketName:
    def test_valid_simple(self):
        assert validate_bucket_name("my-bucket") is True

    def test_valid_with_dots(self):
        assert validate_bucket_name("my.bucket.name") is True

    def test_valid_with_underscores(self):
        assert validate_bucket_name("my_bucket_name") is True

    def test_too_short(self):
        assert validate_bucket_name("ab") is False

    def test_too_long(self):
        assert validate_bucket_name("a" * 64) is False

    def test_uppercase_rejected(self):
        assert validate_bucket_name("My-Bucket") is False

    def test_starts_with_hyphen(self):
        assert validate_bucket_name("-my-bucket") is False


class TestParseMount:
    def test_simple_bucket(self):
        spec = parse_mount("my-bucket")
        assert spec.bucket == "my-bucket"
        assert spec.prefix is None
        assert spec.hns is False

    def test_bucket_with_prefix(self):
        spec = parse_mount("my-bucket/subdir")
        assert spec.bucket == "my-bucket"
        assert spec.prefix == "subdir"
        assert spec.hns is False

    def test_bucket_with_nested_prefix(self):
        spec = parse_mount("my-bucket/path/to/data")
        assert spec.bucket == "my-bucket"
        assert spec.prefix == "path/to/data"

    def test_hns_bucket(self):
        spec = parse_mount("hns:my-bucket")
        assert spec.bucket == "my-bucket"
        assert spec.prefix is None
        assert spec.hns is True

    def test_hns_with_prefix(self):
        spec = parse_mount("hns:my-bucket/output")
        assert spec.bucket == "my-bucket"
        assert spec.prefix == "output"
        assert spec.hns is True

    def test_gs_prefix_stripped(self, caplog):
        with caplog.at_level(logging.WARNING):
            spec = parse_mount("gs://my-bucket")
        assert spec.bucket == "my-bucket"
        assert "Stripping gs://" in caplog.text

    def test_gs_prefix_with_hns(self, caplog):
        with caplog.at_level(logging.WARNING):
            spec = parse_mount("gs://hns:my-bucket")
        assert spec.bucket == "my-bucket"
        assert spec.hns is True

    def test_trailing_slash_stripped(self):
        spec = parse_mount("my-bucket/")
        assert spec.bucket == "my-bucket"
        assert spec.prefix is None

    def test_invalid_bucket_raises(self):
        with pytest.raises(ValueError, match="Invalid bucket name"):
            parse_mount("UPPER-CASE")

    def test_whitespace_stripped(self):
        spec = parse_mount("  my-bucket  ")
        assert spec.bucket == "my-bucket"


class TestMountSpecProperties:
    def test_mount_path_simple(self):
        spec = MountSpec(bucket="my-bucket")
        assert spec.mount_path == "/mnt/gcs/my-bucket"

    def test_mount_path_with_prefix(self):
        spec = MountSpec(bucket="my-bucket", prefix="data/input")
        assert spec.mount_path == "/mnt/gcs/my-bucket/data/input"

    def test_metadata_entry_simple(self):
        spec = MountSpec(bucket="my-bucket")
        assert spec.metadata_entry == "my-bucket"

    def test_metadata_entry_hns(self):
        spec = MountSpec(bucket="my-bucket", hns=True)
        assert spec.metadata_entry == "hns:my-bucket"

    def test_metadata_entry_with_prefix(self):
        spec = MountSpec(bucket="my-bucket", prefix="sub")
        assert spec.metadata_entry == "my-bucket/sub"

    def test_metadata_entry_hns_with_prefix(self):
        spec = MountSpec(bucket="my-bucket", prefix="sub", hns=True)
        assert spec.metadata_entry == "hns:my-bucket/sub"


class TestBuildMetadataString:
    def test_single_mount(self):
        mounts = [MountSpec(bucket="bucket-a")]
        assert build_metadata_string(mounts) == "bucket-a"

    def test_multiple_mounts(self):
        mounts = [
            MountSpec(bucket="bucket-a"),
            MountSpec(bucket="bucket-b", prefix="data"),
            MountSpec(bucket="bucket-c", hns=True),
        ]
        assert build_metadata_string(mounts) == "bucket-a,bucket-b/data,hns:bucket-c"

    def test_empty(self):
        assert build_metadata_string([]) == ""


class TestBuildDockerVolumeFlags:
    def test_single_mount(self):
        mounts = [MountSpec(bucket="my-bucket")]
        flags = build_docker_volume_flags(mounts)
        assert flags == ["-v", "/mnt/gcs/my-bucket:/mnt/gcs/my-bucket"]

    def test_multiple_mounts(self):
        mounts = [
            MountSpec(bucket="bucket-a"),
            MountSpec(bucket="bucket-b", prefix="sub"),
        ]
        flags = build_docker_volume_flags(mounts)
        assert flags == [
            "-v", "/mnt/gcs/bucket-a:/mnt/gcs/bucket-a",
            "-v", "/mnt/gcs/bucket-b/sub:/mnt/gcs/bucket-b/sub",
        ]

    def test_empty(self):
        assert build_docker_volume_flags([]) == []
