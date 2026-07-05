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
from benchmark.workloads.query import JoinEvaluationWorkload


class MockTestDatabaseClient(BaseDatabaseClient):
    """Mock client for JOIN queries supporting native vs app merge paths and inject failures."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)
        self.queries_executed: list[dict[str, Any]] = []
        self.fail_on_query_index: int | None = None
        self.exception_to_raise: Exception = RuntimeError("DB JOIN query error")
        self.mock_strategy = "native"
        self.mock_merge_duration = 0.0
        self.mock_row_count = 200

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
        return {
            "latency_seconds": 0.005,
            "row_count": self.mock_row_count,
            "join_strategy": self.mock_strategy,
            "merge_duration_ms": self.mock_merge_duration,
        }

    async def get_storage_size_bytes(self) -> int:
        return 0


# --- JOIN Workload Tests ---


def test_join_native_path(app_settings: AppSettings) -> None:
    """Verifies Native SQL JOIN path metrics calculations."""
    dataset = DatasetProfile(
        simulated_drones=3,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    query_p = QueryProfile(
        query_patterns=["join_query"],
        time_window_seconds=10.0,
        enable_joins=True,
        metadata={"iteration_count": 3, "query_windows": [10.0]},
    )

    scenario = BenchmarkScenario(
        name="test_join_native",
        description="Verify native JOIN execution model",
        scenario_type=ScenarioType.JOIN_EVALUATION,
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
    client.mock_strategy = "native"
    client.mock_merge_duration = 0.0

    executor = JoinEvaluationWorkload(scenario)
    result = asyncio.run(executor.execute(client))

    assert result.success is True
    metrics_map = {m.metric_type.value: m.value for m in result.metrics}

    # Strategy val: 1.0 (native)
    assert metrics_map["join_strategy"] == 1.0
    assert metrics_map["merge_duration_ms"] == 0.0
    assert metrics_map["rows_returned"] == 600.0


def test_join_app_merge_path(app_settings: AppSettings) -> None:
    """Verifies Application-layer merge path metrics calculations."""
    dataset = DatasetProfile(
        simulated_drones=3,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    query_p = QueryProfile(
        query_patterns=["join_query"],
        time_window_seconds=10.0,
        enable_joins=True,
        metadata={"iteration_count": 3},
    )

    scenario = BenchmarkScenario(
        name="test_join_app",
        description="Verify app merge execution model",
        scenario_type=ScenarioType.JOIN_EVALUATION,
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
    client.mock_strategy = "application_merge"
    client.mock_merge_duration = 1.25

    executor = JoinEvaluationWorkload(scenario)
    result = asyncio.run(executor.execute(client))

    assert result.success is True
    metrics_map = {m.metric_type.value: m.value for m in result.metrics}

    # Strategy val: 2.0 (application_merge)
    assert metrics_map["join_strategy"] == 2.0
    assert metrics_map["merge_duration_ms"] == 1.25
    assert metrics_map["rows_returned"] == 600.0


def test_join_determinism(app_settings: AppSettings) -> None:
    """Verifies that two runs with identical seeds yield identical parameters."""
    dataset = DatasetProfile(
        simulated_drones=3,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    query_p = QueryProfile(
        query_patterns=["join_query"],
        time_window_seconds=10.0,
        enable_joins=True,
        metadata={"iteration_count": 5},
    )

    scenario = BenchmarkScenario(
        name="test_join_determinism",
        description="Verify seed determinism",
        scenario_type=ScenarioType.JOIN_EVALUATION,
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
    executor1 = JoinEvaluationWorkload(scenario)
    result1 = asyncio.run(executor1.execute(client1))

    client2 = MockTestDatabaseClient(app_settings)
    executor2 = JoinEvaluationWorkload(scenario)
    result2 = asyncio.run(executor2.execute(client2))

    assert result1.success is True
    assert result2.success is True

    assert len(client1.queries_executed) == len(client2.queries_executed)
    for q1, q2 in zip(client1.queries_executed, client2.queries_executed, strict=False):
        assert q1["start_time"] == q2["start_time"]
        assert q1["end_time"] == q2["end_time"]
        assert q1["vehicle_id"] == q2["vehicle_id"]


def test_join_failure_handling(app_settings: AppSettings) -> None:
    """Verifies that failures count and stop runs only when threshold exceeded."""
    dataset = DatasetProfile(
        simulated_drones=2,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    query_p = QueryProfile(
        query_patterns=["join_query"],
        time_window_seconds=10.0,
        enable_joins=True,
        metadata={"iteration_count": 5, "failure_threshold": 1},
    )

    scenario = BenchmarkScenario(
        name="test_join_failures",
        description="Verify failure thresholds",
        scenario_type=ScenarioType.JOIN_EVALUATION,
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
    client.fail_on_query_index = 1  # Fail on second query

    executor = JoinEvaluationWorkload(scenario)
    result = asyncio.run(executor.execute(client))

    assert result.success is False
    assert result.error_message == "DB JOIN query error"

    metrics_map = {m.metric_type.value: m.value for m in result.metrics}
    assert metrics_map["failed_queries"] >= 2.0
