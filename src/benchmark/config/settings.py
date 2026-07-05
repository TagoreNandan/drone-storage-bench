from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PostgresSettings(BaseModel):
    """PostgreSQL connection details (used as control plane reference)."""

    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str = "postgres_dev_password"
    database: str = "control_plane"

class MySQLSettings(BaseModel):
    """MySQL connection details."""

    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = "mysql_dev_password"
    database: str = "control_plane"

class MongoDBSettings(BaseModel):
    """MongoDB connection details."""

    host: str = "localhost"
    port: int = 27017
    user: str = "root"
    password: str = "mongodb_dev_password"
    database: str = "drone_telemetry"

class DynamoDBSettings(BaseModel):
    """DynamoDB Local connection details."""

    endpoint_url: str = "http://localhost:8000"
    region: str = "us-east-1"
    access_key: str = "dummy"
    secret_key: str = "dummy"
    table_name: str = "drone_telemetry"


class TimescaleSettings(BaseModel):
    """TimescaleDB connection details."""

    host: str = "localhost"
    port: int = 5433
    user: str = "postgres"
    password: str = "timescale_dev_password"
    database: str = "drone_telemetry"


class QuestSettings(BaseModel):
    """QuestDB connection details."""

    host: str = "localhost"

    # PGWire (used by asyncpg)
    port: int = 8812
    user: str = "admin"
    password: str = "quest"
    database: str = "qdb"

    # Other interfaces (kept for future use)
    port_http: int = 9000
    port_ilp: int = 9009


class ClickHouseSettings(BaseModel):
    """ClickHouse connection details supporting HTTP and native protocols."""

    host: str = "localhost"
    port_http: int = 8123
    port_native: int = 9000
    user: str = "default"
    password: str = "clickhouse_dev_password"
    database: str = "drone_telemetry"


class InfluxSettings(BaseModel):
    """InfluxDB 3 connection details."""

    host: str = "localhost"
    port: int = 8086
    token: str = "influxdb_dev_token_very_long_string_here"
    org: str = "drone_org"
    database: str = "drone_telemetry"


class AppSettings(BaseSettings):
    """Global application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    log_level: str = "INFO"
    random_seed: int = 42
    benchmark_config_path: str = "benchmark.yaml"
    results_dir: str = "./results"

    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    timescaledb: TimescaleSettings = Field(default_factory=TimescaleSettings)
    questdb: QuestSettings = Field(default_factory=QuestSettings)
    clickhouse: ClickHouseSettings = Field(default_factory=ClickHouseSettings)
    influxdb: InfluxSettings = Field(default_factory=InfluxSettings)
    mysql: MySQLSettings = Field(default_factory=MySQLSettings)
    mongodb: MongoDBSettings = Field(default_factory=MongoDBSettings)
    dynamodb: DynamoDBSettings = Field(default_factory=DynamoDBSettings)


# YAML Configuration Models (for benchmark.yaml definitions)


class BenchmarkMetadata(BaseModel):
    """Declarative benchmark run metadata."""

    name: str
    description: str
    version: str
    random_seed: int


class TargetConfig(BaseModel):
    """Status control and overrides for a target database."""

    enabled: bool
    connection_override: str | None = None


class GlobalConfig(BaseModel):
    """Global constraints and telemetry parameters for a benchmark run."""

    duration_seconds: int
    concurrency_limit: int
    cooldown_seconds: int
    batch_size: int
    telemetry_frequency_hz: float


class WorkloadConfig(BaseModel):
    """Scenarios / Workload configurations to run."""

    name: str
    type: str
    enabled: bool
    params: dict[str, Any] = Field(default_factory=dict)


class ScoringWeightsConfig(BaseModel):
    """Scoring weights for each benchmark scenario type."""

    sustained_write_throughput: float = 0.2
    burst_latency: float = 0.15
    time_range_queries: float = 0.15
    aggregation_queries: float = 0.15
    historical_replay: float = 0.15
    compression: float = 0.1
    join_evaluation: float = 0.1


class BenchmarkYamlConfig(BaseModel):
    """Structure parsing the benchmark.yaml file."""

    metadata: BenchmarkMetadata
    global_config: GlobalConfig = Field(..., alias="global")
    targets: dict[str, TargetConfig]
    workloads: list[WorkloadConfig]
    scoring_weights: ScoringWeightsConfig = Field(default_factory=ScoringWeightsConfig)

    @classmethod
    def load_from_yaml(cls, path: Path | str) -> "BenchmarkYamlConfig":
        """Loads and validates configuration from a YAML file.

        TODO: Implement robust error handling for missing/malformed configuration files.
        """
        with Path(path).open() as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)
