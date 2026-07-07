import time
from datetime import UTC, datetime
from typing import Any

import structlog

from benchmark.core.database import BaseDatabaseClient
from benchmark.core.specification import (
    BenchmarkMetric,
    BenchmarkResult,
    MetricType,
    MetricUnit,
)
from benchmark.core.workload import BaseWorkload

logger = structlog.get_logger()


class CompressionEvaluationWorkload(BaseWorkload):
    """Workload scenario designed to evaluate storage compression efficiency.

    Triggers adapter-specific compression commands, queries final physical disk storage
    consumption, and calculates the compression ratio and percentage metrics.
    """

    async def execute(self, client: BaseDatabaseClient) -> BenchmarkResult:
        """Runs the compression evaluation benchmark.

        Args:
            client: An active database client.

        Returns:
            BenchmarkResult containing compression ratios, logical/physical bytes, and timing.
        """
        # Read parameters from query profile and workload profile metadata
        params: dict[str, Any] = {}
        if self.scenario.workload_profile and self.scenario.workload_profile.metadata:
            params.update(self.scenario.workload_profile.metadata)
        if self.scenario.query_profile and self.scenario.query_profile.metadata:
            params.update(self.scenario.query_profile.metadata)

        started_at = datetime.now(UTC)
        comp_start_timer = time.perf_counter()

        logger.info("Executing database-specific compression commands")
        # Trigger adapter-specific compression via execution mapping
        try:
            await client.execute_query("compress", {})
        except Exception as e:
            logger.error("Adapter compression execution failed", error=str(e))
            completed_at = datetime.now(UTC)
            return BenchmarkResult(
                database_name=client.__class__.__name__,
                scenario_name=self.scenario.name,
                scenario_type=self.scenario.scenario_type,
                started_at=started_at,
                completed_at=completed_at,
                metrics=[],
                success=False,
                error_message=f"Adapter compression execution failed: {e!s}",
            )

        comp_duration_ms = (time.perf_counter() - comp_start_timer) * 1000.0

        # Retrieve physical storage size from adapter
        try:
            physical_size = await client.get_storage_size_bytes()
            if physical_size is not None and physical_size <= 0:
                physical_size = None
        except Exception as e:
            logger.error("Failed to retrieve physical disk storage size", error=str(e))
            completed_at = datetime.now(UTC)
            return BenchmarkResult(
                database_name=client.__class__.__name__,
                scenario_name=self.scenario.name,
                scenario_type=self.scenario.scenario_type,
                started_at=started_at,
                completed_at=completed_at,
                metrics=[],
                success=False,
                error_message=f"Disk size retrieval failed: {e!s}",
            )

        # Retrieve logical row counts to compute base logical size
        total_rows = 0
        try:
            row_count_res = await client.execute_query("total_row_count", {})
            total_rows = row_count_res.get("row_count", 0)
        except Exception as e:
            logger.warning("Could not query total row count from database", error=str(e))

        # Fallback dynamic row count calculation if DB is empty or fails
        if total_rows <= 0:
            dataset_p = self.scenario.dataset_profile
            duration = self.scenario.benchmark_duration_seconds
            total_rows = int(
                dataset_p.simulated_drones * dataset_p.telemetry_frequency_hz * duration
            )

        # Assume standard 128 bytes per logical record if logical size is not explicitly configured
        logical_size = params.get("logical_dataset_size_bytes")
        if logical_size is None:
            logical_size = total_rows * 128

        # Compute compression metrics
        if physical_size is not None and physical_size > 0:
            compression_ratio = float(logical_size) / float(physical_size)
            compression_percentage = (1.0 - (float(physical_size) / float(logical_size))) * 100.0
        else:
            compression_ratio = None
            compression_percentage = None

        completed_at = datetime.now(UTC)
        total_duration = time.perf_counter() - comp_start_timer

        metrics = [
            BenchmarkMetric(
                metric_type=MetricType.LOGICAL_DATASET_SIZE_BYTES,
                value=float(logical_size),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.PHYSICAL_STORAGE_SIZE_BYTES,
                value=float(physical_size) if physical_size is not None else None,
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.COMPRESSION_RATIO,
                value=compression_ratio,
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.COMPRESSION_PERCENTAGE,
                value=compression_percentage,
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.COMPRESSION_DURATION_MS,
                value=comp_duration_ms,
                unit=MetricUnit.MILLISECONDS,
            ),
            # Standard metrics for reports
            BenchmarkMetric(
                metric_type=MetricType.TOTAL_DURATION_SECONDS,
                value=total_duration,
                unit=MetricUnit.SECONDS,
            ),
        ]

        return BenchmarkResult(
            database_name=client.__class__.__name__,
            scenario_name=self.scenario.name,
            scenario_type=self.scenario.scenario_type,
            started_at=started_at,
            completed_at=completed_at,
            metrics=metrics,
            success=True,
            error_message=None,
        )
