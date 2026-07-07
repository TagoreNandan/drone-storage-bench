import asyncio
import math
import random
import time
from datetime import UTC, datetime, timedelta

import structlog

from benchmark.core.database import BaseDatabaseClient
from benchmark.core.specification import (
    BenchmarkMetric,
    BenchmarkResult,
    MetricType,
    MetricUnit,
)
from benchmark.core.workload import BaseWorkload
from benchmark.generators.telemetry import DeterministicTelemetryGenerator
from benchmark.utils.batcher import batch_generator

logger = structlog.get_logger()


def calculate_percentile(values: list[float], percentile: float) -> float:
    """Calculates percentile from a list of floats using linear interpolation."""
    if not values:
        return 0.0
    sorted_val = sorted(values)
    k = (len(sorted_val) - 1) * (percentile / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_val[int(k)]
    d0 = sorted_val[int(f)] * (c - k)
    d1 = sorted_val[int(c)] * (k - f)
    return d0 + d1


class WriteThroughputWorkload(BaseWorkload):
    """Workload scenario designed to measure maximum sustained telemetry ingestion rate.

    Streams deterministic records, aggregates them into batches, and pushes them
    into the database client. Respects warmup and execution durations.
    """

    async def execute(self, client: BaseDatabaseClient) -> BenchmarkResult:
        """Runs the write-heavy telemetry ingestion benchmark loop.

        Args:
            client: An active database client.

        Returns:
            BenchmarkResult containing throughput and latency statistics.
        """
        # Ensure workload profile is available
        if not self.scenario.workload_profile:
            raise ValueError("Workload profile must be configured for WriteThroughputWorkload")

        batch_size = self.scenario.workload_profile.batch_size
        warmup_duration = self.scenario.warmup_duration_seconds
        benchmark_duration = self.scenario.benchmark_duration_seconds

        # Configure dynamic parameters from metadata / config
        params = self.scenario.workload_profile.metadata or {}
        failure_threshold = params.get("failure_threshold", 100)

        from benchmark.core.seed import DeterministicSeedManager

        seed_manager = DeterministicSeedManager(self.scenario.dataset_profile.seed)

        # Initialize deterministic telemetry generator
        generator = DeterministicTelemetryGenerator(
            seed_manager=seed_manager,
            num_drones=self.scenario.dataset_profile.simulated_drones,
            frequency_hz=self.scenario.dataset_profile.telemetry_frequency_hz,
            duration_seconds=warmup_duration + benchmark_duration + 10.0,  # Buffer
            custom_metric_names=None,
        )

        records_stream = generator.stream_records()
        batches = batch_generator(records_stream, batch_size)

        # --- 1. Warm-up Phase ---
        if warmup_duration > 0:
            logger.info("Starting sustained write throughput warmup", duration=warmup_duration)
            warmup_start = time.perf_counter()
            for batch in batches:
                try:
                    await client.write_telemetry_batch(batch)
                except Exception as e:
                    logger.debug("Error during warmup batch write", error=str(e))

                if time.perf_counter() - warmup_start >= warmup_duration:
                    break

        # --- 2. Ingestion Benchmarking Phase ---
        logger.info(
            "Starting sustained write throughput benchmark execution", duration=benchmark_duration
        )
        # Re-initialize generator/batches to ensure we don't run out of records due to unthrottled warmup
        generator = DeterministicTelemetryGenerator(
            seed_manager=seed_manager,
            num_drones=self.scenario.dataset_profile.simulated_drones,
            frequency_hz=self.scenario.dataset_profile.telemetry_frequency_hz,
            duration_seconds=benchmark_duration + 10.0,
            custom_metric_names=None,
            start_time=generator.start_time + timedelta(seconds=warmup_duration),
        )
        records_stream = generator.stream_records()
        batches = batch_generator(records_stream, batch_size)

        successful_batches = 0
        failed_batches = 0
        total_rows_written = 0
        latencies_ms: list[float] = []
        last_exception: Exception | None = None

        started_at = datetime.now(UTC)
        benchmark_start_timer = time.perf_counter()

        for batch in batches:
            batch_start_timer = time.perf_counter()
            try:
                await client.write_telemetry_batch(batch)
                batch_latency = (time.perf_counter() - batch_start_timer) * 1000.0
                latencies_ms.append(batch_latency)
                successful_batches += 1
                total_rows_written += len(batch)
            except Exception as e:
                batch_latency = (time.perf_counter() - batch_start_timer) * 1000.0
                latencies_ms.append(batch_latency)
                failed_batches += 1
                last_exception = e
                logger.error("Batch write failure", error=str(e))
                if failed_batches > failure_threshold:
                    logger.error("Failure threshold exceeded, aborting workload")
                    break

            if time.perf_counter() - benchmark_start_timer >= benchmark_duration:
                break

        completed_at = datetime.now(UTC)
        total_duration = time.perf_counter() - benchmark_start_timer

        # Calculate metrics
        avg_latency = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0
        p50 = calculate_percentile(latencies_ms, 50.0)
        p95 = calculate_percentile(latencies_ms, 95.0)
        p99 = calculate_percentile(latencies_ms, 99.0)
        rows_per_second = total_rows_written / total_duration if total_duration > 0 else 0.0

        # Construct metrics list
        metrics = [
            BenchmarkMetric(
                metric_type=MetricType.TOTAL_ROWS_WRITTEN,
                value=float(total_rows_written),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.SUCCESSFUL_BATCHES,
                value=float(successful_batches),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.FAILED_BATCHES,
                value=float(failed_batches),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.TOTAL_DURATION_SECONDS,
                value=total_duration,
                unit=MetricUnit.SECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.ROWS_PER_SECOND,
                value=rows_per_second,
                unit=MetricUnit.RECORDS_PER_SECOND,
            ),
            BenchmarkMetric(
                metric_type=MetricType.AVERAGE_BATCH_LATENCY_MS,
                value=avg_latency,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.P50_BATCH_LATENCY_MS,
                value=p50,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.P95_BATCH_LATENCY_MS,
                value=p95,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.P99_BATCH_LATENCY_MS,
                value=p99,
                unit=MetricUnit.MILLISECONDS,
            ),
            # Standard metrics for general report systems
            BenchmarkMetric(
                metric_type=MetricType.WRITE_THROUGHPUT,
                value=rows_per_second,
                unit=MetricUnit.RECORDS_PER_SECOND,
            ),
            BenchmarkMetric(
                metric_type=MetricType.WRITE_LATENCY_MEAN,
                value=avg_latency,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.WRITE_LATENCY_P95,
                value=p95,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.WRITE_LATENCY_P99,
                value=p99,
                unit=MetricUnit.MILLISECONDS,
            ),
        ]

        success = failed_batches <= failure_threshold
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


class BurstWriteLatencyWorkload(BaseWorkload):
    """Workload scenario designed to measure write latency under sudden spikes of telemetry.

    Simulates a fleet operating at a steady baseline telemetry rate, then periodically
    spiking ingestion rates according to a burst multiplier.
    """

    async def execute(self, client: BaseDatabaseClient) -> BenchmarkResult:
        """Runs the burst write latency benchmark loop.

        Args:
            client: An active database client.

        Returns:
            BenchmarkResult containing latency percentiles and burst-specific throughputs.
        """
        # Ensure workload profile is available
        if not self.scenario.workload_profile:
            raise ValueError("Workload profile must be configured for BurstWriteLatencyWorkload")

        wp = self.scenario.workload_profile
        batch_size = wp.batch_size
        warmup_duration = self.scenario.warmup_duration_seconds
        benchmark_duration = self.scenario.benchmark_duration_seconds

        # Configure parameters from profile & metadata
        params = wp.metadata or {}
        failure_threshold = params.get("failure_threshold", 100)

        # Burst parameters
        burst_interval = wp.burst_interval_sec or params.get("burst_interval_sec", 10.0)
        burst_duration = params.get("burst_duration_sec", 2.0)
        burst_multiplier = wp.burst_multiplier or 4.0

        # Base injection rates (records/second)
        drones_count = self.scenario.dataset_profile.simulated_drones
        freq_hz = self.scenario.dataset_profile.telemetry_frequency_hz
        natural_rate = drones_count * freq_hz
        steady_rate = wp.rate_limit_ops_sec or params.get("rate_limit_ops_sec", natural_rate)
        burst_rate = steady_rate * burst_multiplier

        # Initialize deterministic telemetry generator
        from benchmark.core.seed import DeterministicSeedManager

        seed_manager = DeterministicSeedManager(self.scenario.dataset_profile.seed)
        generator = DeterministicTelemetryGenerator(
            seed_manager=seed_manager,
            num_drones=drones_count,
            frequency_hz=freq_hz,
            duration_seconds=warmup_duration + benchmark_duration + 10.0,
            custom_metric_names=None,
        )

        records_stream = generator.stream_records()
        batches = batch_generator(records_stream, batch_size)

        # --- 1. Warm-up Phase ---
        if warmup_duration > 0:
            logger.info("Starting burst write latency warmup", duration=warmup_duration)
            warmup_start = time.perf_counter()
            for batch in batches:
                try:
                    await client.write_telemetry_batch(batch)
                except Exception as e:
                    logger.debug("Error during warmup batch write", error=str(e))

                if time.perf_counter() - warmup_start >= warmup_duration:
                    break

        # --- 2. Burst Latency Benchmarking Phase ---
        logger.info(
            "Starting burst write latency benchmark execution",
            duration=benchmark_duration,
            burst_interval=burst_interval,
            burst_duration=burst_duration,
            burst_multiplier=burst_multiplier,
        )
        # Re-initialize generator/batches to ensure we don't run out of records due to unthrottled warmup
        generator = DeterministicTelemetryGenerator(
            seed_manager=seed_manager,
            num_drones=drones_count,
            frequency_hz=freq_hz,
            duration_seconds=benchmark_duration + 10.0,
            custom_metric_names=None,
            start_time=generator.start_time + timedelta(seconds=warmup_duration),
        )
        records_stream = generator.stream_records()
        batches = batch_generator(records_stream, batch_size)

        successful_batches = 0
        failed_batches = 0
        total_rows_written = 0

        # Burst specific tracking
        rows_written_in_burst = 0
        rows_written_outside_burst = 0
        time_spent_in_burst = 0.0
        time_spent_outside_burst = 0.0

        latencies_ms: list[float] = []
        last_exception: Exception | None = None

        started_at = datetime.now(UTC)
        benchmark_start_timer = time.perf_counter()
        last_step_timer = benchmark_start_timer

        # Concurrent readers execution if configured for mixed workload
        read_task = None
        stop_reads = asyncio.Event()
        read_latencies_ms: list[float] = []
        successful_reads = 0

        qp = self.scenario.query_profile
        if self.scenario.concurrent_readers > 0 and qp is not None:

            async def run_concurrent_reads() -> None:
                nonlocal successful_reads
                local_rand = random.Random(self.scenario.deterministic_random_seed + 1)
                start_time = datetime(2026, 7, 4, 0, 0, 0, tzinfo=UTC)

                patterns = qp.query_patterns or ["time_range_query"]

                while not stop_reads.is_set():
                    pattern = local_rand.choice(patterns)
                    window_size = qp.time_window_seconds
                    max_offset = max(0.0, benchmark_duration - window_size)
                    offset = local_rand.uniform(0.0, max_offset)
                    w_start = start_time + timedelta(seconds=offset)
                    w_end = w_start + timedelta(seconds=window_size)

                    vehicle_idx = local_rand.randint(0, max(0, drones_count - 1))
                    vehicle_id = f"drone_{vehicle_idx:04d}"

                    query_params = {
                        "start_time": w_start,
                        "end_time": w_end,
                        "vehicle_id": vehicle_id,
                        "aggregation_interval_seconds": 60.0,
                    }

                    q_start = time.perf_counter()
                    try:
                        q_name = "time_range_query"
                        if pattern in ("altitude_anomaly_detection", "battery_drain_rate_by_drone_model"):
                            q_name = "aggregation_query"
                        elif pattern == "join_control_plane_metadata":
                            q_name = "join_query"
                        elif pattern in ("time_range_query", "aggregation_query", "historical_replay_query", "join_query"):
                            q_name = pattern

                        await client.execute_query(q_name, query_params)
                        q_lat = (time.perf_counter() - q_start) * 1000.0
                        read_latencies_ms.append(q_lat)
                        successful_reads += 1
                    except Exception as e:
                        logger.debug("Concurrent query failed in mixed workload", error=str(e))

                    await asyncio.sleep(0.05)

            read_task = asyncio.create_task(run_concurrent_reads())

        for batch in batches:
            current_timer = time.perf_counter()
            elapsed = current_timer - benchmark_start_timer

            # Check if currently in burst state
            cycle_elapsed = elapsed % burst_interval
            in_burst = cycle_elapsed < burst_duration

            # Determine rate limit (records/second)
            current_target_rate = burst_rate if in_burst else steady_rate
            # Expected time to process this batch (seconds)
            expected_batch_time = len(batch) / current_target_rate

            # Execute batch write
            batch_start_timer = time.perf_counter()
            try:
                await client.write_telemetry_batch(batch)
                batch_latency = (time.perf_counter() - batch_start_timer) * 1000.0
                latencies_ms.append(batch_latency)
                successful_batches += 1
                total_rows_written += len(batch)

                if in_burst:
                    rows_written_in_burst += len(batch)
                else:
                    rows_written_outside_burst += len(batch)
            except Exception as e:
                batch_latency = (time.perf_counter() - batch_start_timer) * 1000.0
                latencies_ms.append(batch_latency)
                failed_batches += 1
                last_exception = e
                logger.error("Batch write failure in burst workload", error=str(e))
                if failed_batches > failure_threshold:
                    logger.error("Failure threshold exceeded, aborting workload")
                    break

            # Measure step elapsed time
            step_elapsed = time.perf_counter() - last_step_timer
            if in_burst:
                time_spent_in_burst += step_elapsed
            else:
                time_spent_outside_burst += step_elapsed

            # Apply throttling if we processed faster than the target rate allows
            batch_elapsed = time.perf_counter() - batch_start_timer
            if batch_elapsed < expected_batch_time:
                sleep_time = expected_batch_time - batch_elapsed
                await asyncio.sleep(sleep_time)
                # Count sleep time towards the state duration
                if in_burst:
                    time_spent_in_burst += sleep_time
                else:
                    time_spent_outside_burst += sleep_time

            last_step_timer = time.perf_counter()

            if time.perf_counter() - benchmark_start_timer >= benchmark_duration:
                break

        # Stop and await concurrent read task
        stop_reads.set()
        if read_task:
            try:
                await read_task
            except Exception:
                pass

        completed_at = datetime.now(UTC)
        total_duration = time.perf_counter() - benchmark_start_timer

        # Calculate metrics
        avg_latency = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0
        p50 = calculate_percentile(latencies_ms, 50.0)
        p95 = calculate_percentile(latencies_ms, 95.0)
        p99 = calculate_percentile(latencies_ms, 99.0)
        max_latency = max(latencies_ms) if latencies_ms else 0.0

        throughput_burst = (
            rows_written_in_burst / time_spent_in_burst if time_spent_in_burst > 0 else 0.0
        )
        throughput_outside = (
            rows_written_outside_burst / time_spent_outside_burst
            if time_spent_outside_burst > 0
            else 0.0
        )

        metrics = [
            BenchmarkMetric(
                metric_type=MetricType.TOTAL_ROWS_WRITTEN,
                value=float(total_rows_written),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.SUCCESSFUL_BATCHES,
                value=float(successful_batches),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.FAILED_BATCHES,
                value=float(failed_batches),
                unit=MetricUnit.COUNT,
            ),
            BenchmarkMetric(
                metric_type=MetricType.TOTAL_DURATION_SECONDS,
                value=total_duration,
                unit=MetricUnit.SECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.AVERAGE_BATCH_LATENCY_MS,
                value=avg_latency,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.AVERAGE_LATENCY_MS,
                value=avg_latency,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.P50_BATCH_LATENCY_MS,
                value=p50,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.P95_BATCH_LATENCY_MS,
                value=p95,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.P99_BATCH_LATENCY_MS,
                value=p99,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.MAXIMUM_BATCH_LATENCY_MS,
                value=max_latency,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.THROUGHPUT_DURING_BURST,
                value=throughput_burst,
                unit=MetricUnit.RECORDS_PER_SECOND,
            ),
            BenchmarkMetric(
                metric_type=MetricType.THROUGHPUT_OUTSIDE_BURST,
                value=throughput_outside,
                unit=MetricUnit.RECORDS_PER_SECOND,
            ),
        ]

        if read_latencies_ms:
            read_avg = sum(read_latencies_ms) / len(read_latencies_ms)
            read_p95 = calculate_percentile(read_latencies_ms, 95.0)
            read_p99 = calculate_percentile(read_latencies_ms, 99.0)
            read_ops = successful_reads / total_duration if total_duration > 0 else 0.0

            metrics.extend([
                BenchmarkMetric(
                    metric_type=MetricType.READ_THROUGHPUT,
                    value=read_ops,
                    unit=MetricUnit.RECORDS_PER_SECOND,
                ),
                BenchmarkMetric(
                    metric_type=MetricType.READ_LATENCY_MEAN,
                    value=read_avg,
                    unit=MetricUnit.MILLISECONDS,
                ),
                BenchmarkMetric(
                    metric_type=MetricType.READ_LATENCY_P95,
                    value=read_p95,
                    unit=MetricUnit.MILLISECONDS,
                ),
                BenchmarkMetric(
                    metric_type=MetricType.READ_LATENCY_P99,
                    value=read_p99,
                    unit=MetricUnit.MILLISECONDS,
                ),
            ])

        metrics.extend([
            # Standard mappings for base reporting systems
            BenchmarkMetric(
                metric_type=MetricType.WRITE_THROUGHPUT,
                value=total_rows_written / total_duration if total_duration > 0 else 0.0,
                unit=MetricUnit.RECORDS_PER_SECOND,
            ),
            BenchmarkMetric(
                metric_type=MetricType.WRITE_LATENCY_MEAN,
                value=avg_latency,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.WRITE_LATENCY_P95,
                value=p95,
                unit=MetricUnit.MILLISECONDS,
            ),
            BenchmarkMetric(
                metric_type=MetricType.WRITE_LATENCY_P99,
                value=p99,
                unit=MetricUnit.MILLISECONDS,
            ),
        ])

        success = failed_batches <= failure_threshold
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


# Alias to maintain backward compatibility with original stub imports in orchestrator.py
IngestionWorkload = WriteThroughputWorkload
