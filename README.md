# Drone Storage Bench

`drone-storage-bench` is a high-performance database benchmarking utility designed to evaluate and compare timeseries and analytical database technologies under identical, reproducible drone telemetry workloads.

> [!IMPORTANT]
> **Benchmarking Scope Only**: This repository is dedicated exclusively to database evaluation and telemetry ingestion performance metrics. It contains no application frontend, REST APIs, or business logic.

---

## 🛠️ Technology Stack

- **Runtime**: Python 3.13
- **Package Manager**: [uv](https://github.com/astral-sh/uv) (for ultra-fast, reproducible builds)
- **Containerization**: Docker Compose
- **Quality Assurance**: Ruff (Linting/Formatting), mypy (Type Checking), pytest (Unit Testing)
- **Logging**: Structured Logging (`structlog`)

---

## 🏗️ Architecture & Project Structure

The project uses a clean **src layout** and is structured modularly to decouple workload definition, data generation, database drivers, metrics collection, and reporting.

```text
drone-storage-bench/
├── .env.example                       # Reference environment settings
├── .gitignore                         # Git exclusion rules
├── benchmark.yaml                     # Declarative benchmark configuration
├── docker-compose.benchmark.yml       # DB services orchestration file
├── LICENSE                            # MIT License
├── pyproject.toml                     # Project packaging & dependencies
├── README.md                          # Project overview
├── docker/                            # Database config overrides & Dockerfiles
├── docs/                              # Extended design and DB configuration documentation
├── results/                           # Benchmark reports and output artifacts
│   ├── raw/                           # Raw JSON/CSV performance data
│   ├── processed/                     # Aggregate and summary run data
│   └── reports/                       # Generated Markdown/HTML charts
├── src/
│   └── benchmark/
│       ├── __init__.py                # Package root
│       ├── config/                    # Configuration structures and env loading
│       ├── core/                      # Interfaces (DB clients, workloads, seeds)
│       ├── databases/                 # DB-specific client implementations
│       ├── generators/                # Deterministic telemetry data generators
│       ├── metrics/                   # Telemetry write/read collector engine
│       ├── reporting/                 # Charting, tables, and reporting code
│       ├── runners/                   # CLI execution engine and orchestrator
│       ├── scoring/                   # Multi-dimensional database indexing / evaluation
│       ├── utils/                     # Logging configurators and helper methods
│       └── workloads/                 # Concrete benchmark run definition logic
└── tests/                             # Scaffolding and unit test suite
```

---

## 🛢️ Target Databases

We benchmark four leading timeseries/analytical databases under identical write and query patterns. A standard PostgreSQL instance serves strictly as the reference control plane (e.g., to measure `JOIN` efficiency with relational drone metadata).

1. **TimescaleDB**: PostgreSQL-based timeseries database utilizing hypertables and compression.
2. **QuestDB**: High-performance timeseries database optimized for speed using memory-mapped files and a column-oriented model.
3. **ClickHouse**: Columnar analytical database optimized for real-time aggregation and massive insert rates.
4. **InfluxDB 3**: Columnar engine specifically architected for timeseries and telemetry metrics using Apache Arrow.
5. **PostgreSQL** *(Control Plane Reference)*: Used to simulate standard relational schemas and test timeseries-to-control JOIN queries.

---

## 🚀 Getting Started

### Prerequisites

Ensure you have the following installed on your machine:
- **Python 3.13**
- **uv** (Install via `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Docker & Docker Compose**

### 1. Environment Setup

Clone this repository and synchronize the Python virtual environment:
```bash
# Synchronize environment and install dependencies
uv sync
```

Copy the example environment file and adjust target parameters if necessary:
```bash
cp .env.example .env
```

### 2. Start the Target Databases

Spin up all target databases in Docker. The compose configuration applies strict resource constraints to each container (capped at 2.0 CPUs and 4GB RAM to guarantee equal CPU/memory benchmarking environments):
```bash
docker compose -f docker-compose.benchmark.yml up -d
```

Verify that all target containers are up, running, and pass their respective health checks:
```bash
# Check container status and health state
docker compose -f docker-compose.benchmark.yml ps
```

To monitor database logs during startup or benchmark runs:
```bash
# Stream logs for all database targets
docker compose -f docker-compose.benchmark.yml logs -f
```

To teardown the environment and clean data volumes:
```bash
# Stop containers and drop persistent volumes
docker compose -f docker-compose.benchmark.yml down -v
```


---

## 📊 Running Benchmarks

All execution patterns are defined declaratively in `benchmark.yaml`. You can customize the run time, active target databases, concurrency, and workload scenarios there.

Execute the CLI orchestrator stub:
```bash
# Run the benchmark engine
uv run benchmark-cli run --config benchmark.yaml
```

---

## 📈 Workload Methodology

### Sustained Write Throughput Benchmark

The sustained write throughput workload (`WriteThroughputWorkload`) measures the maximum ingestion rate a target database can maintain over a continuous duration under a steady telemetry write workload.

#### Key Mechanics:
1. **Deterministic Telemetry Stream**: The workload streams records on-the-fly from the `DeterministicTelemetryGenerator` using fleet settings from the scenario configuration.
2. **Generator-Based Batching**: Records are accumulated in memory and yielded in blocks matching the configured `batch_size` via a low-overhead utility (`batch_generator`), ensuring minimal memory usage. Remaining records are flushed in a final partial batch at the end.
3. **Warm-up Phase**: An optional, configurable warmup period allows target databases to stabilize caches, initialize connection pools, and trigger initial indexes before throughput counting starts.
4. **Monotonic Timing**: Latencies and durations are measured strictly using monotonic timers (`time.perf_counter()`) to guarantee high-precision results across different operating environments.
5. **Graceful Error Containment**: Individual batch failures increment error counters without aborting execution, unless the number of failed writes exceeds a configurable `failure_threshold` parameter.

#### Collected Metrics:
- `total_rows_written`: Total count of telemetry records successfully written.
- `successful_batches`: Total number of successful batch writes.
- `failed_batches`: Count of failed batch write attempts.
- `total_duration_seconds`: Total active benchmarking time (excluding warmup).
- `rows_per_second`: Average sustained ingestion rate (records/sec).
- `average_batch_latency_ms`: Mean latency to write a single batch.
- `p50_batch_latency_ms`, `p95_batch_latency_ms`, `p99_batch_latency_ms`: Key latency percentiles calculated via linear interpolation.

### Burst Write Latency Benchmark

The burst write latency workload (`BurstWriteLatencyWorkload`) evaluates time-series database write performance under sudden, high-frequency ingestion spikes.

#### Key Mechanics:
1. **Steady vs. Burst States**: The workload schedules ingestion in cyclic intervals (`burst_interval_sec`). Inside each cycle, it spends `burst_duration_sec` in a burst state (ingesting at rate `steady_rate * burst_multiplier`), and the remaining duration in a steady state (ingesting at baseline `steady_rate`).
2. **Rate Throttling (Monotonic Sleep)**: Based on the active state (burst vs. steady), a target rate is calculated. If a batch is processed faster than the target rate allows, the workload sleeps using high-precision monotonic timing (`time.perf_counter()`) to enforce the profile.
3. **Chronological Preservation**: Spikes are simulated by throttling consumption rates rather than altering generator sequences, ensuring telemetry records stay deterministic and chronologically ordered.
4. **State-isolated Throughput**: Records written and time elapsed are tracked separately for burst and steady windows to report isolated throughput rates.

#### Collected Metrics:
- `average_batch_latency_ms`: Mean batch latency across all states.
- `p50_batch_latency_ms`, `p95_batch_latency_ms`, `p99_batch_latency_ms`: Ingestion latency distributions.
- `maximum_batch_latency_ms`: Peak batch latency recorded during run.
- `throughput_during_burst`: Sustained write rate during burst windows (records/sec).
- `throughput_outside_burst`: Sustained write rate during steady-state windows (records/sec).
- `rows_written`, `successful_batches`, `failed_batches`: Overall count metrics.

### Time-Range Query Benchmark

The time-range query workload (`TimeRangeQueryWorkload`) measures database performance for retrieving telemetry data over varying time windows (e.g., 30s, 5m, 30m) representing standard Ground Control Station telemetry logs lookup.

#### Key Mechanics:
1. **Deterministic Input Selection**: Operates on a pre-populated telemetry database. For each iteration, the workload selects a query window size, start offset, and drone vehicle ID using a local random number generator driven by a deterministic seed.
2. **Window Allocation Constraints**: Start times are calculated randomly such that the window fits entirely within the bounds of the loaded dataset.
3. **Execution Safety Limits**: Individual query failures are logged and tracked without aborting the workload, until the total failures count exceeds the configured `failure_threshold`.
4. **Result Rows Auditing**: Evaluates database responsiveness by tracking both the latency metrics and the physical volume of data returned (`rows_returned_average`, `rows_returned_maximum`).

#### Collected Metrics:
- `total_queries`, `successful_queries`, `failed_queries`: Total counts of query attempts, successes, and exceptions.
- `average_latency_ms`, `p50_latency_ms`, `p95_latency_ms`, `p99_latency_ms`: Ingestion latency distributions across query executions.
- `maximum_latency_ms`: The single slowest query execution latency.
- `rows_returned_average`, `rows_returned_maximum`: Average and peak counts of rows returned in query responses.

### Aggregation Query Benchmark

The aggregation query workload (`AggregationQueryWorkload`) measures analytical query performance over pre-loaded telemetry data, exercising calculations like average, minimum, maximum, count, and sum.

#### Key Mechanics:
1. **Deterministic Function and Window Selection**: For each iteration, the query engine selects an aggregation function and time window size randomly from configured lists using a local deterministic random seed.
2. **Dynamic Param Generation**: A random start offset is selected such that the query window fits within the dataset bounds. A random drone vehicle ID is also generated.
3. **Execution Routing**: Sends query requests containing `start_time`, `end_time`, `vehicle_id`, and `aggregation_function` to the database adapter.
4. **Group Returns Auditing**: Computes the average and maximum number of grouped rows/buckets returned by the analytical query (`average_groups_returned`, `maximum_groups_returned`).

#### Collected Metrics:
- `total_queries`, `successful_queries`, `failed_queries`: Total counts of query attempts, successes, and exceptions.
- `average_latency_ms`, `p50_latency_ms`, `p95_latency_ms`, `p99_latency_ms`: Ingestion latency distributions across query executions.
- `maximum_latency_ms`: The single slowest query execution latency.
- `average_groups_returned`, `maximum_groups_returned`: Statistics on the count of groups/buckets returned in the response.

### Historical Replay Benchmark

The historical replay workload (`HistoricalReplayWorkload`) evaluates time-series database query speed when reconstructing a complete drone mission in chronological order.

#### Key Mechanics:
1. **Deterministic Mission Selection**: For each iteration, the workload selects a mission ID randomly from configured inputs or auto-generated lists using a seed manager, unless a single mission is explicitly configured.
2. **Chronological Sorting**: Query configurations enforce sorted retrieval (`sort_order="asc"`) to simulate standard Ground Control Station telemetry replay sequences.
3. **Replay Throughput**: Measures how many rows are retrieved per active query execution second (`replay_throughput_rows_per_second`).
4. **Exception Handling Boundaries**: Fails safely after consecutive query failures exceed the configured `failure_threshold`.

#### Collected Metrics:
- `total_replays`, `successful_replays`, `failed_replays`: Overall replay execution statistics.
- `average_latency_ms`, `p50_latency_ms`, `p95_latency_ms`, `p99_latency_ms`: Ingestion latency distributions across replayed missions.
- `maximum_latency_ms`: The single slowest mission replay latency.
- `rows_returned`: Total accumulated telemetry rows loaded and replayed.
- `replay_throughput_rows_per_second`: Average chronological rows replayed per second.

### Compression Evaluation Benchmark

The compression evaluation workload (`CompressionEvaluationWorkload`) measures database storage efficiency after loading telemetry datasets.

#### Key Mechanics:
1. **Compression Execution**: Triggers database-specific compression mechanisms asynchronously or synchronously by dispatching the command `"compress"` to the adapter.
2. **Logical Size Auditing**: Establishes dataset logical size dynamically based on row count queries (`logical = rows * 128 bytes`), or pulls it from a configured parameter.
3. **Physical Size Querying**: Queries the adapter using `get_storage_size_bytes()` to retrieve active physical disk space.
4. **Efficiency Metrics**: Calculates the compression ratio and saved storage space percentage.

#### Collected Metrics:
- `logical_dataset_size_bytes`: Total byte size of the logical telemetry data.
- `physical_storage_size_bytes`: Disk storage size occupied by compressed tables/collections.
- `compression_ratio`: Ratio of logical size to physical size (higher means better storage efficiency).
- `compression_percentage`: Percentage of storage space saved via compression.
- `compression_duration_ms`: Duration of the trigger compression command call.

### JOIN Evaluation Benchmark

The JOIN evaluation workload (`JoinEvaluationWorkload`) measures the cost of correlating telemetry datasets with control-plane metadata (e.g. drone details, registration tables).

#### Key Mechanics:
1. **Execution Strategies**: Supports two execution models through the database adapter interface:
   - **Native SQL JOIN**: Executed directly inside relationally-aware databases (PostgreSQL/TimescaleDB).
   - **Application-Layer Merge**: Performed by the client driver when time-series engines (QuestDB/ClickHouse/InfluxDB) do not natively support or optimize relational table JOIN operations.
2. **Strategy Auditing**: The adapter returns the strategy used and any elapsed merge/correlation duration to compile statistics.
3. **Deterministic Random Sampling**: Selects vehicle ID, time windows, and start offsets deterministically using seeded random configurations.

#### Collected Metrics:
- `total_queries`, `successful_queries`, `failed_queries`: Total counts of JOIN correlation query executions.
- `average_latency_ms`, `p50_latency_ms`, `p95_latency_ms`, `p99_latency_ms`: Ingestion latency distributions across query executions.
- `maximum_latency_ms`: The single slowest query execution latency.
- `rows_returned`: Total accumulated rows returned by the JOIN query.
- `merge_duration_ms`: Duration of correlation operations spent at the application layer.
- `join_strategy`: Numerical representation of the strategy used (`1.0` for Native, `2.0` for App-layer merge).

### Benchmark Scoring Engine

The scoring engine (`ScoringEngine`) computes comparative, multi-dimensional scorecards and overall weighted rankings for all database targets based on workload metrics.

#### Key Mechanics:
1. **Scenario Weighting**: Loads weight configurations dynamically from `benchmark.yaml`. Active scenario weights are normalized to sum to `1.0` to support custom subsets.
2. **Metric Normalization**: Normalizes raw values to a `[0.0, 100.0]` scale to allow cross-unit comparison:
   - *Higher-is-better* (throughput, compression ratio): `score = (value - min_val) / (max_val - min_val) * 100.0`
   - *Lower-is-better* (latency, physical size): `score = (max_val - value) / (max_val - min_val) * 100.0`
3. **Robust Tie Resolution**: Ranks databases using standard competition rules (e.g. `1, 1, 3`). On score ties, secondary alphabetical sort guarantees deterministic ordering.
4. **Failure Resiliency**: Assigns `0.0` to missing or unsuccessful scenario executions, allowing the rest of the suite scoring to proceed.

#### Configured Default Weights:
- `sustained_write_throughput`: 0.20
- `burst_latency`: 0.15
- `time_range_queries`: 0.15
- `aggregation_queries`: 0.15
- `historical_replay`: 0.15
- `compression`: 0.10
- `join_evaluation`: 0.10

---









## 🧪 Developer Workflow

### Linting & Formatting
We enforce strict style guides via Ruff and type hinting via mypy:
```bash
# Run Ruff lint check
uv run ruff check src/ tests/

# Run Ruff format check
uv run ruff format --check src/ tests/

# Run mypy static type analysis
uv run mypy src/ tests/
```

### Running Tests
Execute the verification tests:
```bash
uv run pytest
```

---

## 📜 License
Distributed under the MIT License. See [LICENSE](file:///Users/somespecies/Desktop/main%20projects/drone-storage-bench/LICENSE) for more information.
