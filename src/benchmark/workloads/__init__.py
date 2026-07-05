"""Benchmark workloads definitions for drone-storage-bench.

This package contains workloads definitions including write-heavy ingestion scenarios,
read-heavy query structures, mixed profiles, and control-plane relational JOIN scenarios.
"""

from benchmark.workloads.compression import CompressionEvaluationWorkload
from benchmark.workloads.ingestion import IngestionWorkload
from benchmark.workloads.query import QueryWorkload

__all__ = ["CompressionEvaluationWorkload", "IngestionWorkload", "QueryWorkload"]
