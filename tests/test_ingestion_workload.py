import asyncio
import time
from typing import Any

import pytest

from benchmark.config.settings import AppSettings
from benchmark.core.database import BaseDatabaseClient
from benchmark.core.specification import (
    BenchmarkScenario,
    DatasetProfile,
    ScenarioPriority,
    ScenarioType,
    TelemetryRecord,
    WorkloadProfile,
)
from benchmark.utils.batcher import batch_generator
from benchmark.workloads.ingestion import WriteThroughputWorkload, calculate_percentile


class MockTestDatabaseClient(BaseDatabaseClient):
    """Mock client counting writes and supporting inject failures."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)
        self.batches_written: list[list[TelemetryRecord]] = []
        self.fail_on_batch_index: int | None = None
        self.exception_to_raise: Exception = RuntimeError("DB write error")

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def is_healthy(self) -> bool:
        return True

    async def setup_schema(self) -> None:
        pass

    async def cleanup_data(self) -> None:
        pass

    async def write_telemetry_batch(self, batch: list[TelemetryRecord]) -> dict[str, Any]:
        if (
            self.fail_on_batch_index is not None
            and len(self.batches_written) >= self.fail_on_batch_index
        ):
            raise self.exception_to_raise
        self.batches_written.append(batch)
        return {"latency_seconds": 0.005, "success_count": len(batch), "error_count": 0}

    async def execute_query(self, query_name: str, params: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def get_storage_size_bytes(self) -> int:
        return 0


# --- 1. Batcher Tests ---


def test_batch_generator_basic() -> None:
    """Verifies that the batcher aggregates records correctly and flushes remainder."""
    items = [1, 2, 3, 4, 5, 6, 7]
    batches = list(batch_generator(iter(items), batch_size=3))

    assert len(batches) == 3
    assert batches[0] == [1, 2, 3]
    assert batches[1] == [4, 5, 6]
    assert batches[2] == [7]  # Partial final flush


def test_batch_generator_invalid_size() -> None:
    """Verifies that batch size of less than 1 raises ValueError."""
    with pytest.raises(ValueError, match="batch_size must be at least 1"):
        next(batch_generator(iter([1, 2]), batch_size=0))


def test_batch_generator_empty() -> None:
    """Verifies that batch generator yields nothing for empty inputs."""
    batches: list[list[Any]] = list(batch_generator(iter([]), batch_size=5))
    assert len(batches) == 0


# --- 2. Percentiles Math Tests ---


def test_percentiles_calculation() -> None:
    """Verifies pure Python percentile calculations using linear interpolation."""
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert calculate_percentile(values, 50.0) == 30.0
    assert calculate_percentile(values, 90.0) == 46.0  # Interpolated

    assert calculate_percentile([], 95.0) == 0.0


# --- 3. Ingestion Workload Tests ---


def test_workload_duration_respected(app_settings: AppSettings) -> None:
    """Verifies that the workload stops executing once benchmark duration expires."""
    dataset = DatasetProfile(
        simulated_drones=5,
        metrics_per_drone=5,
        telemetry_frequency_hz=50.0,
        seed=42,
    )
    workload = WorkloadProfile(batch_size=10)

    # Set duration short (0.2 seconds) to guarantee clean stop without running long
    scenario = BenchmarkScenario(
        name="test_duration_write",
        description="Duration constraint check",
        scenario_type=ScenarioType.WRITE_THROUGHPUT,
        priority=ScenarioPriority.LOW,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=0.2,
        dataset_profile=dataset,
        workload_profile=workload,
        concurrent_writers=1,
        concurrent_readers=0,
        deterministic_random_seed=42,
        metrics_to_collect=[],
    )

    client = MockTestDatabaseClient(app_settings)
    executor = WriteThroughputWorkload(scenario)

    start_t = time.perf_counter()
    result = asyncio.run(executor.execute(client))
    elapsed_t = time.perf_counter() - start_t

    assert result.success is True
    # The elapsed time should be very close to the benchmark duration setting (under 0.5s)
    assert elapsed_t < 1.0


def test_workload_metrics_calculations(app_settings: AppSettings) -> None:
    """Verifies that write workload returns expected compiled metrics."""
    dataset = DatasetProfile(
        simulated_drones=3,
        metrics_per_drone=5,
        telemetry_frequency_hz=25.0,
        seed=10,
    )
    workload = WorkloadProfile(batch_size=5)

    scenario = BenchmarkScenario(
        name="test_metrics_write",
        description="Write throughput metrics",
        scenario_type=ScenarioType.WRITE_THROUGHPUT,
        priority=ScenarioPriority.LOW,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=0.1,
        dataset_profile=dataset,
        workload_profile=workload,
        concurrent_writers=1,
        concurrent_readers=0,
        deterministic_random_seed=10,
        metrics_to_collect=[],
    )

    client = MockTestDatabaseClient(app_settings)
    executor = WriteThroughputWorkload(scenario)

    result = asyncio.run(executor.execute(client))
    assert result.success is True

    # Assert metric entries presence
    metrics_map = {m.metric_type.value: m.value for m in result.metrics}

    assert "total_rows_written" in metrics_map
    assert metrics_map["total_rows_written"] is not None
    assert metrics_map["total_rows_written"] > 0
    assert "successful_batches" in metrics_map
    assert metrics_map["successful_batches"] is not None
    assert metrics_map["successful_batches"] > 0
    assert "failed_batches" in metrics_map
    assert metrics_map["failed_batches"] == 0.0
    assert "p50_batch_latency_ms" in metrics_map
    assert "rows_per_second" in metrics_map
    assert metrics_map["rows_per_second"] is not None
    assert metrics_map["rows_per_second"] > 0.0


def test_workload_failure_threshold(app_settings: AppSettings) -> None:
    """Verifies failure handling limits abort runs when threshold exceeded."""
    dataset = DatasetProfile(
        simulated_drones=2,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    # Set metadata failure threshold to 2
    workload = WorkloadProfile(batch_size=2, metadata={"failure_threshold": 2})

    scenario = BenchmarkScenario(
        name="test_failures_write",
        description="Write throughput failure threshold checks",
        scenario_type=ScenarioType.WRITE_THROUGHPUT,
        priority=ScenarioPriority.LOW,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=1.0,
        dataset_profile=dataset,
        workload_profile=workload,
        concurrent_writers=1,
        concurrent_readers=0,
        deterministic_random_seed=10,
        metrics_to_collect=[],
    )

    client = MockTestDatabaseClient(app_settings)
    # Trigger db errors on every batch after index 1
    client.fail_on_batch_index = 1

    executor = WriteThroughputWorkload(scenario)
    result = asyncio.run(executor.execute(client))

    # Should abort and report success as False
    assert result.success is False
    assert result.error_message == "DB write error"

    metrics_map = {m.metric_type.value: m.value for m in result.metrics}
    assert metrics_map["failed_batches"] is not None
    assert metrics_map["failed_batches"] > 2
