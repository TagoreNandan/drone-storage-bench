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
from benchmark.workloads.query import AggregationQueryWorkload


class MockTestDatabaseClient(BaseDatabaseClient):
    """Mock client counting aggregation queries and supporting inject failures."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)
        self.queries_executed: list[dict[str, Any]] = []
        self.fail_on_query_index: int | None = None
        self.exception_to_raise: Exception = RuntimeError("DB aggregation error")
        self.mock_groups_count = 5

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
        return {"latency_seconds": 0.003, "groups_returned": self.mock_groups_count}

    async def get_storage_size_bytes(self) -> int:
        return 0


# --- Aggregation Workload Tests ---


def test_aggregation_determinism(app_settings: AppSettings) -> None:
    """Verifies that two runs with identical seeds select identical functions and windows."""
    dataset = DatasetProfile(
        simulated_drones=3,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=42,
    )
    query_p = QueryProfile(
        query_patterns=["aggregation_query"],
        time_window_seconds=10.0,
        metadata={"iteration_count": 5, "aggregation_functions": ["AVG", "MIN", "MAX"]},
    )

    scenario = BenchmarkScenario(
        name="test_agg_determinism",
        description="Verify determinism in aggregations",
        scenario_type=ScenarioType.AGGREGATION_QUERIES,
        priority=ScenarioPriority.MEDIUM,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=100.0,
        dataset_profile=dataset,
        query_profile=query_p,
        concurrent_writers=0,
        concurrent_readers=1,
        deterministic_random_seed=12,
        metrics_to_collect=[],
    )

    client1 = MockTestDatabaseClient(app_settings)
    executor1 = AggregationQueryWorkload(scenario)
    result1 = asyncio.run(executor1.execute(client1))

    client2 = MockTestDatabaseClient(app_settings)
    executor2 = AggregationQueryWorkload(scenario)
    result2 = asyncio.run(executor2.execute(client2))

    assert result1.success is True
    assert result2.success is True

    # Assert matching selected functions, windows, and vehicles
    assert len(client1.queries_executed) == len(client2.queries_executed)
    for q1, q2 in zip(client1.queries_executed, client2.queries_executed, strict=False):
        assert q1["aggregation_function"] == q2["aggregation_function"]
        assert q1["start_time"] == q2["start_time"]
        assert q1["end_time"] == q2["end_time"]
        assert q1["vehicle_id"] == q2["vehicle_id"]


def test_aggregation_multiple_functions(app_settings: AppSettings) -> None:
    """Verifies selection pulls randomly from the configured aggregation list."""
    dataset = DatasetProfile(
        simulated_drones=3,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    query_p = QueryProfile(
        query_patterns=["aggregation_query"],
        time_window_seconds=5.0,
        metadata={"iteration_count": 15, "aggregation_functions": ["MIN", "MAX", "SUM"]},
    )

    scenario = BenchmarkScenario(
        name="test_agg_multiple",
        description="Verify function range is evaluated",
        scenario_type=ScenarioType.AGGREGATION_QUERIES,
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
    executor = AggregationQueryWorkload(scenario)
    result = asyncio.run(executor.execute(client))

    assert result.success is True

    # Check aggregation functions selected
    agg_funcs = {q["aggregation_function"] for q in client.queries_executed}
    assert "MIN" in agg_funcs
    assert "MAX" in agg_funcs
    assert "SUM" in agg_funcs


def test_aggregation_failure_threshold(app_settings: AppSettings) -> None:
    """Verifies that workload halts when aggregation failures exceed limit."""
    dataset = DatasetProfile(
        simulated_drones=2,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    query_p = QueryProfile(
        query_patterns=["aggregation_query"],
        time_window_seconds=10.0,
        metadata={"iteration_count": 10, "failure_threshold": 1},
    )

    scenario = BenchmarkScenario(
        name="test_agg_failures",
        description="Verify aggregation failures thresholds",
        scenario_type=ScenarioType.AGGREGATION_QUERIES,
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
    client.fail_on_query_index = 2

    executor = AggregationQueryWorkload(scenario)
    result = asyncio.run(executor.execute(client))

    assert result.success is False
    assert result.error_message == "DB aggregation error"

    metrics_map = {m.metric_type.value: m.value for m in result.metrics}
    assert metrics_map["failed_queries"] >= 2.0


def test_aggregation_empty_groups(app_settings: AppSettings) -> None:
    """Verifies metrics when aggregations return empty result groups."""
    dataset = DatasetProfile(
        simulated_drones=2,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    query_p = QueryProfile(
        query_patterns=["aggregation_query"],
        time_window_seconds=10.0,
        metadata={"iteration_count": 5},
    )

    scenario = BenchmarkScenario(
        name="test_agg_empty",
        description="Verify empty aggregation groups are handled",
        scenario_type=ScenarioType.AGGREGATION_QUERIES,
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
    client.mock_groups_count = 0

    executor = AggregationQueryWorkload(scenario)
    result = asyncio.run(executor.execute(client))

    assert result.success is True

    metrics_map = {m.metric_type.value: m.value for m in result.metrics}
    assert metrics_map["average_groups_returned"] == 0.0
    assert metrics_map["maximum_groups_returned"] == 0.0
