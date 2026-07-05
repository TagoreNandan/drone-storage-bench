from benchmark.config.settings import AppSettings
from benchmark.core.database import BaseDatabaseClient
from benchmark.core.specification import (
    BenchmarkScenario,
    DatasetProfile,
    MetricType,
    ScenarioType,
    WorkloadProfile,
)
from benchmark.core.workload import BaseWorkload
from benchmark.databases.clickhouse import ClickHouseClient
from benchmark.databases.influxdb import InfluxDBClient
from benchmark.databases.postgresql import PostgreSQLClient
from benchmark.databases.questdb import QuestDBClient
from benchmark.databases.timescaledb import TimescaleDBClient
from benchmark.workloads.ingestion import IngestionWorkload
from benchmark.workloads.query import QueryWorkload


def test_database_clients_inherit_base(app_settings: AppSettings) -> None:
    """Verifies that all concrete database client drivers inherit from BaseDatabaseClient."""
    clients = [
        PostgreSQLClient(app_settings),
        TimescaleDBClient(app_settings),
        QuestDBClient(app_settings),
        ClickHouseClient(app_settings),
        InfluxDBClient(app_settings),
    ]

    for client in clients:
        assert isinstance(client, BaseDatabaseClient)
        assert callable(client.connect)
        assert callable(client.disconnect)
        assert callable(client.is_healthy)
        assert callable(client.setup_schema)
        assert callable(client.cleanup_data)
        assert callable(client.write_telemetry_batch)
        assert callable(client.execute_query)
        assert callable(client.get_storage_size_bytes)


def test_workloads_inherit_base() -> None:
    """Verifies that workload implementations inherit from BaseWorkload."""
    dataset = DatasetProfile(
        simulated_drones=10,
        metrics_per_drone=5,
        telemetry_frequency_hz=10.0,
        seed=123,
    )
    workload_profile = WorkloadProfile(batch_size=100)

    scenario = BenchmarkScenario(
        name="test_scenario",
        description="A validation scenario",
        scenario_type=ScenarioType.WRITE_THROUGHPUT,
        warmup_duration_seconds=1.0,
        benchmark_duration_seconds=5.0,
        dataset_profile=dataset,
        workload_profile=workload_profile,
        concurrent_writers=1,
        concurrent_readers=0,
        deterministic_random_seed=42,
        metrics_to_collect=[MetricType.WRITE_THROUGHPUT],
    )

    workloads = [
        IngestionWorkload(scenario),
        QueryWorkload(scenario),
    ]

    for wl in workloads:
        assert isinstance(wl, BaseWorkload)
        assert wl.scenario.name == "test_scenario"
