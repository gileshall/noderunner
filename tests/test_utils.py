"""Tests for noderunner.utils — cluster name generation and output spec parsing."""

import re

import pytest

from noderunner.utils import OutputSpec, generate_cluster_name, parse_output_spec


class TestGenerateClusterName:
    def test_format(self):
        name = generate_cluster_name()
        assert name.startswith("noderunner-")
        # noderunner-<8hex>-<timestamp>
        parts = name.split("-", 1)
        assert parts[0] == "noderunner"

    def test_uniqueness(self):
        names = {generate_cluster_name() for _ in range(100)}
        assert len(names) == 100

    def test_valid_chars(self):
        name = generate_cluster_name()
        assert re.match(r"^[a-z0-9-]+$", name)

    def test_reasonable_length(self):
        name = generate_cluster_name()
        # noderunner(10) + -(1) + hex(8) + -(1) + timestamp(~10) = ~30
        assert len(name) < 40


class TestParseOutputSpec:
    def test_valid(self):
        spec = parse_output_spec("gs://my-bucket/path/file.txt:./output.txt")
        assert spec == OutputSpec(src="gs://my-bucket/path/file.txt", dst="./output.txt")

    def test_valid_nested(self):
        spec = parse_output_spec("gs://bucket/a/b/c.csv:results/c.csv")
        assert spec == OutputSpec(src="gs://bucket/a/b/c.csv", dst="results/c.csv")

    def test_no_gs_prefix_raises(self):
        with pytest.raises(ValueError, match="must start with gs://"):
            parse_output_spec("s3://bucket/file:out")

    def test_no_colon_raises(self):
        with pytest.raises(ValueError, match="must be 'gs://src:dst'"):
            parse_output_spec("gs://bucket/file")

    def test_colon_in_path(self):
        # Last colon separates src:dst
        spec = parse_output_spec("gs://bucket/file:with:colons:out.txt")
        assert spec.src == "gs://bucket/file:with:colons"
        assert spec.dst == "out.txt"
