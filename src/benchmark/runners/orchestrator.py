import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from benchmark.config.settings import AppSettings, BenchmarkYamlConfig
from benchmark.core.database import BaseDatabaseClient
from benchmark.core.runner import BaseWorkloadRunner
from benchmark.core.specification import (
    BenchmarkResult,
    BenchmarkScenario,
    BenchmarkSuite,
    DatasetProfile,
    MetricType,
    QueryProfile,
    ScenarioPriority,
    ScenarioType,
    WorkloadProfile,
)
from benchmark.core.workload import BaseWorkload
from benchmark.databases import DB_CLIENT_REGISTRY
from benchmark.reporting.generator import ReportGenerator
from benchmark.workloads.compression import CompressionEvaluationWorkload
from benchmark.workloads.ingestion import BurstWriteLatencyWorkload, IngestionWorkload
from benchmark.workloads.query import (
    AggregationQueryWorkload,
    HistoricalReplayWorkload,
    JoinEvaluationWorkload,
    QueryWorkload,
    TimeRangeQueryWorkload,
)

logger = structlog.get_logger()


class BenchmarkOrchestrator(BaseWorkloadRunner):
    """Orchestrates database client setup, health check, sequential runs, and report generation."""

    def __init__(self, settings: AppSettings, run_config: BenchmarkYamlConfig) -> None:
        """Initialize the orchestrator."""
        super().__init__(settings, run_config)
        self.suite_results: list[BenchmarkResult] = []

    def _map_config_to_suite(self) -> BenchmarkSuite:
        """Translates the benchmark.yaml config models into a BenchmarkSuite specification."""
        scenarios = []
        global_c = self.run_config.global_config
        metadata = self.run_config.metadata

        for wl in self.run_config.workloads:
            if not wl.enabled:
                continue

            # Map YAML type string to ScenarioType enum
            try:
                s_type = ScenarioType(wl.type)
            except ValueError:
                # Deduce from workload names/types
                if wl.type == "ingestion":
                    s_type = ScenarioType.WRITE_THROUGHPUT
                elif wl.type == "mixed":
                    s_type = ScenarioType.BURST_WRITE_LATENCY
                elif wl.type == "query":
                    s_type = ScenarioType.TIME_RANGE_QUERIES
                else:
                    s_type = ScenarioType.WRITE_THROUGHPUT

            # Ingest vs. Query Profiles setup
            workload_profile = None
            query_profile = None

            is_write_heavy = s_type in (
                ScenarioType.WRITE_THROUGHPUT,
                ScenarioType.BURST_WRITE_LATENCY,
                ScenarioType.HISTORICAL_REPLAY,
                ScenarioType.COMPRESSION_EVALUATION,
            )
            is_read_heavy = s_type in (
                ScenarioType.TIME_RANGE_QUERIES,
                ScenarioType.AGGREGATION_QUERIES,
                ScenarioType.JOIN_EVALUATION,
            )

            if is_write_heavy:
                workload_profile = WorkloadProfile(
                    batch_size=wl.params.get("batch_size", global_c.batch_size),
                    rate_limit_ops_sec=wl.params.get("rate_limit_ops_sec"),
                    is_bursty=s_type == ScenarioType.BURST_WRITE_LATENCY,
                    burst_interval_sec=wl.params.get("burst_interval_sec"),
                    burst_multiplier=wl.params.get("burst_multiplier", 1.0),
                    metadata=wl.params,
                )

            if is_read_heavy:
                query_profile = QueryProfile(
                    query_patterns=wl.params.get("query_patterns", ["latest_position_per_drone"]),
                    time_window_seconds=wl.params.get("time_window_seconds", 300.0),
                    aggregation_interval_seconds=wl.params.get("aggregation_interval_seconds"),
                    enable_joins=s_type == ScenarioType.JOIN_EVALUATION,
                    join_target_table=wl.params.get("join_target_table"),
                    metadata=wl.params,
                )

            # Ensure profiles are initialized to satisfy validator requirements
            concurrent_writers = global_c.concurrency_limit if workload_profile else 0
            concurrent_readers = global_c.concurrency_limit if query_profile else 0

            if concurrent_writers > 0 and workload_profile is None:
                workload_profile = WorkloadProfile(batch_size=global_c.batch_size)
            if concurrent_readers > 0 and query_profile is None:
                query_profile = QueryProfile(query_patterns=["latest"], time_window_seconds=300.0)

            # Deduce metrics to record
            metrics = []
            if workload_profile:
                metrics.extend([MetricType.WRITE_THROUGHPUT, MetricType.WRITE_LATENCY_P95])
            if query_profile:
                metrics.extend([MetricType.READ_THROUGHPUT, MetricType.READ_LATENCY_P95])
            if s_type == ScenarioType.JOIN_EVALUATION:
                metrics.append(MetricType.JOIN_LATENCY_MS)
            if s_type == ScenarioType.COMPRESSION_EVALUATION:
                metrics.append(MetricType.COMPRESSION_RATIO)

            dataset_p = DatasetProfile(
                simulated_drones=wl.params.get("simulated_drones", 100),
                metrics_per_drone=wl.params.get("metrics_per_drone", 30),
                telemetry_frequency_hz=global_c.telemetry_frequency_hz,
                seed=metadata.random_seed,
                total_records=wl.params.get("total_records"),
            )

            scenarios.append(
                BenchmarkScenario(
                    name=wl.name,
                    description=f"Auto-generated configuration for workload {wl.name}",
                    scenario_type=s_type,
                    priority=ScenarioPriority.MEDIUM,
                    warmup_duration_seconds=5.0,
                    benchmark_duration_seconds=float(global_c.duration_seconds),
                    dataset_profile=dataset_p,
                    workload_profile=workload_profile,
                    query_profile=query_profile,
                    concurrent_writers=concurrent_writers,
                    concurrent_readers=concurrent_readers,
                    deterministic_random_seed=metadata.random_seed,
                    metrics_to_collect=metrics,
                )
            )

        return BenchmarkSuite(
            name=metadata.name,
            description=metadata.description,
            global_seed=metadata.random_seed,
            scenarios=scenarios,
        )

    async def execute_suite(self) -> dict[str, Any]:
        """Executes the complete benchmarking suite sequentially across all databases.

        Verifies adapter health checks, loops through database engines and workloads,
        contains exceptions to avoid crashing, and writes structured outputs to results/.
        """
        suite = self._map_config_to_suite()
        logger.info(
            "Mapped benchmark configuration to suite",
            suite_name=suite.name,
            scenarios_count=len(suite.scenarios),
        )

        # 1. Instantiate and verify database targets
        active_clients: dict[str, BaseDatabaseClient] = {}
        for target, target_conf in self.run_config.targets.items():
            if not target_conf.enabled:
                continue

            if target not in DB_CLIENT_REGISTRY:
                logger.warning("Target database not found in client registry", target=target)
                continue

            # Instantiate using global settings
            client_class = DB_CLIENT_REGISTRY[target]
            active_clients[target] = client_class(self.settings)

        # 2. Establish connections and execute health checks
        healthy_clients: dict[str, BaseDatabaseClient] = {}
        for target, client in active_clients.items():
            logger.info("Initializing database client connection", target=target)
            try:
                await client.connect()
                if await client.is_healthy():
                    healthy_clients[target] = client
                    logger.info("Database client connection verified healthy", target=target)
                else:
                    logger.error("Database health check failed", target=target)
                    await client.disconnect()
            except Exception as e:
                logger.exception(
                    "Failed to connect to database client", target=target, error=str(e)
                )

        # 3. Sequentially run benchmark scenarios
        try:
            for scenario in suite.scenarios:
                logger.info("Executing benchmark scenario", scenario=scenario.name)

                for target, client in healthy_clients.items():
                    logger.info(
                        "Running scenario against database", target=target, scenario=scenario.name
                    )
                    start_time = datetime.now(UTC)

                    try:
                        # Initialize schema
                        await client.setup_schema()

                        # Warmup phase
                        logger.info(
                            "Starting scenario warmup", duration=scenario.warmup_duration_seconds
                        )
                        # Cap sleep for speed during testing
                        await asyncio.sleep(min(scenario.warmup_duration_seconds, 0.1))

                        # Deduce and run workload stub
                        workload: BaseWorkload
                        is_write = scenario.concurrent_writers > 0
                        if is_write:
                            if scenario.scenario_type == ScenarioType.BURST_WRITE_LATENCY:
                                workload = BurstWriteLatencyWorkload(scenario)
                            else:
                                workload = IngestionWorkload(scenario)
                        else:
                            if scenario.scenario_type == ScenarioType.TIME_RANGE_QUERIES:
                                workload = TimeRangeQueryWorkload(scenario)
                            elif scenario.scenario_type == ScenarioType.AGGREGATION_QUERIES:
                                workload = AggregationQueryWorkload(scenario)
                            elif scenario.scenario_type == ScenarioType.HISTORICAL_REPLAY:
                                workload = HistoricalReplayWorkload(scenario)
                            elif scenario.scenario_type == ScenarioType.COMPRESSION_EVALUATION:
                                workload = CompressionEvaluationWorkload(scenario)
                            elif scenario.scenario_type == ScenarioType.JOIN_EVALUATION:
                                workload = JoinEvaluationWorkload(scenario)
                            else:
                                workload = QueryWorkload(scenario)

                        # Delegate execution to workload runner
                        logger.info("Invoking workload execution")
                        result = await self.run(client, workload)
                        self.suite_results.append(result)

                    except Exception as e:
                        logger.exception(
                            "Workload execution failed gracefully",
                            target=target,
                            scenario=scenario.name,
                            error=str(e),
                        )
                        # Record a failed run rather than crash
                        self.suite_results.append(
                            BenchmarkResult(
                                database_name=client.__class__.__name__,
                                scenario_name=scenario.name,
                                scenario_type=scenario.scenario_type,
                                started_at=start_time,
                                completed_at=datetime.now(UTC),
                                metrics=[],
                                success=False,
                                error_message=f"Scenario execution failed: {e!s}",
                            )
                        )
                    finally:
                        # In-between runs data cleanup to isolate runs
                        try:
                            await client.cleanup_data()
                        except Exception as e:
                            logger.error("Failed to run data cleanup", target=target, error=str(e))

                    # Cooldown interval
                    cooldown = self.run_config.global_config.cooldown_seconds
                    logger.info("Starting cooldown period", duration=cooldown)
                    await asyncio.sleep(min(cooldown, 0.1))  # Cap sleep for speed

        finally:
            # 4. Gracefully close connections
            for target, client in healthy_clients.items():
                try:
                    await client.disconnect()
                except Exception as e:
                    logger.error(
                        "Failed to disconnect database client", target=target, error=str(e)
                    )

        # 5. Export structured reports
        results_dir_path = Path(self.settings.results_dir)
        report_gen = ReportGenerator(results_dir_path)

        timestamp_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        json_filename = f"{suite.name}_{timestamp_str}.json"
        md_filename = f"{suite.name}_{timestamp_str}.md"

        json_path = report_gen.generate_json_results(self.suite_results, json_filename)
        md_path = report_gen.generate_markdown_summary(self.suite_results, md_filename)

        logger.info(
            "Structured reports written",
            json_report=str(json_path),
            markdown_report=str(md_path),
        )

        return {
            "suite_name": suite.name,
            "results": [res.model_dump(mode="json") for res in self.suite_results],
        }

    async def run(self, client: BaseDatabaseClient, workload: BaseWorkload) -> BenchmarkResult:
        """Runs the specified workload against a database target."""
        # Coordinating execution by calling the workload executor
        return await workload.execute(client)
