# Drone Storage Bench - Architecture Documentation

## Core Design Principles

1. **Isolation**: Workload specifications (`workloads/`) are fully decoupled from database connection and execution details (`databases/`). This ensures that TimescaleDB, QuestDB, ClickHouse, and InfluxDB 3 are subjected to the exact same access patterns, metrics measurements, and limits.
2. **Reproducibility**: All random generations (timestamps, metrics values, simulated drone telemetry paths, query parameter distributions) are driven by a deterministic sub-seed derived from a single global root seed (`DeterministicSeedManager`).
3. **Structured Ingestion**: Telemetry generation relies on a declarative framework. High-frequency updates are aggregated into batches and written as blocks to measure write efficiency.
4. **Relational Correlation Control**: PostgreSQL is included as a baseline comparison target specifically to measure timeseries-to-control metadata JOIN queries.

## Component Layout & Relationships

```mermaid
graph TD
    CLI[runners/cli.py] --> Orchestrator[runners/orchestrator.py]
    Orchestrator --> Config[config/settings.py]
    Orchestrator --> Seed[core/seed.py]
    Orchestrator --> Metrics[metrics/collector.py]
    
    Orchestrator --> DatabaseClient[core/database.py]
    Orchestrator --> Workload[core/workload.py]
    
    DatabaseClient <|-- PostgreSQLClient[databases/postgresql.py]
    DatabaseClient <|-- TimescaleClient[databases/timescaledb.py]
    DatabaseClient <|-- QuestClient[databases/questdb.py]
    DatabaseClient <|-- ClickHouseClient[databases/clickhouse.py]
    DatabaseClient <|-- InfluxClient[databases/influxdb.py]
    
    Workload <|-- IngestionWorkload[workloads/ingestion.py]
    Workload <|-- QueryWorkload[workloads/query.py]
    
    IngestionWorkload --> TelemetryGenerator[generators/telemetry.py]
    
    Orchestrator --> Scoring[scoring/engine.py]
    Orchestrator --> Reporting[reporting/generator.py]
```

## Setup & Running Flow

1. **CLI Run Command**: User invokes `benchmark-cli run --config benchmark.yaml`.
2. **Settings Initialization**: The application parses environment variables (`.env`) and reads the YAML profile to generate configuration structures.
3. **Connection Phase**: For each enabled target database, the Orchestrator instantiates the driver, establishes connections, and executes DDL scripts (`setup_schema`).
4. **Workload Phase**:
   - The workload pulls data from `BaseTelemetryGenerator` (seeding workers with deterministic sub-seeds).
   - Ingestion batches are written to the database client asynchronously.
   - Operations are measured for latency, outcome status, and throughput.
5. **Cooldown Phase**: A configurable sleep duration occurs between database trials to prevent thermal throttling or background thread interference.
6. **Reporting Phase**: Summarized stats are normalized into score indexes, JSON artifacts are output to `results/raw/`, and a comparative markdown report is compiled to `results/reports/`.
