from datetime import UTC, datetime

from benchmark.core.specification import (
    BenchmarkMetric,
    BenchmarkResult,
    BenchmarkScenario,
    BenchmarkSuite,
    DatasetProfile,
    MetricType,
    MetricUnit,
    ScenarioPriority,
    ScenarioType,
)
from benchmark.scoring.engine import ScoringEngine


def test_scoring_normalization_and_weighting() -> None:
    """Verifies min-max normalization, direction rules, and weight mapping."""
    dataset = DatasetProfile(
        simulated_drones=5,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    scenario_write = BenchmarkScenario(
        name="write_scenario",
        description="Sustained write throughput",
        scenario_type=ScenarioType.WRITE_THROUGHPUT,
        priority=ScenarioPriority.HIGH,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=10.0,
        dataset_profile=dataset,
        concurrent_writers=0,
        concurrent_readers=0,
        deterministic_random_seed=42,
        metrics_to_collect=[],
    )
    scenario_latency = BenchmarkScenario(
        name="latency_scenario",
        description="Time range query latency",
        scenario_type=ScenarioType.TIME_RANGE_QUERIES,
        priority=ScenarioPriority.MEDIUM,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=10.0,
        dataset_profile=dataset,
        concurrent_writers=0,
        concurrent_readers=0,
        deterministic_random_seed=42,
        metrics_to_collect=[],
    )

    suite = BenchmarkSuite(
        name="test_suite",
        description="Test suite description",
        global_seed=42,
        scenarios=[scenario_write, scenario_latency],
    )

    # 1. Ingestion: high rows_per_second is better (dbA: 150000, dbB: 50000, dbC: 100000)
    # 2. Latency: lower average_latency_ms is better (dbA: 10.0, dbB: 20.0, dbC: 15.0)
    results = [
        # dbA
        BenchmarkResult(
            database_name="dbA",
            scenario_name="write_scenario",
            scenario_type=ScenarioType.WRITE_THROUGHPUT,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            metrics=[
                BenchmarkMetric(
                    metric_type=MetricType.ROWS_PER_SECOND,
                    value=150000.0,
                    unit=MetricUnit.COUNT,
                )
            ],
            success=True,
        ),
        BenchmarkResult(
            database_name="dbA",
            scenario_name="latency_scenario",
            scenario_type=ScenarioType.TIME_RANGE_QUERIES,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            metrics=[
                BenchmarkMetric(
                    metric_type=MetricType.AVERAGE_LATENCY_MS,
                    value=10.0,
                    unit=MetricUnit.MILLISECONDS,
                )
            ],
            success=True,
        ),
        # dbB
        BenchmarkResult(
            database_name="dbB",
            scenario_name="write_scenario",
            scenario_type=ScenarioType.WRITE_THROUGHPUT,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            metrics=[
                BenchmarkMetric(
                    metric_type=MetricType.ROWS_PER_SECOND,
                    value=50000.0,
                    unit=MetricUnit.COUNT,
                )
            ],
            success=True,
        ),
        BenchmarkResult(
            database_name="dbB",
            scenario_name="latency_scenario",
            scenario_type=ScenarioType.TIME_RANGE_QUERIES,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            metrics=[
                BenchmarkMetric(
                    metric_type=MetricType.AVERAGE_LATENCY_MS,
                    value=20.0,
                    unit=MetricUnit.MILLISECONDS,
                )
            ],
            success=True,
        ),
        # dbC
        BenchmarkResult(
            database_name="dbC",
            scenario_name="write_scenario",
            scenario_type=ScenarioType.WRITE_THROUGHPUT,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            metrics=[
                BenchmarkMetric(
                    metric_type=MetricType.ROWS_PER_SECOND,
                    value=100000.0,
                    unit=MetricUnit.COUNT,
                )
            ],
            success=True,
        ),
        BenchmarkResult(
            database_name="dbC",
            scenario_name="latency_scenario",
            scenario_type=ScenarioType.TIME_RANGE_QUERIES,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            metrics=[
                BenchmarkMetric(
                    metric_type=MetricType.AVERAGE_LATENCY_MS,
                    value=15.0,
                    unit=MetricUnit.MILLISECONDS,
                )
            ],
            success=True,
        ),
    ]

    # Weights: sustained_write_throughput: 0.6, time_range_queries: 0.4. Sum = 1.0.
    weights = {
        "sustained_write_throughput": 0.6,
        "time_range_queries": 0.4,
    }
    engine = ScoringEngine(weights=weights)
    report = engine.score(results, suite)

    # Convert results list to mapping for easy checking
    db_map = {item.database: item for item in report.database_scores}

    # Expected Normalization write:
    # dbA: 150000 (max) -> 100.0
    # dbB: 50000 (min) -> 0.0
    # dbC: 100000 (mid) -> 50.0
    # Expected Normalization latency (lower is better):
    # dbA: 10.0 (min) -> 100.0
    # dbB: 20.0 (max) -> 0.0
    # dbC: 15.0 (mid) -> 50.0

    # Overall:
    # dbA: 100.0 * 0.6 + 100.0 * 0.4 = 100.0
    # dbB: 0.0 * 0.6 + 0.0 * 0.4 = 0.0
    # dbC: 50.0 * 0.6 + 50.0 * 0.4 = 50.0

    assert db_map["dbA"].overall_score == 100.0
    assert db_map["dbA"].rank == 1

    assert db_map["dbC"].overall_score == 50.0
    assert db_map["dbC"].rank == 2

    assert db_map["dbB"].overall_score == 0.0
    assert db_map["dbB"].rank == 3


def test_scoring_ties_and_deterministic_order() -> None:
    """Verifies tie handling and deterministic sorting by database name."""
    dataset = DatasetProfile(
        simulated_drones=5,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    scenario = BenchmarkScenario(
        name="write_scenario",
        description="Sustained write throughput",
        scenario_type=ScenarioType.WRITE_THROUGHPUT,
        priority=ScenarioPriority.HIGH,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=10.0,
        dataset_profile=dataset,
        concurrent_writers=0,
        concurrent_readers=0,
        deterministic_random_seed=42,
        metrics_to_collect=[],
    )
    suite = BenchmarkSuite(
        name="test_suite",
        description="Test suite description",
        global_seed=42,
        scenarios=[scenario],
    )

    results = [
        # dbB and dbA have identical metric values (ties)
        BenchmarkResult(
            database_name="dbB",
            scenario_name="write_scenario",
            scenario_type=ScenarioType.WRITE_THROUGHPUT,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            metrics=[
                BenchmarkMetric(
                    metric_type=MetricType.ROWS_PER_SECOND,
                    value=100.0,
                    unit=MetricUnit.COUNT,
                )
            ],
            success=True,
        ),
        BenchmarkResult(
            database_name="dbA",
            scenario_name="write_scenario",
            scenario_type=ScenarioType.WRITE_THROUGHPUT,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            metrics=[
                BenchmarkMetric(
                    metric_type=MetricType.ROWS_PER_SECOND,
                    value=100.0,
                    unit=MetricUnit.COUNT,
                )
            ],
            success=True,
        ),
        # dbC has worse performance
        BenchmarkResult(
            database_name="dbC",
            scenario_name="write_scenario",
            scenario_type=ScenarioType.WRITE_THROUGHPUT,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            metrics=[
                BenchmarkMetric(
                    metric_type=MetricType.ROWS_PER_SECOND,
                    value=50.0,
                    unit=MetricUnit.COUNT,
                )
            ],
            success=True,
        ),
    ]

    engine = ScoringEngine()
    report = engine.score(results, suite)

    # Deterministic alphabetical ordering on tie: dbA should be ranked before dbB
    assert report.database_scores[0].database == "dbA"
    assert report.database_scores[0].overall_score == 100.0
    assert report.database_scores[0].rank == 1

    assert report.database_scores[1].database == "dbB"
    assert report.database_scores[1].overall_score == 100.0
    assert report.database_scores[1].rank == 1

    assert report.database_scores[2].database == "dbC"
    assert report.database_scores[2].overall_score == 0.0
    assert report.database_scores[2].rank == 3


def test_scoring_missing_results_and_failures() -> None:
    """Verifies that missing or failed results yield zero scenario score and compute correctly."""
    dataset = DatasetProfile(
        simulated_drones=5,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=10,
    )
    scenario_write = BenchmarkScenario(
        name="write_scenario",
        description="Sustained write throughput",
        scenario_type=ScenarioType.WRITE_THROUGHPUT,
        priority=ScenarioPriority.HIGH,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=10.0,
        dataset_profile=dataset,
        concurrent_writers=0,
        concurrent_readers=0,
        deterministic_random_seed=42,
        metrics_to_collect=[],
    )
    scenario_latency = BenchmarkScenario(
        name="latency_scenario",
        description="Time range query latency",
        scenario_type=ScenarioType.TIME_RANGE_QUERIES,
        priority=ScenarioPriority.MEDIUM,
        warmup_duration_seconds=0.0,
        benchmark_duration_seconds=10.0,
        dataset_profile=dataset,
        concurrent_writers=0,
        concurrent_readers=0,
        deterministic_random_seed=42,
        metrics_to_collect=[],
    )
    suite = BenchmarkSuite(
        name="test_suite",
        description="Test suite description",
        global_seed=42,
        scenarios=[scenario_write, scenario_latency],
    )

    results = [
        # dbA has both
        BenchmarkResult(
            database_name="dbA",
            scenario_name="write_scenario",
            scenario_type=ScenarioType.WRITE_THROUGHPUT,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            metrics=[
                BenchmarkMetric(
                    metric_type=MetricType.ROWS_PER_SECOND,
                    value=100.0,
                    unit=MetricUnit.COUNT,
                )
            ],
            success=True,
        ),
        BenchmarkResult(
            database_name="dbA",
            scenario_name="latency_scenario",
            scenario_type=ScenarioType.TIME_RANGE_QUERIES,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            metrics=[
                BenchmarkMetric(
                    metric_type=MetricType.AVERAGE_LATENCY_MS,
                    value=10.0,
                    unit=MetricUnit.MILLISECONDS,
                )
            ],
            success=True,
        ),
        # dbB has failed write query, but successful latency
        BenchmarkResult(
            database_name="dbB",
            scenario_name="write_scenario",
            scenario_type=ScenarioType.WRITE_THROUGHPUT,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            metrics=[],
            success=False,
        ),
        BenchmarkResult(
            database_name="dbB",
            scenario_name="latency_scenario",
            scenario_type=ScenarioType.TIME_RANGE_QUERIES,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            metrics=[
                BenchmarkMetric(
                    metric_type=MetricType.AVERAGE_LATENCY_MS,
                    value=10.0,
                    unit=MetricUnit.MILLISECONDS,
                )
            ],
            success=True,
        ),
    ]

    weights = {
        "sustained_write_throughput": 0.5,
        "time_range_queries": 0.5,
    }
    engine = ScoringEngine(weights=weights)
    report = engine.score(results, suite)

    db_map = {item.database: item for item in report.database_scores}

    # dbB missed/failed on write_scenario -> got 0.0 normalized score.
    # Latency: dbA (10.0), dbB (10.0) -> both got 100.0 normalized score.
    # Overall:
    # dbA: 100 * 0.5 + 100 * 0.5 = 100.0
    # dbB: 0 * 0.5 + 100 * 0.5 = 50.0

    assert db_map["dbA"].overall_score == 100.0
    assert db_map["dbB"].overall_score == 50.0
