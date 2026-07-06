from statistics import mean
from typing import Any


class MetricsCollector:
    """Collects, aggregates, and structures benchmark latency and throughput data.

    Calculates percentiles (p50, p95, p99), mean latencies, and failure ratios
    for a fair multi-database performance comparison.
    """

    def __init__(self) -> None:
        """Initialize list containers for metrics storage."""
        self._records: list[dict[str, Any]] = []

    def record_operation(
        self, database: str, workload: str, op_type: str, duration_sec: float, success: bool
    ) -> None:
        """Records the latency and outcome of a single operation.

        Args:
            database: Name of target database.
            workload: Name of workload running.
            op_type: Operation type ('write' or 'query').
            duration_sec: Execution duration in seconds.
            success: Whether the operation succeeded.
        """
        self._records.append(
            {
                "database": database,
                "workload": workload,
                "op_type": op_type,
                "duration_sec": duration_sec,
                "success": success,
            }
        )

    def calculate_summary(self) -> dict[str, Any]:
        """Calculate benchmark summary statistics."""
        summary: dict[str, Any] = {
            "total_operations": len(self._records),
            "databases": {},
        }

        databases = {record["database"] for record in self._records}

        for database in databases:
            records = [record for record in self._records if record["database"] == database]

            durations = [record["duration_sec"] for record in records]
            successes = sum(record["success"] for record in records)

            durations.sort()

            if durations:
                p50 = durations[int((len(durations) - 1) * 0.50)]
                p95 = durations[int((len(durations) - 1) * 0.95)]
                p99 = durations[int((len(durations) - 1) * 0.99)]
            else:
                p50 = 0.0
                p95 = 0.0
                p99 = 0.0

            total_time = sum(durations)

            throughput = len(records) / total_time if total_time > 0 else 0.0

            summary["databases"][database] = {
                "operations": len(records),
                "successful_operations": successes,
                "failed_operations": len(records) - successes,
                "success_rate": (successes / len(records) if records else 0.0),
                "average_latency_seconds": (mean(durations) if durations else 0.0),
                "min_latency_seconds": (min(durations) if durations else 0.0),
                "max_latency_seconds": (max(durations) if durations else 0.0),
                "p50_latency_seconds": p50,
                "p95_latency_seconds": p95,
                "p99_latency_seconds": p99,
                "throughput_ops_per_second": throughput,
            }

        return summary
