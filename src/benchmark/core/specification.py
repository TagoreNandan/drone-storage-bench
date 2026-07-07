from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScenarioPriority(IntEnum):
    """Priority level for executing a benchmark scenario."""

    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3


class MetricUnit(StrEnum):
    """Standardized units of measure for metrics collected."""

    OPERATIONS_PER_SECOND = "ops/sec"
    RECORDS_PER_SECOND = "rec/sec"
    MILLISECONDS = "ms"
    SECONDS = "sec"
    BYTES = "bytes"
    MEGABYTES = "MB"
    PERCENT = "percent"
    COUNT = "count"


class MetricType(StrEnum):
    """Supported telemetry and database metrics."""

    WRITE_THROUGHPUT = "write_throughput"
    WRITE_LATENCY_MEAN = "write_latency_mean"
    WRITE_LATENCY_P95 = "write_latency_p95"
    WRITE_LATENCY_P99 = "write_latency_p99"
    READ_THROUGHPUT = "read_throughput"
    READ_LATENCY_MEAN = "read_latency_mean"
    READ_LATENCY_P95 = "read_latency_p95"
    READ_LATENCY_P99 = "read_latency_p99"
    CPU_UTILIZATION_PERCENT = "cpu_utilization_percent"
    MEMORY_UTILIZATION_MB = "memory_utilization_mb"
    DISK_SIZE_BYTES = "disk_size_bytes"
    JOIN_LATENCY_MS = "join_latency_ms"
    COMPRESSION_RATIO = "compression_ratio"
    ERROR_COUNT = "error_count"

    # Compression Evaluation Metrics
    LOGICAL_DATASET_SIZE_BYTES = "logical_dataset_size_bytes"
    PHYSICAL_STORAGE_SIZE_BYTES = "physical_storage_size_bytes"
    COMPRESSION_PERCENTAGE = "compression_percentage"
    COMPRESSION_DURATION_MS = "compression_duration_ms"

    # Sustained Write Throughput Metrics
    TOTAL_ROWS_WRITTEN = "total_rows_written"
    SUCCESSFUL_BATCHES = "successful_batches"
    FAILED_BATCHES = "failed_batches"
    TOTAL_DURATION_SECONDS = "total_duration_seconds"
    ROWS_PER_SECOND = "rows_per_second"
    AVERAGE_BATCH_LATENCY_MS = "average_batch_latency_ms"
    P50_BATCH_LATENCY_MS = "p50_batch_latency_ms"
    P95_BATCH_LATENCY_MS = "p95_batch_latency_ms"
    P99_BATCH_LATENCY_MS = "p99_batch_latency_ms"
    MAXIMUM_BATCH_LATENCY_MS = "maximum_batch_latency_ms"
    THROUGHPUT_DURING_BURST = "throughput_during_burst"
    THROUGHPUT_OUTSIDE_BURST = "throughput_outside_burst"

    # Time-Range Query Metrics
    TOTAL_QUERIES = "total_queries"
    SUCCESSFUL_QUERIES = "successful_queries"
    FAILED_QUERIES = "failed_queries"
    AVERAGE_LATENCY_MS = "average_latency_ms"
    P50_LATENCY_MS = "p50_latency_ms"
    P95_LATENCY_MS = "p95_latency_ms"
    P99_LATENCY_MS = "p99_latency_ms"
    MAXIMUM_LATENCY_MS = "maximum_latency_ms"
    ROWS_RETURNED_AVERAGE = "rows_returned_average"
    ROWS_RETURNED_MAXIMUM = "rows_returned_maximum"
    AVERAGE_GROUPS_RETURNED = "average_groups_returned"
    MAXIMUM_GROUPS_RETURNED = "maximum_groups_returned"

    # Historical Replay Metrics
    TOTAL_REPLAYS = "total_replays"
    SUCCESSFUL_REPLAYS = "successful_replays"
    FAILED_REPLAYS = "failed_replays"
    REPLAY_THROUGHPUT_ROWS_PER_SECOND = "replay_throughput_rows_per_second"
    ROWS_RETURNED = "rows_returned"

    # JOIN Evaluation Metrics
    MERGE_DURATION_MS = "merge_duration_ms"
    JOIN_STRATEGY = "join_strategy"


class BenchmarkMetric(BaseModel):
    """A single captured metric data point."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metric_type: MetricType
    value: float | None = None
    unit: MetricUnit
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetProfile(BaseModel):
    """Configuration defining telemetry payload structure and parameters."""

    model_config = ConfigDict(frozen=True)

    simulated_drones: int = Field(..., gt=0, description="Number of unique drone IDs to simulate.")
    metrics_per_drone: int = Field(
        ..., gt=0, description="Number of distinct measurements emitted per drone."
    )
    telemetry_frequency_hz: float = Field(..., gt=0.0, description="Emissions frequency in Hz.")
    payload_schema_version: str = Field("1.0.0", description="Version of the telemetry schema.")
    seed: int = Field(..., description="Deterministic seed for mock data generation.")
    total_records: int | None = Field(
        None, gt=0, description="Optional hard cap on total telemetry records to generate."
    )


class WorkloadProfile(BaseModel):
    """Behavior of write-heavy operations, concurrency, and injection rate."""

    model_config = ConfigDict(frozen=True)

    batch_size: int = Field(..., gt=0, description="Size of insert block.")
    rate_limit_ops_sec: int | None = Field(None, gt=0, description="Optional throttle on writes.")
    is_bursty: bool = Field(False, description="Whether to simulate burst telemetry profiles.")
    burst_interval_sec: float | None = Field(
        None, gt=0.0, description="Time interval between ingestion spikes."
    )
    burst_multiplier: float = Field(1.0, ge=1.0, description="Multiplier applied during a burst.")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary custom parameters."
    )


class QueryProfile(BaseModel):
    """Access profile defining query operations, windows, and relational JOIN operations."""

    model_config = ConfigDict(frozen=True)

    query_patterns: list[str] = Field(..., description="Query templates / identifiers to execute.")
    time_window_seconds: float = Field(
        ..., gt=0.0, description="Time-range window to filter in query."
    )
    aggregation_interval_seconds: float | None = Field(
        None, gt=0.0, description="Aggregation window (e.g. 5m bucket)."
    )
    enable_joins: bool = Field(
        False, description="Whether to execute SQL JOINs with control-plane."
    )
    join_target_table: str | None = Field(
        None, description="Name of the control-plane relational table to JOIN against."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary custom parameters."
    )


class ScenarioType(StrEnum):
    """Standardized benchmark scenarios supported by the runner."""

    WRITE_THROUGHPUT = "write_throughput"
    BURST_WRITE_LATENCY = "burst_write_latency"
    TIME_RANGE_QUERIES = "time_range_queries"
    AGGREGATION_QUERIES = "aggregation_queries"
    HISTORICAL_REPLAY = "historical_replay"
    COMPRESSION_EVALUATION = "compression_evaluation"
    JOIN_EVALUATION = "join_evaluation"


class ExpectedOutputSpec(BaseModel):
    """Declarative specification describing expected outputs shape and validation rules."""

    model_config = ConfigDict(frozen=True)

    required_fields: list[str] = Field(
        default_factory=list, description="Fields required in query outputs."
    )
    expected_row_count: int | None = Field(
        None, ge=0, description="Expected row count returned, if fixed."
    )
    schema_definition: dict[str, str] = Field(
        default_factory=dict, description="Field name to type mappings for validation."
    )


class BenchmarkScenario(BaseModel):
    """Complete specification of a database-agnostic benchmark run configuration."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., min_length=3, description="Name of the scenario.")
    description: str = Field(..., description="Description of scenario goals.")
    scenario_type: ScenarioType = Field(..., description="Category of benchmark scenario.")
    priority: ScenarioPriority = Field(
        ScenarioPriority.MEDIUM, description="Scenario running order."
    )
    warmup_duration_seconds: float = Field(
        ..., ge=0.0, description="Warm-up phase before recording results."
    )
    benchmark_duration_seconds: float = Field(..., gt=0.0, description="Recorded test duration.")
    dataset_profile: DatasetProfile = Field(..., description="Dataset shape details.")
    workload_profile: WorkloadProfile | None = Field(
        None, description="Ingestion properties (if write is involved)."
    )
    query_profile: QueryProfile | None = Field(
        None, description="Read properties (if query is involved)."
    )
    concurrent_writers: int = Field(..., ge=0, description="Number of parallel write tasks.")
    concurrent_readers: int = Field(..., ge=0, description="Number of parallel query tasks.")
    deterministic_random_seed: int = Field(..., description="Specific seed for reproducibility.")
    metrics_to_collect: list[MetricType] = Field(
        ..., description="Metrics collected in this scenario."
    )
    expected_outputs: ExpectedOutputSpec = Field(
        default_factory=lambda: ExpectedOutputSpec(),
        description="Out shape specification for validation.",
    )

    @model_validator(mode="after")
    def validate_scenario_requirements(self) -> "BenchmarkScenario":
        """Ensures that writers/readers match the workload/query profiles requested."""
        if self.concurrent_writers > 0 and self.workload_profile is None:
            raise ValueError("Workload profile must be configured if concurrent writers > 0.")
        if self.concurrent_readers > 0 and self.query_profile is None:
            raise ValueError("Query profile must be configured if concurrent readers > 0.")
        if self.scenario_type == ScenarioType.JOIN_EVALUATION and (
            self.query_profile is None or not self.query_profile.enable_joins
        ):
            raise ValueError(
                "Query profile enable_joins must be True for JOIN_EVALUATION scenario."
            )
        return self


class BenchmarkSuite(BaseModel):
    """A collection of BenchmarkScenarios constituting a comparative run."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., min_length=3)
    description: str
    global_seed: int
    scenarios: list[BenchmarkScenario] = Field(..., description="Scenarios included in the suite.")

    @model_validator(mode="after")
    def validate_unique_scenario_names(self) -> "BenchmarkSuite":
        """Asserts that all scenarios within the suite have distinct names."""
        names = [s.name for s in self.scenarios]
        if len(names) != len(set(names)):
            raise ValueError("All scenario names within a BenchmarkSuite must be unique.")
        return self


class BenchmarkResult(BaseModel):
    """Immutable result metadata captured from executing a scenario against a database."""

    model_config = ConfigDict(frozen=True)

    database_name: str
    scenario_name: str
    scenario_type: ScenarioType
    started_at: datetime
    completed_at: datetime
    metrics: list[BenchmarkMetric] = Field(default_factory=list)
    success: bool
    error_message: str | None = None


class TelemetryRecord(BaseModel):
    """Immutable simulated drone telemetry data record."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime = Field(..., description="Timestamp of telemetry collection.")
    vehicle_id: str = Field(..., description="Unique identifier of the drone.")
    mission_id: str = Field(..., description="Identifier of the current flight mission.")
    latitude: float = Field(..., description="GPS Latitude in decimal degrees.")
    longitude: float = Field(..., description="GPS Longitude in decimal degrees.")
    altitude: float = Field(..., description="Altitude in meters above sea level.")
    roll: float = Field(..., description="Vehicle roll angle in degrees.")
    pitch: float = Field(..., description="Vehicle pitch angle in degrees.")
    yaw: float = Field(..., description="Vehicle yaw angle in degrees.")
    velocity: float = Field(..., ge=0.0, description="Velocity of the vehicle in m/s.")
    battery_percentage: float = Field(
        ..., ge=0.0, le=100.0, description="Remaining battery life percent."
    )
    custom_metrics: dict[str, float] = Field(
        default_factory=dict, description="Configurable extra parameters (e.g. TUNNEL metrics)."
    )
