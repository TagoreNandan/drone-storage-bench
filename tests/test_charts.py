from datetime import UTC, datetime
from pathlib import Path

from benchmark.core.specification import (
    BenchmarkMetric,
    BenchmarkResult,
    MetricType,
    MetricUnit,
    ScenarioType,
)
from benchmark.reporting.charts import generate_all_charts
from benchmark.reporting.generator import ReportGenerator
from benchmark.scoring.engine import DatabaseScore, ScenarioScore, ScoringReport


def test_generate_all_charts_empty(tmp_path: Path) -> None:
    """Verifies that all 6 charts are generated as placeholders when no results exist."""
    charts_dir = tmp_path / "charts"
    results: list[BenchmarkResult] = []
    score_report = None

    paths = generate_all_charts(results, score_report, charts_dir, "test_prefix")

    assert len(paths) == 6
    for chart_name, path in paths.items():
        assert path.exists(), f"{chart_name} chart was not created"
        assert path.name.startswith("test_prefix_"), f"{chart_name} has incorrect filename"
        assert path.name.endswith(".png"), f"{chart_name} is not a PNG file"
        assert path.stat().st_size > 0, f"{chart_name} is an empty file"


def test_generate_all_charts_with_data(tmp_path: Path) -> None:
    """Verifies that all 6 charts are correctly generated when valid data is provided."""
    charts_dir = tmp_path / "charts"

    # Mock suite results
    r1 = BenchmarkResult(
        database_name="Postgres",
        scenario_name="Ingestion Workload",
        scenario_type=ScenarioType.WRITE_THROUGHPUT,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        success=True,
        metrics=[
            BenchmarkMetric(
                metric_type=MetricType.ROWS_PER_SECOND,
                value=150000.0,
                unit=MetricUnit.RECORDS_PER_SECOND,
            ),
            BenchmarkMetric(
                metric_type=MetricType.AVERAGE_LATENCY_MS, value=12.5, unit=MetricUnit.MILLISECONDS
            ),
            BenchmarkMetric(
                metric_type=MetricType.PHYSICAL_STORAGE_SIZE_BYTES,
                value=5000000.0,
                unit=MetricUnit.BYTES,
            ),
        ],
    )
    r2 = BenchmarkResult(
        database_name="Postgres",
        scenario_name="Compression Evaluation",
        scenario_type=ScenarioType.COMPRESSION_EVALUATION,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        success=True,
        metrics=[
            BenchmarkMetric(
                metric_type=MetricType.COMPRESSION_RATIO, value=4.5, unit=MetricUnit.COUNT
            ),
            BenchmarkMetric(
                metric_type=MetricType.COMPRESSION_PERCENTAGE, value=77.7, unit=MetricUnit.PERCENT
            ),
            BenchmarkMetric(
                metric_type=MetricType.PHYSICAL_STORAGE_SIZE_BYTES,
                value=1200000.0,
                unit=MetricUnit.BYTES,
            ),
        ],
    )

    suite_results = [r1, r2]

    # Mock ScoringReport
    score_report = ScoringReport(
        database_scores=[
            DatabaseScore(
                database="Postgres",
                overall_score=85.5,
                rank=1,
                scenario_scores=[
                    ScenarioScore(
                        database="Postgres",
                        scenario="Ingestion Workload",
                        scenario_type=ScenarioType.WRITE_THROUGHPUT.value,
                        metric_type=MetricType.ROWS_PER_SECOND.value,
                        raw_value=150000.0,
                        normalized_score=85.5,
                        weighted_score=17.1,
                    )
                ],
            )
        ],
        scoring_weights={"sustained_write_throughput": 0.20},
    )

    paths = generate_all_charts(suite_results, score_report, charts_dir, "run_123")

    assert len(paths) == 6
    for chart_name, path in paths.items():
        assert path.exists(), f"{chart_name} chart was not created"
        assert path.name.startswith("run_123_")
        assert path.stat().st_size > 0, f"{chart_name} is an empty file"


def test_report_generator_integration(tmp_path: Path) -> None:
    """Verifies report generator generates and embeds visualization paths."""
    results_dir = tmp_path / "results"
    report_gen = ReportGenerator(results_dir)

    r = BenchmarkResult(
        database_name="Postgres",
        scenario_name="Ingestion Workload",
        scenario_type=ScenarioType.WRITE_THROUGHPUT,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        success=True,
        metrics=[],
    )

    md_path = report_gen.generate_markdown_summary([r], "test_report.md", score_report=None)

    assert md_path.exists()
    md_content = md_path.read_text()

    # Verify section and image links exist
    assert "## Performance Visualizations" in md_content
    assert "![Overall Score](../charts/test_report_overall_score.png)" in md_content
    assert "![Performance Radar](../charts/test_report_radar_chart.png)" in md_content
    assert "![Throughput](../charts/test_report_throughput.png)" in md_content
    assert "![Latency](../charts/test_report_latency.png)" in md_content
    assert "![Compression](../charts/test_report_compression.png)" in md_content
    assert "![Storage Footprint](../charts/test_report_storage_footprint.png)" in md_content

    # Check physical file creation
    charts_dir = results_dir / "charts"
    assert (charts_dir / "test_report_overall_score.png").exists()
    assert (charts_dir / "test_report_radar_chart.png").exists()
    assert (charts_dir / "test_report_throughput.png").exists()
    assert (charts_dir / "test_report_latency.png").exists()
    assert (charts_dir / "test_report_compression.png").exists()
    assert (charts_dir / "test_report_storage_footprint.png").exists()
