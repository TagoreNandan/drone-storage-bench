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
from benchmark.workloads.query import HistoricalReplayWorkload


class MockTestDatabaseClient(BaseDatabaseClient):
    """Mock client counting replay queries and supporting inject failures."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)
        self.queries_executed: list[dict[str, Any]] = []
        self.fail_on_query_index: int | None = None
        self.exception_to_raise: Exception = RuntimeError("DB replay query error")
        self.mock_row_count = 500

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
        return {"latency_seconds": 0.010, "row_count": self.mock_row_count}

    async def get_storage_size_bytes(self) -> int:
        return 0


# --- Replay Workload Tests ---


def test_replay_determinism_and_sorting(app_settings: AppSettings) -> None:
    """Verifies that two runs with identical seeds select identical missions and sort order."""
    dataset = DatasetProfile(
        simulated_drones=5,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=42,
    )
    query_p = QueryProfile(
        query_patterns=["historical_replay_query"],
        time_window_seconds=100.0,
        metadata={"iteration_count": 5},
    )

    scenario = BenchmarkScenario(
        name="test_replay_determinism",
        description="Verify replay seed determinism",
        scenario_type=ScenarioType.HISTORICAL_REPLAY,
        priority=ScenarioPriority.MEDIUM,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=100.0,
        dataset_profile=dataset,
        query_profile=query_p,
        concurrent_writers=0,
        concurrent_readers=1,
        deterministic_random_seed=15,
        metrics_to_collect=[],
    )

    client1 = MockTestDatabaseClient(app_settings)
    executor1 = HistoricalReplayWorkload(scenario)
    result1 = asyncio.run(executor1.execute(client1))

    client2 = MockTestDatabaseClient(app_settings)
    executor2 = HistoricalReplayWorkload(scenario)
    result2 = asyncio.run(executor2.execute(client2))

    assert result1.success is True
    assert result2.success is True

    # Assert exactly matching randomized missions and sorting
    assert len(client1.queries_executed) == len(client2.queries_executed)
    for q1, q2 in zip(client1.queries_executed, client2.queries_executed, strict=False):
        assert q1["mission_id"] == q2["mission_id"]
        assert q1["sort_order"] == "asc"  # Chronological ordering requested
        assert q2["sort_order"] == "asc"


def test_replay_throughput_calculations(app_settings: AppSettings) -> None:
    """Verifies that throughput rows/sec and latencies match simulated mocks."""
    dataset = DatasetProfile(
        simulated_drones=3,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    query_p = QueryProfile(
        query_patterns=["historical_replay_query"],
        time_window_seconds=50.0,
        metadata={"iteration_count": 3, "mission_id": "mission_0001"},
    )

    scenario = BenchmarkScenario(
        name="test_replay_throughput",
        description="Verify calculations formatting",
        scenario_type=ScenarioType.HISTORICAL_REPLAY,
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
    client.mock_row_count = 1000  # 1000 rows returned per query

    executor = HistoricalReplayWorkload(scenario)
    result = asyncio.run(executor.execute(client))

    assert result.success is True

    metrics_map = {m.metric_type.value: m.value for m in result.metrics}

    assert metrics_map["total_replays"] == 3.0
    assert metrics_map["successful_replays"] == 3.0
    assert metrics_map["rows_returned"] == 3000.0
    assert metrics_map["replay_throughput_rows_per_second"] is not None
    assert metrics_map["replay_throughput_rows_per_second"] > 0.0
    assert "average_latency_ms" in metrics_map
    assert "p99_latency_ms" in metrics_map


def test_replay_empty_mission(app_settings: AppSettings) -> None:
    """Verifies throughput outputs when replaying empty/non-existent mission."""
    dataset = DatasetProfile(
        simulated_drones=2,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    query_p = QueryProfile(
        query_patterns=["historical_replay_query"],
        time_window_seconds=10.0,
        metadata={"iteration_count": 3},
    )

    scenario = BenchmarkScenario(
        name="test_replay_empty",
        description="Verify empty mission handles cleanly",
        scenario_type=ScenarioType.HISTORICAL_REPLAY,
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
    client.mock_row_count = 0  # Zero rows matching mission

    executor = HistoricalReplayWorkload(scenario)
    result = asyncio.run(executor.execute(client))

    assert result.success is True

    metrics_map = {m.metric_type.value: m.value for m in result.metrics}
    assert metrics_map["rows_returned"] == 0.0
    assert metrics_map["replay_throughput_rows_per_second"] == 0.0


def test_replay_failure_handling(app_settings: AppSettings) -> None:
    """Verifies that failures count and cause runs to halt when threshold is exceeded."""
    dataset = DatasetProfile(
        simulated_drones=2,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    query_p = QueryProfile(
        query_patterns=["historical_replay_query"],
        time_window_seconds=10.0,
        metadata={"iteration_count": 5, "failure_threshold": 1},
    )

    scenario = BenchmarkScenario(
        name="test_replay_failures",
        description="Verify failure thresholds",
        scenario_type=ScenarioType.HISTORICAL_REPLAY,
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
    client.fail_on_query_index = 1  # Crash on second replay

    executor = HistoricalReplayWorkload(scenario)
    result = asyncio.run(executor.execute(client))

    assert result.success is False
    assert result.error_message == "DB replay query error"

    metrics_map = {m.metric_type.value: m.value for m in result.metrics}
    assert metrics_map["failed_replays"] is not None
    assert metrics_map["failed_replays"] >= 2.0
