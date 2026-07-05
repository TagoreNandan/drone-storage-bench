import json
from pathlib import Path

from benchmark.core.specification import BenchmarkResult


class ReportGenerator:
    """Generates artifacts, reports, and formatted tables from benchmark runs.

    Supports exporting to JSON, CSV, and summary Markdown for performance reports.
    """

    def __init__(self, results_dir: Path) -> None:
        """Initialize with target results storage directory."""
        self.results_dir = results_dir

    def generate_json_results(self, suite_results: list[BenchmarkResult], filename: str) -> Path:
        """Saves raw benchmark execution metadata and stats to a JSON file.

        Args:
            suite_results: List of compiled BenchmarkResult objects.
            filename: Target output filename.

        Returns:
            Path to the written JSON artifact.
        """
        raw_dir = self.results_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        output_path = raw_dir / filename

        # Dump results model data to JSON
        serializable_results = [result.model_dump(mode="json") for result in suite_results]

        with output_path.open("w") as f:
            json.dump(
                {
                    "run_timestamp": serializable_results[0]["started_at"]
                    if serializable_results
                    else "",
                    "results": serializable_results,
                },
                f,
                indent=2,
            )

        return output_path

    def generate_markdown_summary(
        self, suite_results: list[BenchmarkResult], filename: str
    ) -> Path:
        """Generates a high-level Markdown report comparing the databases.

        Args:
            suite_results: List of compiled BenchmarkResult objects.
            filename: Target output filename.

        Returns:
            Path to the written Markdown file.
        """
        reports_dir = self.results_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        output_path = reports_dir / filename

        # Compile comparative Markdown table
        lines = [
            "# Drone Storage Bench - Evaluation Report",
            "",
            "Comparative summary of time-series database benchmark workloads.",
            "",
            (
                "| Database | Scenario | Scenario Type | Success | Duration (s) | "
                "Error Details / Metrics Summary |"
            ),
            "| --- | --- | --- | --- | --- | --- |",
        ]

        for r in suite_results:
            duration = (r.completed_at - r.started_at).total_seconds()
            success_str = "✅ YES" if r.success else "❌ NO"

            # Summarize metrics or errors
            if r.success:
                metrics_summary = ", ".join(
                    [f"{m.metric_type.value}: {m.value} {m.unit.value}" for m in r.metrics]
                )
                details = metrics_summary if metrics_summary else "Completed (No metrics recorded)"
            else:
                details = f"Error: {r.error_message}"

            lines.append(
                f"| {r.database_name} | {r.scenario_name} | {r.scenario_type.value} | "
                f"{success_str} | {duration:.2f} | {details} |"
            )

        with output_path.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return output_path
