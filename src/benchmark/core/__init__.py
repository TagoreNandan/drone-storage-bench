"""Core Abstract Interfaces and Base Classes for drone-storage-bench.

This package contains standard base classes and interfaces that ensure ClickHouse,
TimescaleDB, QuestDB, and InfluxDB 3 are tested using identical calling conventions
and metrics instrumentation.
"""

from benchmark.core.database import BaseDatabaseClient
from benchmark.core.runner import BaseWorkloadRunner
from benchmark.core.seed import DeterministicSeedManager
from benchmark.core.specification import (
    BenchmarkMetric,
    BenchmarkResult,
    BenchmarkScenario,
    BenchmarkSuite,
    DatasetProfile,
    ExpectedOutputSpec,
    MetricType,
    MetricUnit,
    QueryProfile,
    ScenarioPriority,
    ScenarioType,
    TelemetryRecord,
    WorkloadProfile,
)
from benchmark.core.workload import BaseWorkload

__all__ = [
    "BaseDatabaseClient",
    "BaseWorkload",
    "BaseWorkloadRunner",
    "BenchmarkMetric",
    "BenchmarkResult",
    "BenchmarkScenario",
    "BenchmarkSuite",
    "DatasetProfile",
    "DeterministicSeedManager",
    "ExpectedOutputSpec",
    "MetricType",
    "MetricUnit",
    "QueryProfile",
    "ScenarioPriority",
    "ScenarioType",
    "TelemetryRecord",
    "WorkloadProfile",
]
