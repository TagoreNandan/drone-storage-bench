import random
import time
from datetime import UTC, datetime

import structlog

from benchmark.core.database import BaseDatabaseClient
from benchmark.core.specification import (
    BenchmarkMetric,
    BenchmarkResult,
    MetricType,
    MetricUnit,
)
from benchmark.core.workload import BaseWorkload
from benchmark.workloads.ingestion import calculate_percentile

logger = structlog.get_logger()


class QueryWorkload(BaseWorkload):
    """Workload scenario designed to test telemetry retrieval and aggregations.

    Evaluates time-bucket aggregations, windowing, bounding box searches,
    and relational joins with the PostgreSQL control plane.
    """

    async def execute(self, client: BaseDatabaseClient) -> BenchmarkResult:
        """Runs the query benchmark execution loop.

        Args:
            client: An active database client.

        Returns:
            BenchmarkResult containing query performance metrics.
        """
        # Return scaffold placeholder.
        now = datetime.now(UTC)
        return BenchmarkResult(
            database_name=client.__class__.__name__,
            scenario_name=self.scenario.name,
            scenario_type=self.scenario.scenario_type,
            started_at=now,
            completed_at=now,
            metrics=[],
            success=False,
            error_message="Query workload execution not implemented.",
        )


class TimeRangeQueryWorkload(BaseWorkload):
    """Workload scenario designed to measure query latency for retrieving telemetry over windows.

    Executes repeated time-range queries against the target database, selecting
    windows and drone IDs deterministically based on seed configurations.
    """

    async def execute(self, client: BaseDatabaseClient) -> BenchmarkResult:
        """Runs the time-range query benchmark loop.

        Args:
            client: An active database client.

        Returns:
            BenchmarkResult containing query latency, success rates, and row counts.
        """
        if not self.scenario.query_profile:
            raise ValueError("Query profile must be configured for TimeRangeQueryWorkload")

        qp = self.scenario.query_profile
        dataset_p = self.scenario.dataset_profile

        # Read config options from metadata
        params = qp.metadata or {}
        iteration_count = params.get("iteration_count", 100)
        failure_threshold = params.get("failure_threshold", 10)

        # Configurable query windows list (seconds)
        raw_windows = params.get("query_windows")
        if isinstance(raw_windows, list):
            query_windows = [float(w) for w in raw_windows]
        else:
            query_windows = [qp.time_window_seconds]

        # Deterministic random generator for inputs
        local_random = random.Random(self.scenario.deterministic_random_seed)

        # Establish start & end range of telemetry data loaded in database
        from datetime import timedelta

        start_time = datetime(2026, 7, 4, 0, 0, 0, tzinfo=UTC)
        dataset_duration = self.scenario.benchmark_duration_seconds
        start_time + timedelta(seconds=dataset_duration)

        logger.info(
            "Starting time-range query benchmark execution",
            iterations=iteration_count,
            time_windows=query_windows,
            dataset_duration=dataset_duration,
        )

        successful_queries = 0
        failed_queries = 0
        latencies_ms: list[float] = []
        rows_returned_list: list[int] = []
        last_exception: Exception | None = None

        started_at = datetime.now(UTC)
        benchmark_start_timer = time.perf_counter()

        for _ in range(iteration_count):
            # 1. Randomly select query window size
            window_size = local_random.choice(query_windows)

            # Ensure window size doesn't exceed total dataset duration
            window_size = min(window_size, dataset_duration)

            # 2. Pick a random start time within dataset limits
            max_offset = max(0.0, dataset_duration - window_size)
            offset = local_random.uniform(0.0, max_offset)
            window_start = start_time + timedelta(seconds=offset)
            window_end = window_start + timedelta(seconds=window_size)

            # 3. Select random vehicle ID
            vehicle_idx = local_random.randint(0, max(0, dataset_p.simulated_drones - 1))
            vehicle_id = f"drone_{vehicle_idx:04d}"

            # Execute query
            query_params = {
                "start_time": window_start,
                "end_time": window_end,
                "vehicle_id": vehicle_id,
            }

            q_start_timer = time.perf_counter()
            try:
                # Execute database specific query through adapter
                res = await client.execute_query("time_range_query", query_params)
                q_latency = (time.perf_counter() - q_start_timer) * 1000.0
                latencies_ms.append(q_latency)
                successful_queries += 1

                # Extract row counts returned
                row_count = res.get("row_count", 0)
                rows_returned_list.append(row_count)
            except Exception as e:
                q_latency = (time.perf_counter() - q_start_timer) * 1000.0
                latencies_ms.append(q_latency)
                failed_queries += 1
                last_exception = e
                logger.error("Query execution failed", error=str(e), params=query_params)
                if failed_queries > failure_threshold:
                    logger.error("Failure threshold exceeded, aborting query workload")
                    break

        completed_at = datetime.now(UTC)
        total_duration = time.perf_counter() - benchmark_start_timer

        # Calculate statistics
        total_queries = successful_queries + failed_queries
        avg_latency = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0
        p50 = calculate_percentile(latencies_ms, 50.0)
        p95 = calculate_percentile(latencies_ms, 95.0)
        p99 = calculate_percentile(latencies_ms, 99.0)
        max_latency = max(latencies_ms) if latencies_ms else 0.0

        avg_rows = sum(rows_returned_list) / len(rows_returned_list) if rows_returned_list else 0.0
        max_rows = max(rows_returned_list) if rows_returned_list else 0

        # Construct metrics list
        metrics = [
            BenchmarkMetric(
                metric_type=MetricType.TOTAL_QUERIES,
                value=float(total_queries),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.SUCCESSFUL_QUERIES,
                value=float(successful_queries),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.FAILED_QUERIES,
                value=float(failed_queries),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.TOTAL_DURATION_SECONDS,
                value=total_duration,
                unit=MetricUnit.SECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.AVERAGE_LATENCY_MS,
                value=avg_latency,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.P50_LATENCY_MS,
                value=p50,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.P95_LATENCY_MS,
                value=p95,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.P99_LATENCY_MS,
                value=p99,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.MAXIMUM_LATENCY_MS,
                value=max_latency,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.ROWS_RETURNED_AVERAGE,
                value=avg_rows,
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.ROWS_RETURNED_MAXIMUM,
                value=float(max_rows),
                unit=MetricUnit.COUNT,
            ),
            # Standard metrics for general report systems
            BenchmarkMetric(
                metric_type=MetricType.READ_THROUGHPUT,
                value=successful_queries / total_duration if total_duration > 0 else 0.0,
                unit=MetricUnit.OPERATIONS_PER_SECOND,
            ),
            BenchmarkMetric(
                metric_type=MetricType.READ_LATENCY_MEAN,
                value=avg_latency,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.READ_LATENCY_P95,
                value=p95,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.READ_LATENCY_P99,
                value=p99,
                unit=MetricUnit.MILLISECONDS,
            ),
        ]

        success = failed_queries <= failure_threshold
        error_msg = str(last_exception) if last_exception else None

        return BenchmarkResult(
            database_name=client.__class__.__name__,
            scenario_name=self.scenario.name,
            scenario_type=self.scenario.scenario_type,
            started_at=started_at,
            completed_at=completed_at,
            metrics=metrics,
            success=success,
            error_message=error_msg,
        )


class AggregationQueryWorkload(BaseWorkload):
    """Workload scenario designed to measure analytical query performance over telemetry data.

    Executes repeated aggregations (AVG, MIN, MAX, SUM, etc.) over configurable
    time windows, using deterministic random query inputs.
    """

    async def execute(self, client: BaseDatabaseClient) -> BenchmarkResult:
        """Runs the aggregation query benchmark loop.

        Args:
            client: An active database client.

        Returns:
            BenchmarkResult containing analytical performance statistics.
        """
        if not self.scenario.query_profile:
            raise ValueError("Query profile must be configured for AggregationQueryWorkload")

        qp = self.scenario.query_profile
        dataset_p = self.scenario.dataset_profile

        # Read config options from metadata
        params = qp.metadata or {}
        iteration_count = params.get("iteration_count", 100)
        failure_threshold = params.get("failure_threshold", 10)

        # Configurable aggregation functions list
        agg_functions = params.get("aggregation_functions", ["AVG"])

        # Configurable query windows list (seconds)
        raw_windows = params.get("query_windows")
        if isinstance(raw_windows, list):
            query_windows = [float(w) for w in raw_windows]
        else:
            query_windows = [qp.time_window_seconds]

        # Deterministic random generator for inputs
        local_random = random.Random(self.scenario.deterministic_random_seed)

        # Establish start & end range of telemetry data loaded in database
        from datetime import timedelta

        start_time = datetime(2026, 7, 4, 0, 0, 0, tzinfo=UTC)
        dataset_duration = self.scenario.benchmark_duration_seconds
        start_time + timedelta(seconds=dataset_duration)

        logger.info(
            "Starting aggregation query benchmark execution",
            iterations=iteration_count,
            time_windows=query_windows,
            agg_functions=agg_functions,
            dataset_duration=dataset_duration,
        )

        successful_queries = 0
        failed_queries = 0
        latencies_ms: list[float] = []
        groups_returned_list: list[int] = []
        last_exception: Exception | None = None

        started_at = datetime.now(UTC)
        benchmark_start_timer = time.perf_counter()

        for _ in range(iteration_count):
            # 1. Randomly select aggregation function
            agg_func = local_random.choice(agg_functions)

            # 2. Randomly select query window size
            window_size = local_random.choice(query_windows)
            window_size = min(window_size, dataset_duration)

            # 3. Pick a random start time within dataset limits
            max_offset = max(0.0, dataset_duration - window_size)
            offset = local_random.uniform(0.0, max_offset)
            window_start = start_time + timedelta(seconds=offset)
            window_end = window_start + timedelta(seconds=window_size)

            # 4. Select random vehicle ID
            vehicle_idx = local_random.randint(0, max(0, dataset_p.simulated_drones - 1))
            vehicle_id = f"drone_{vehicle_idx:04d}"

            # Execute query
            query_params = {
                "start_time": window_start,
                "end_time": window_end,
                "vehicle_id": vehicle_id,
                "aggregation_function": agg_func,
                "aggregation_interval_seconds": qp.aggregation_interval_seconds or 60.0,
            }

            q_start_timer = time.perf_counter()
            try:
                res = await client.execute_query("aggregation_query", query_params)
                q_latency = (time.perf_counter() - q_start_timer) * 1000.0
                latencies_ms.append(q_latency)
                successful_queries += 1

                # Extract groups returned
                groups_count = res.get("groups_returned", 0)
                groups_returned_list.append(groups_count)
            except Exception as e:
                q_latency = (time.perf_counter() - q_start_timer) * 1000.0
                latencies_ms.append(q_latency)
                failed_queries += 1
                last_exception = e
                logger.error("Aggregation query failed", error=str(e), params=query_params)
                if failed_queries > failure_threshold:
                    logger.error("Failure threshold exceeded, aborting aggregation workload")
                    break

        completed_at = datetime.now(UTC)
        total_duration = time.perf_counter() - benchmark_start_timer

        # Calculate statistics
        total_queries = successful_queries + failed_queries
        avg_latency = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0
        p50 = calculate_percentile(latencies_ms, 50.0)
        p95 = calculate_percentile(latencies_ms, 95.0)
        p99 = calculate_percentile(latencies_ms, 99.0)
        max_latency = max(latencies_ms) if latencies_ms else 0.0

        avg_groups = (
            sum(groups_returned_list) / len(groups_returned_list) if groups_returned_list else 0.0
        )
        max_groups = max(groups_returned_list) if groups_returned_list else 0

        # Construct metrics list
        metrics = [
            BenchmarkMetric(
                metric_type=MetricType.TOTAL_QUERIES,
                value=float(total_queries),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.SUCCESSFUL_QUERIES,
                value=float(successful_queries),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.FAILED_QUERIES,
                value=float(failed_queries),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.TOTAL_DURATION_SECONDS,
                value=total_duration,
                unit=MetricUnit.SECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.AVERAGE_LATENCY_MS,
                value=avg_latency,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.P50_LATENCY_MS,
                value=p50,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.P95_LATENCY_MS,
                value=p95,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.P99_LATENCY_MS,
                value=p99,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.MAXIMUM_LATENCY_MS,
                value=max_latency,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.AVERAGE_GROUPS_RETURNED,
                value=avg_groups,
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.MAXIMUM_GROUPS_RETURNED,
                value=float(max_groups),
                unit=MetricUnit.COUNT,
            ),
            # Standard metrics for general report systems
            BenchmarkMetric(
                metric_type=MetricType.READ_THROUGHPUT,
                value=successful_queries / total_duration if total_duration > 0 else 0.0,
                unit=MetricUnit.OPERATIONS_PER_SECOND,
            ),
            BenchmarkMetric(
                metric_type=MetricType.READ_LATENCY_MEAN,
                value=avg_latency,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.READ_LATENCY_P95,
                value=p95,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.READ_LATENCY_P99,
                value=p99,
                unit=MetricUnit.MILLISECONDS,
            ),
        ]

        success = failed_queries <= failure_threshold
        error_msg = str(last_exception) if last_exception else None

        return BenchmarkResult(
            database_name=client.__class__.__name__,
            scenario_name=self.scenario.name,
            scenario_type=self.scenario.scenario_type,
            started_at=started_at,
            completed_at=completed_at,
            metrics=metrics,
            success=success,
            error_message=error_msg,
        )


class HistoricalReplayWorkload(BaseWorkload):
    """Workload scenario designed to measure chronological mission replay performance.

    Queries all telemetry records of a given mission ID sequentially sorted by timestamp.
    """

    async def execute(self, client: BaseDatabaseClient) -> BenchmarkResult:
        """Runs the historical replay benchmark loop.

        Args:
            client: An active database client.

        Returns:
            BenchmarkResult containing mission replay performance metrics.
        """
        if not self.scenario.query_profile:
            raise ValueError("Query profile must be configured for HistoricalReplayWorkload")

        qp = self.scenario.query_profile
        dataset_p = self.scenario.dataset_profile

        # Read config options from metadata
        params = qp.metadata or {}
        iteration_count = params.get("iteration_count", 5)
        failure_threshold = params.get("failure_threshold", 2)

        # Configurable mission selection list
        configured_missions = params.get("mission_ids")
        if isinstance(configured_missions, list):
            mission_ids = [str(m) for m in configured_missions]
        else:
            # Auto generate based on dataset drone limits
            mission_ids = [f"mission_{i:04d}" for i in range(dataset_p.simulated_drones)]

        # Specific mission ID override if explicitly set
        single_mission = params.get("mission_id")

        # Deterministic random generator for input selections
        local_random = random.Random(self.scenario.deterministic_random_seed)

        logger.info(
            "Starting historical replay benchmark execution",
            iterations=iteration_count,
            available_missions=mission_ids,
        )

        successful_replays = 0
        failed_replays = 0
        total_rows_returned = 0
        latencies_ms: list[float] = []
        last_exception: Exception | None = None

        started_at = datetime.now(UTC)
        benchmark_start_timer = time.perf_counter()

        for _ in range(iteration_count):
            # Select mission to replay
            if single_mission:
                selected_mission = str(single_mission)
            else:
                selected_mission = local_random.choice(mission_ids)

            query_params = {
                "mission_id": selected_mission,
                "sort_order": "asc",  # Chronological order
            }

            replay_start_timer = time.perf_counter()
            try:
                # Query complete mission through database client adapter
                res = await client.execute_query("historical_replay_query", query_params)
                replay_latency = (time.perf_counter() - replay_start_timer) * 1000.0
                latencies_ms.append(replay_latency)
                successful_replays += 1

                # Accumulate rows returned
                row_count = res.get("row_count", 0)
                total_rows_returned += row_count
            except Exception as e:
                replay_latency = (time.perf_counter() - replay_start_timer) * 1000.0
                latencies_ms.append(replay_latency)
                failed_replays += 1
                last_exception = e
                logger.error(
                    "Historical replay query execution failed",
                    error=str(e),
                    mission=selected_mission,
                )
                if failed_replays > failure_threshold:
                    logger.error("Failure threshold exceeded, aborting replay workload")
                    break

        completed_at = datetime.now(UTC)
        total_duration = time.perf_counter() - benchmark_start_timer

        # Calculate statistics
        total_replays = successful_replays + failed_replays
        avg_latency = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0
        p50 = calculate_percentile(latencies_ms, 50.0)
        p95 = calculate_percentile(latencies_ms, 95.0)
        p99 = calculate_percentile(latencies_ms, 99.0)
        max_latency = max(latencies_ms) if latencies_ms else 0.0

        # Throughput calculations (rows per second across active query time)
        total_active_query_sec = sum(latencies_ms) / 1000.0
        replay_throughput = (
            total_rows_returned / total_active_query_sec if total_active_query_sec > 0.0 else 0.0
        )

        metrics = [
            BenchmarkMetric(
                metric_type=MetricType.TOTAL_REPLAYS,
                value=float(total_replays),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.SUCCESSFUL_REPLAYS,
                value=float(successful_replays),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.FAILED_REPLAYS,
                value=float(failed_replays),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.TOTAL_DURATION_SECONDS,
                value=total_duration,
                unit=MetricUnit.SECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.AVERAGE_LATENCY_MS,
                value=avg_latency,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.P50_LATENCY_MS,
                value=p50,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.P95_LATENCY_MS,
                value=p95,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.P99_LATENCY_MS,
                value=p99,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.MAXIMUM_LATENCY_MS,
                value=max_latency,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.ROWS_RETURNED,
                value=float(total_rows_returned),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.REPLAY_THROUGHPUT_ROWS_PER_SECOND,
                value=replay_throughput,
                unit=MetricUnit.RECORDS_PER_SECOND,
            ),
            # Standard metrics for reports
            BenchmarkMetric(
                metric_type=MetricType.READ_THROUGHPUT,
                value=successful_replays / total_duration if total_duration > 0.0 else 0.0,
                unit=MetricUnit.OPERATIONS_PER_SECOND,
            ),
            BenchmarkMetric(
                metric_type=MetricType.READ_LATENCY_MEAN,
                value=avg_latency,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.READ_LATENCY_P95,
                value=p95,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.READ_LATENCY_P99,
                value=p99,
                unit=MetricUnit.MILLISECONDS,
            ),
        ]

        success = failed_replays <= failure_threshold
        error_msg = str(last_exception) if last_exception else None

        return BenchmarkResult(
            database_name=client.__class__.__name__,
            scenario_name=self.scenario.name,
            scenario_type=self.scenario.scenario_type,
            started_at=started_at,
            completed_at=completed_at,
            metrics=metrics,
            success=success,
            error_message=error_msg,
        )


class JoinEvaluationWorkload(BaseWorkload):
    """Workload scenario to evaluate correlating telemetry with control-plane metadata.

    Supports native SQL JOIN and application-layer merge execution models.
    """

    async def execute(self, client: BaseDatabaseClient) -> BenchmarkResult:
        """Runs the JOIN query benchmark loop.

        Args:
            client: An active database client.

        Returns:
            BenchmarkResult containing query latencies, strategy, and merge timing.
        """
        if not self.scenario.query_profile:
            raise ValueError("Query profile must be configured for JoinEvaluationWorkload")

        qp = self.scenario.query_profile
        dataset_p = self.scenario.dataset_profile

        # Read config options from metadata
        params = qp.metadata or {}
        iteration_count = params.get("iteration_count", 20)
        failure_threshold = params.get("failure_threshold", 5)

        # Configurable query windows list (seconds)
        raw_windows = params.get("query_windows")
        if isinstance(raw_windows, list):
            query_windows = [float(w) for w in raw_windows]
        else:
            query_windows = [qp.time_window_seconds]

        # Deterministic random generator for inputs
        local_random = random.Random(self.scenario.deterministic_random_seed)

        # Establish start & end range of telemetry data loaded in database
        from datetime import timedelta

        start_time = datetime(2026, 7, 4, 0, 0, 0, tzinfo=UTC)
        dataset_duration = self.scenario.benchmark_duration_seconds
        start_time + timedelta(seconds=dataset_duration)

        logger.info(
            "Starting JOIN query benchmark execution",
            iterations=iteration_count,
            time_windows=query_windows,
            dataset_duration=dataset_duration,
        )

        successful_queries = 0
        failed_queries = 0
        latencies_ms: list[float] = []
        rows_returned_list: list[int] = []
        merge_durations_ms: list[float] = []
        strategies: set[str] = set()
        last_exception: Exception | None = None

        started_at = datetime.now(UTC)
        benchmark_start_timer = time.perf_counter()

        for _ in range(iteration_count):
            # 1. Randomly select query window size
            window_size = local_random.choice(query_windows)
            window_size = min(window_size, dataset_duration)

            # 2. Pick a random start time within dataset limits
            max_offset = max(0.0, dataset_duration - window_size)
            offset = local_random.uniform(0.0, max_offset)
            window_start = start_time + timedelta(seconds=offset)
            window_end = window_start + timedelta(seconds=window_size)

            # 3. Select random vehicle ID
            vehicle_idx = local_random.randint(0, max(0, dataset_p.simulated_drones - 1))
            vehicle_id = f"drone_{vehicle_idx:04d}"

            # Execute query
            query_params = {
                "start_time": window_start,
                "end_time": window_end,
                "vehicle_id": vehicle_id,
                "join_target_table": qp.join_target_table or "vehicles",
            }

            q_start_timer = time.perf_counter()
            try:
                # Execute database specific JOIN through adapter
                res = await client.execute_query("join_query", query_params)
                q_latency = (time.perf_counter() - q_start_timer) * 1000.0
                latencies_ms.append(q_latency)
                successful_queries += 1

                # Extract row counts and merge times
                row_count = res.get("row_count", 0)
                rows_returned_list.append(row_count)

                merge_dur = res.get("merge_duration_ms", 0.0)
                merge_durations_ms.append(merge_dur)

                strategy = res.get("join_strategy", "native")
                strategies.add(strategy)
            except Exception as e:
                q_latency = (time.perf_counter() - q_start_timer) * 1000.0
                latencies_ms.append(q_latency)
                failed_queries += 1
                last_exception = e
                logger.error("JOIN query execution failed", error=str(e), params=query_params)
                if failed_queries > failure_threshold:
                    logger.error("Failure threshold exceeded, aborting JOIN workload")
                    break

        completed_at = datetime.now(UTC)
        total_duration = time.perf_counter() - benchmark_start_timer

        # Calculate statistics
        total_queries = successful_queries + failed_queries
        avg_latency = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0
        p50 = calculate_percentile(latencies_ms, 50.0)
        p95 = calculate_percentile(latencies_ms, 95.0)
        p99 = calculate_percentile(latencies_ms, 99.0)
        max_latency = max(latencies_ms) if latencies_ms else 0.0

        total_rows = sum(rows_returned_list)
        avg_merge = sum(merge_durations_ms) / len(merge_durations_ms) if merge_durations_ms else 0.0

        # Encode strategy: 1.0 for native, 2.0 for application-layer merge
        strategy_str = next(iter(strategies)) if strategies else "native"
        strategy_val = 1.0 if "native" in strategy_str.lower() else 2.0

        # Construct metrics list
        metrics = [
            BenchmarkMetric(
                metric_type=MetricType.TOTAL_QUERIES,
                value=float(total_queries),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.SUCCESSFUL_QUERIES,
                value=float(successful_queries),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.FAILED_QUERIES,
                value=float(failed_queries),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.TOTAL_DURATION_SECONDS,
                value=total_duration,
                unit=MetricUnit.SECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.AVERAGE_LATENCY_MS,
                value=avg_latency,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.P50_LATENCY_MS,
                value=p50,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.P95_LATENCY_MS,
                value=p95,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.P99_LATENCY_MS,
                value=p99,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.MAXIMUM_LATENCY_MS,
                value=max_latency,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.ROWS_RETURNED,
                value=float(total_rows),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.MERGE_DURATION_MS,
                value=avg_merge,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.JOIN_STRATEGY,
                value=strategy_val,
                unit=MetricUnit.COUNT,
            ),
            # Standard metrics for general report systems
            BenchmarkMetric(
                metric_type=MetricType.READ_THROUGHPUT,
                value=successful_queries / total_duration if total_duration > 0.0 else 0.0,
                unit=MetricUnit.OPERATIONS_PER_SECOND,
            ),
            BenchmarkMetric(
                metric_type=MetricType.READ_LATENCY_MEAN,
                value=avg_latency,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.READ_LATENCY_P95,
                value=p95,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.READ_LATENCY_P99,
                value=p99,
                unit=MetricUnit.MILLISECONDS,
            ),
        ]

        success = failed_queries <= failure_threshold
        error_msg = str(last_exception) if last_exception else None

        return BenchmarkResult(
            database_name=client.__class__.__name__,
            scenario_name=self.scenario.name,
            scenario_type=self.scenario.scenario_type,
            started_at=started_at,
            completed_at=completed_at,
            metrics=metrics,
            success=success,
            error_message=error_msg,
        )
