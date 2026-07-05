"""Reporting and visualization module for drone-storage-bench.

This package transforms raw JSON/CSV benchmark metrics into formatted markdown tables,
HTML summaries, and execution artifacts stored in results/ directories.
"""

from benchmark.reporting.generator import ReportGenerator

__all__ = ["ReportGenerator"]
