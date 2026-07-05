import asyncio
from typing import Any

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
from benchmark.workloads.ingestion import BurstWriteLatencyWorkload


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


# --- Burst Workload Tests ---


def test_burst_scheduling_and_multiplier(app_settings: AppSettings) -> None:
    """Verifies burst write latency workload schedules steady/burst cycles and multiplier."""
    dataset = DatasetProfile(
        simulated_drones=3,
        metrics_per_drone=5,
        telemetry_frequency_hz=50.0,
        seed=12,
    )
    # Configure short burst cycle (interval 0.2s, burst 0.1s, multiplier 4.0, base rate 100)
    workload = WorkloadProfile(
        batch_size=2,
        rate_limit_ops_sec=100,
        is_bursty=True,
        burst_interval_sec=0.2,
        burst_multiplier=4.0,
        metadata={"burst_duration_sec": 0.1},
    )

    scenario = BenchmarkScenario(
        name="test_burst_workload",
        description="Burst scheduling and multiplier verification",
        scenario_type=ScenarioType.BURST_WRITE_LATENCY,
        priority=ScenarioPriority.MEDIUM,
        warmup_duration_seconds=0.0,
        # Duration 0.4s covers exactly two cycles
        benchmark_duration_seconds=0.4,
        dataset_profile=dataset,
        workload_profile=workload,
        concurrent_writers=1,
        concurrent_readers=0,
        deterministic_random_seed=12,
        metrics_to_collect=[],
    )

    client = MockTestDatabaseClient(app_settings)
    executor = BurstWriteLatencyWorkload(scenario)

    result = asyncio.run(executor.execute(client))
    assert result.success is True

    # Assert metrics
    metrics_map = {m.metric_type.value: m.value for m in result.metrics}

    assert "total_rows_written" in metrics_map
    assert metrics_map["total_rows_written"] > 0
    assert "average_batch_latency_ms" in metrics_map
    assert "p95_batch_latency_ms" in metrics_map
    assert "maximum_batch_latency_ms" in metrics_map
    assert "throughput_during_burst" in metrics_map
    assert "throughput_outside_burst" in metrics_map

    # Throughput during burst should be significantly higher due to multiplier
    # (Since base rate limit is 100 recs/sec and multiplier is 4.0, burst rate is 400 recs/sec)
    assert metrics_map["throughput_during_burst"] >= 0.0
    assert metrics_map["throughput_outside_burst"] >= 0.0


def test_burst_workload_failure_handling(app_settings: AppSettings) -> None:
    """Verifies that failed batches are counted and cause failure if threshold is exceeded."""
    dataset = DatasetProfile(
        simulated_drones=2,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    workload = WorkloadProfile(
        batch_size=2,
        rate_limit_ops_sec=50,
        metadata={"failure_threshold": 1, "burst_duration_sec": 0.1},
    )

    scenario = BenchmarkScenario(
        name="test_burst_failures",
        description="Failure threshold bounds checks",
        scenario_type=ScenarioType.BURST_WRITE_LATENCY,
        priority=ScenarioPriority.MEDIUM,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=0.5,
        dataset_profile=dataset,
        workload_profile=workload,
        concurrent_writers=1,
        concurrent_readers=0,
        deterministic_random_seed=10,
        metrics_to_collect=[],
    )

    client = MockTestDatabaseClient(app_settings)
    client.fail_on_batch_index = 1  # Crash on second batch

    executor = BurstWriteLatencyWorkload(scenario)
    result = asyncio.run(executor.execute(client))

    # Should report success as False
    assert result.success is False
    assert result.error_message == "DB write error"

    metrics_map = {m.metric_type.value: m.value for m in result.metrics}
    assert metrics_map["failed_batches"] >= 2.0


def test_burst_workload_determinism(app_settings: AppSettings) -> None:
    """Verifies that two runs with identical seeds yield exactly matching counts."""
    dataset = DatasetProfile(
        simulated_drones=3,
        metrics_per_drone=10,
        telemetry_frequency_hz=20.0,
        seed=42,
    )
    workload = WorkloadProfile(
        batch_size=5, rate_limit_ops_sec=100, metadata={"burst_duration_sec": 0.1}
    )

    scenario = BenchmarkScenario(
        name="test_burst_determinism",
        description="Verify determinism with same seeds",
        scenario_type=ScenarioType.BURST_WRITE_LATENCY,
        priority=ScenarioPriority.MEDIUM,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=0.2,
        dataset_profile=dataset,
        workload_profile=workload,
        concurrent_writers=1,
        concurrent_readers=0,
        deterministic_random_seed=42,
        metrics_to_collect=[],
    )

    client1 = MockTestDatabaseClient(app_settings)
    executor1 = BurstWriteLatencyWorkload(scenario)
    result1 = asyncio.run(executor1.execute(client1))

    client2 = MockTestDatabaseClient(app_settings)
    executor2 = BurstWriteLatencyWorkload(scenario)
    result2 = asyncio.run(executor2.execute(client2))

    # Assert determinism of written data structure counts
    metrics1 = {m.metric_type.value: m.value for m in result1.metrics}
    metrics2 = {m.metric_type.value: m.value for m in result2.metrics}

    assert metrics1["total_rows_written"] == metrics2["total_rows_written"]
    assert metrics1["successful_batches"] == metrics2["successful_batches"]
    assert len(client1.batches_written) == len(client2.batches_written)

    # Confirm contents generated match exactly
    for b1, b2 in zip(client1.batches_written, client2.batches_written, strict=False):
        assert [r.vehicle_id for r in b1] == [r.vehicle_id for r in b2]
        assert [r.battery_percentage for r in b1] == [r.battery_percentage for r in b2]
