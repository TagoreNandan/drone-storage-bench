import pytest
from pydantic import ValidationError

from benchmark.core.specification import (
    BenchmarkScenario,
    BenchmarkSuite,
    DatasetProfile,
    MetricType,
    QueryProfile,
    ScenarioPriority,
    ScenarioType,
    WorkloadProfile,
)


def test_dataset_profile_valid() -> None:
    """Verifies that a valid DatasetProfile validates and is immutable."""
    profile = DatasetProfile(
        simulated_drones=100,
        metrics_per_drone=15,
        telemetry_frequency_hz=50.0,
        seed=42,
        total_records=10000,
    )
    assert profile.simulated_drones == 100
    assert profile.seed == 42

    with pytest.raises(ValidationError):
        # Mutating frozen model raises ValidationError
        profile.simulated_drones = 200  # type: ignore


def test_workload_profile_validation() -> None:
    """Verifies that negative constraints on WorkloadProfile raise ValidationError."""
    with pytest.raises(ValidationError):
        WorkloadProfile(batch_size=-10)


def test_benchmark_scenario_validation_rules() -> None:
    """Verifies cross-field validators on BenchmarkScenario."""
    dataset = DatasetProfile(
        simulated_drones=10,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=123,
    )

    # 1. Invalid: concurrent writers > 0 but workload_profile is None
    with pytest.raises(ValidationError) as exc_info:
        BenchmarkScenario(
            name="test_scenario",
            description="A test scenario",
            scenario_type=ScenarioType.WRITE_THROUGHPUT,
            priority=ScenarioPriority.HIGH,
            warmup_duration_seconds=5.0,
            benchmark_duration_seconds=10.0,
            dataset_profile=dataset,
            workload_profile=None,
            concurrent_writers=2,
            concurrent_readers=0,
            deterministic_random_seed=42,
            metrics_to_collect=[MetricType.WRITE_THROUGHPUT],
        )
    assert "Workload profile must be configured if concurrent writers > 0" in str(exc_info.value)

    # 2. Invalid: concurrent readers > 0 but query_profile is None
    with pytest.raises(ValidationError) as exc_info:
        BenchmarkScenario(
            name="test_scenario",
            description="A test scenario",
            scenario_type=ScenarioType.TIME_RANGE_QUERIES,
            priority=ScenarioPriority.HIGH,
            warmup_duration_seconds=5.0,
            benchmark_duration_seconds=10.0,
            dataset_profile=dataset,
            query_profile=None,
            concurrent_writers=0,
            concurrent_readers=5,
            deterministic_random_seed=42,
            metrics_to_collect=[MetricType.READ_THROUGHPUT],
        )
    assert "Query profile must be configured if concurrent readers > 0" in str(exc_info.value)

    # 3. Invalid: JOIN_EVALUATION scenario without enable_joins
    query_p = QueryProfile(
        query_patterns=["some_query"],
        time_window_seconds=60.0,
        enable_joins=False,  # Should be True for JOIN_EVALUATION
    )
    with pytest.raises(ValidationError) as exc_info:
        BenchmarkScenario(
            name="test_scenario",
            description="A test scenario",
            scenario_type=ScenarioType.JOIN_EVALUATION,
            priority=ScenarioPriority.HIGH,
            warmup_duration_seconds=5.0,
            benchmark_duration_seconds=10.0,
            dataset_profile=dataset,
            query_profile=query_p,
            concurrent_writers=0,
            concurrent_readers=2,
            deterministic_random_seed=42,
            metrics_to_collect=[MetricType.JOIN_LATENCY_MS],
        )
    assert "Query profile enable_joins must be True for JOIN_EVALUATION" in str(exc_info.value)


def test_benchmark_suite_unique_names() -> None:
    """Verifies that BenchmarkSuite enforces unique scenario names."""
    dataset = DatasetProfile(
        simulated_drones=10,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=123,
    )
    workload = WorkloadProfile(batch_size=100)

    scenario_1 = BenchmarkScenario(
        name="duplicate_name",
        description="First description",
        scenario_type=ScenarioType.WRITE_THROUGHPUT,
        warmup_duration_seconds=1.0,
        benchmark_duration_seconds=5.0,
        dataset_profile=dataset,
        workload_profile=workload,
        concurrent_writers=1,
        concurrent_readers=0,
        deterministic_random_seed=1,
        metrics_to_collect=[MetricType.WRITE_THROUGHPUT],
    )

    scenario_2 = BenchmarkScenario(
        name="duplicate_name",  # Duplicate name
        description="Second description",
        scenario_type=ScenarioType.WRITE_THROUGHPUT,
        warmup_duration_seconds=1.0,
        benchmark_duration_seconds=5.0,
        dataset_profile=dataset,
        workload_profile=workload,
        concurrent_writers=1,
        concurrent_readers=0,
        deterministic_random_seed=2,
        metrics_to_collect=[MetricType.WRITE_THROUGHPUT],
    )

    with pytest.raises(ValidationError) as exc_info:
        BenchmarkSuite(
            name="invalid_suite",
            description="A suite with duplicate names",
            global_seed=42,
            scenarios=[scenario_1, scenario_2],
        )
    assert "All scenario names within a BenchmarkSuite must be unique" in str(exc_info.value)


def test_scenario_types_coverage() -> None:
    """Verifies that all 7 required database-agnostic scenarios are configured."""
    scenarios_list = [t.value for t in ScenarioType]
    required = {
        "write_throughput",
        "burst_write_latency",
        "time_range_queries",
        "aggregation_queries",
        "historical_replay",
        "compression_evaluation",
        "join_evaluation",
    }
    for req in required:
        assert req in scenarios_list
