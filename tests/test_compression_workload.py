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
from benchmark.workloads.compression import CompressionEvaluationWorkload


class MockTestDatabaseClient(BaseDatabaseClient):
    """Mock client counting compression calls and supporting inject failures."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)
        self.compress_called = 0
        self.total_row_count_called = 0
        self.fail_on_compress = False
        self.fail_on_disk_size = False
        self.fail_on_row_count = False
        self.mock_storage_size = 5000000
        self.mock_row_count = 100000

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
        if query_name == "compress":
            self.compress_called += 1
            if self.fail_on_compress:
                raise RuntimeError("Compress query error")
            return {"status": "success"}
        elif query_name == "total_row_count":
            self.total_row_count_called += 1
            if self.fail_on_row_count:
                raise RuntimeError("Row count query error")
            return {"row_count": self.mock_row_count}
        return {}

    async def get_storage_size_bytes(self) -> int:
        if self.fail_on_disk_size:
            raise RuntimeError("Disk size retrieval error")
        return self.mock_storage_size


# --- Compression Workload Tests ---


def test_compression_ratio_calculations(app_settings: AppSettings) -> None:
    """Verifies that compression ratios and percentages are correctly computed."""
    dataset = DatasetProfile(
        simulated_drones=5,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    query_p = QueryProfile(
        query_patterns=["compress"],
        time_window_seconds=10.0,
        metadata={"logical_dataset_size_bytes": 10000000},  # Explicit logical size
    )

    scenario = BenchmarkScenario(
        name="test_compression",
        description="Verify compression workload",
        scenario_type=ScenarioType.COMPRESSION_EVALUATION,
        priority=ScenarioPriority.MEDIUM,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=100.0,
        dataset_profile=dataset,
        query_profile=query_p,
        concurrent_writers=0,
        concurrent_readers=0,
        deterministic_random_seed=42,
        metrics_to_collect=[],
    )

    client = MockTestDatabaseClient(app_settings)
    # Set physical compressed size to 2MB (2000000 bytes)
    client.mock_storage_size = 2000000

    executor = CompressionEvaluationWorkload(scenario)
    result = asyncio.run(executor.execute(client))

    assert result.success is True
    assert client.compress_called == 1

    metrics_map = {m.metric_type.value: m.value for m in result.metrics}

    # Logical size: 10,000,000, physical size: 2,000,000
    # Ratio = 10000000 / 2000000 = 5.0
    # Percentage = (1.0 - 0.2) * 100 = 80.0
    assert metrics_map["logical_dataset_size_bytes"] == 10000000.0
    assert metrics_map["physical_storage_size_bytes"] == 2000000.0
    assert metrics_map["compression_ratio"] == 5.0
    assert metrics_map["compression_percentage"] == 80.0
    assert "compression_duration_ms" in metrics_map


def test_compression_dynamic_size_calculation(app_settings: AppSettings) -> None:
    """Verifies fallback dynamic logical size calculation using row count querying."""
    dataset = DatasetProfile(
        simulated_drones=10,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    query_p = QueryProfile(
        query_patterns=["compress"],
        time_window_seconds=10.0,
        metadata={},  # No logical size configured, falls back to total_rows * 128
    )

    scenario = BenchmarkScenario(
        name="test_compression_dynamic",
        description="Verify dynamic logical size",
        scenario_type=ScenarioType.COMPRESSION_EVALUATION,
        priority=ScenarioPriority.MEDIUM,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=100.0,
        dataset_profile=dataset,
        query_profile=query_p,
        concurrent_writers=0,
        concurrent_readers=0,
        deterministic_random_seed=42,
        metrics_to_collect=[],
    )

    client = MockTestDatabaseClient(app_settings)
    client.mock_row_count = 50000
    client.mock_storage_size = 3200000

    executor = CompressionEvaluationWorkload(scenario)
    result = asyncio.run(executor.execute(client))

    assert result.success is True
    assert client.total_row_count_called == 1

    metrics_map = {m.metric_type.value: m.value for m in result.metrics}

    # Logical size: 50,000 * 128 = 6,400,000
    # Physical size: 3,200,000
    # Ratio = 6400000 / 3200000 = 2.0
    # Percentage = 50.0
    assert metrics_map["logical_dataset_size_bytes"] == 6400000.0
    assert metrics_map["physical_storage_size_bytes"] == 3200000.0
    assert metrics_map["compression_ratio"] == 2.0
    assert metrics_map["compression_percentage"] == 50.0


def test_compression_zero_byte_edge_cases(app_settings: AppSettings) -> None:
    """Verifies that physical sizes of zero are gracefully processed without ZeroDivisionError."""
    dataset = DatasetProfile(
        simulated_drones=2,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    query_p = QueryProfile(
        query_patterns=["compress"],
        time_window_seconds=10.0,
        metadata={"logical_dataset_size_bytes": 0},
    )

    scenario = BenchmarkScenario(
        name="test_compression_zeros",
        description="Verify zero division error avoidance",
        scenario_type=ScenarioType.COMPRESSION_EVALUATION,
        priority=ScenarioPriority.MEDIUM,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=10.0,
        dataset_profile=dataset,
        query_profile=query_p,
        concurrent_writers=0,
        concurrent_readers=0,
        deterministic_random_seed=10,
        metrics_to_collect=[],
    )

    client = MockTestDatabaseClient(app_settings)
    client.mock_storage_size = 0
    client.mock_row_count = 0

    executor = CompressionEvaluationWorkload(scenario)
    result = asyncio.run(executor.execute(client))

    assert result.success is True

    metrics_map = {m.metric_type.value: m.value for m in result.metrics}
    assert metrics_map["logical_dataset_size_bytes"] == 0.0
    assert metrics_map["physical_storage_size_bytes"] == 0.0
    assert metrics_map["compression_ratio"] == 1.0
    assert metrics_map["compression_percentage"] == 0.0


def test_compression_failure_handling(app_settings: AppSettings) -> None:
    """Verifies adapter query execution errors report success as False."""
    dataset = DatasetProfile(
        simulated_drones=2,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    query_p = QueryProfile(
        query_patterns=["compress"],
        time_window_seconds=10.0,
    )

    scenario = BenchmarkScenario(
        name="test_compression_fails",
        description="Verify failure states",
        scenario_type=ScenarioType.COMPRESSION_EVALUATION,
        priority=ScenarioPriority.MEDIUM,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=10.0,
        dataset_profile=dataset,
        query_profile=query_p,
        concurrent_writers=0,
        concurrent_readers=0,
        deterministic_random_seed=10,
        metrics_to_collect=[],
    )

    client = MockTestDatabaseClient(app_settings)
    # Fail compress query
    client.fail_on_compress = True

    executor = CompressionEvaluationWorkload(scenario)
    result = asyncio.run(executor.execute(client))

    assert result.success is False
    assert result.error_message is not None
    assert "Compress query error" in result.error_message
