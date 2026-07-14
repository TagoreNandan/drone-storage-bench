import asyncio
from typing import Any

from benchmark.config.settings import AppSettings
from benchmark.core.database import BaseDatabaseClient
from benchmark.core.specification import (
    BenchmarkScenario,
    DatasetProfile,
    QueryProfile,
    ScenarioPriority,
    ScenarioType,
    TelemetryRecord,
)
from benchmark.workloads.query import TimeRangeQueryWorkload


class MockTestDatabaseClient(BaseDatabaseClient):
    """Mock client counting queries and supporting inject failures."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)
        self.queries_executed: list[dict[str, Any]] = []
        self.fail_on_query_index: int | None = None
        self.exception_to_raise: Exception = RuntimeError("DB query error")
        self.mock_row_count = 100

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
        return {}

    async def execute_query(self, query_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if (
            self.fail_on_query_index is not None
            and len(self.queries_executed) >= self.fail_on_query_index
        ):
            raise self.exception_to_raise
        self.queries_executed.append(params)
        return {"latency_seconds": 0.002, "row_count": self.mock_row_count}

    async def get_storage_size_bytes(self) -> int:
        return 0


# --- Query Workload Tests ---


def test_query_determinism(app_settings: AppSettings) -> None:
    """Verifies that two runs with identical seeds yield identical window start/end offsets."""
    dataset = DatasetProfile(
        simulated_drones=5,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    query_p = QueryProfile(
        query_patterns=["time_range_query"],
        time_window_seconds=10.0,
        metadata={"iteration_count": 5},
    )

    scenario = BenchmarkScenario(
        name="test_query_determinism",
        description="Query determinism verification",
        scenario_type=ScenarioType.TIME_RANGE_QUERIES,
        priority=ScenarioPriority.MEDIUM,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=100.0,
        dataset_profile=dataset,
        query_profile=query_p,
        concurrent_writers=0,
        concurrent_readers=1,
        deterministic_random_seed=42,
        metrics_to_collect=[],
    )

    client1 = MockTestDatabaseClient(app_settings)
    executor1 = TimeRangeQueryWorkload(scenario)
    result1 = asyncio.run(executor1.execute(client1))

    client2 = MockTestDatabaseClient(app_settings)
    executor2 = TimeRangeQueryWorkload(scenario)
    result2 = asyncio.run(executor2.execute(client2))

    assert result1.success is True
    assert result2.success is True

    # Assert exactly matching randomized windows
    assert len(client1.queries_executed) == len(client2.queries_executed)
    for q1, q2 in zip(client1.queries_executed, client2.queries_executed, strict=False):
        assert q1["start_time"] == q2["start_time"]
        assert q1["end_time"] == q2["end_time"]
        assert q1["vehicle_id"] == q2["vehicle_id"]


def test_query_varying_windows(app_settings: AppSettings) -> None:
    """Verifies that window selection pulls randomly from multiple configured options."""
    dataset = DatasetProfile(
        simulated_drones=3,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    # Configure multiple windows: 5s and 50s
    query_p = QueryProfile(
        query_patterns=["time_range_query"],
        time_window_seconds=5.0,
        metadata={"iteration_count": 10, "query_windows": [5.0, 50.0]},
    )

    scenario = BenchmarkScenario(
        name="test_query_varying",
        description="Varying windows verification",
        scenario_type=ScenarioType.TIME_RANGE_QUERIES,
        priority=ScenarioPriority.MEDIUM,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=100.0,
        dataset_profile=dataset,
        query_profile=query_p,
        concurrent_writers=0,
        concurrent_readers=1,
        deterministic_random_seed=42,
        metrics_to_collect=[],
    )

    client = MockTestDatabaseClient(app_settings)
    executor = TimeRangeQueryWorkload(scenario)
    result = asyncio.run(executor.execute(client))

    assert result.success is True

    # Determine window sizes used
    window_sizes = {
        round((q["end_time"] - q["start_time"]).total_seconds()) for q in client.queries_executed
    }
    # Verify both 5s and 50s windows are used
    assert 5 in window_sizes
    assert 50 in window_sizes


def test_query_workload_failure_threshold(app_settings: AppSettings) -> None:
    """Verifies that query loop aborts when failures exceed configured threshold."""
    dataset = DatasetProfile(
        simulated_drones=3,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    query_p = QueryProfile(
        query_patterns=["time_range_query"],
        time_window_seconds=5.0,
        metadata={"iteration_count": 10, "failure_threshold": 1},
    )

    scenario = BenchmarkScenario(
        name="test_query_failures",
        description="Verify failure thresholds in queries",
        scenario_type=ScenarioType.TIME_RANGE_QUERIES,
        priority=ScenarioPriority.MEDIUM,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=100.0,
        dataset_profile=dataset,
        query_profile=query_p,
        concurrent_writers=0,
        concurrent_readers=1,
        deterministic_random_seed=10,
        metrics_to_collect=[],
    )

    client = MockTestDatabaseClient(app_settings)
    # Fail on second query
    client.fail_on_query_index = 1

    executor = TimeRangeQueryWorkload(scenario)
    result = asyncio.run(executor.execute(client))

    assert result.success is False
    assert result.error_message == "DB query error"

    metrics_map = {m.metric_type.value: m.value for m in result.metrics}
    assert metrics_map["failed_queries"] is not None
    assert metrics_map["failed_queries"] >= 2.0


def test_query_workload_empty_results(app_settings: AppSettings) -> None:
    """Verifies metric calculations when query returns zero rows."""
    dataset = DatasetProfile(
        simulated_drones=2,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    query_p = QueryProfile(
        query_patterns=["time_range_query"],
        time_window_seconds=5.0,
        metadata={"iteration_count": 5},
    )

    scenario = BenchmarkScenario(
        name="test_query_empty",
        description="Verify empty query outputs formatting",
        scenario_type=ScenarioType.TIME_RANGE_QUERIES,
        priority=ScenarioPriority.MEDIUM,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=100.0,
        dataset_profile=dataset,
        query_profile=query_p,
        concurrent_writers=0,
        concurrent_readers=1,
        deterministic_random_seed=10,
        metrics_to_collect=[],
    )

    client = MockTestDatabaseClient(app_settings)
    # Set mock db row counts to zero
    client.mock_row_count = 0

    executor = TimeRangeQueryWorkload(scenario)
    result = asyncio.run(executor.execute(client))

    assert result.success is True

    metrics_map = {m.metric_type.value: m.value for m in result.metrics}
    assert metrics_map["rows_returned_average"] == 0.0
    assert metrics_map["rows_returned_maximum"] == 0.0
