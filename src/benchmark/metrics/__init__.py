"""Metrics collection and aggregation package for drone-storage-bench.

This package registers latencies, error counts, and resources during benchmark runs,
producing clean structured statistics (e.g. throughput, percentiles) for downstream reports.
"""

from benchmark.metrics.collector import MetricsCollector

__all__ = ["MetricsCollector"]
