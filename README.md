<div align="center">

# 🚁 Drone Storage Bench

### A Reproducible Database Benchmarking Framework for High-Frequency Drone Telemetry Workloads

# Quick Start

## Prerequisites

- Docker Desktop

## Run

```bash
cp .env.example .env
docker compose up --build
```

Reports are generated under:

```
results/raw/
results/reports/
results/charts/
```

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/Tests-58%20Passing-success.svg)]()
[![Ruff](https://img.shields.io/badge/Ruff-Passing-success.svg)]()
[![Mypy](https://img.shields.io/badge/Mypy-Strict-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()

Evaluate SQL, NoSQL, OLAP, and Time-Series databases under identical UAV telemetry workloads using a unified benchmarking framework.

</div>

---

# Overview

Drone Storage Bench is a reproducible benchmarking framework designed to compare multiple database technologies under realistic high-frequency drone telemetry workloads.

Modern UAV systems continuously generate GPS coordinates, altitude, orientation, velocity, battery statistics, and mission metadata at very high frequencies. Choosing the appropriate storage engine requires objective evaluation rather than assumptions.

This framework executes identical workloads across multiple database systems through a common abstraction layer, ensuring fair comparisons of:

- Sustained ingestion throughput
- Mixed read/write performance
- Analytical query execution
- Storage efficiency
- Resource utilization
- Overall database behavior

The project was designed with reproducibility, modularity, and automation as primary goals.

---

# Key Features

- Unified database abstraction layer
- Modular adapter architecture
- Fully asynchronous benchmark execution
- Declarative benchmark configuration
- Docker-based deployment
- Automatic scoring engine
- Deterministic telemetry generation
- JSON report generation
- Markdown report generation
- Interactive HTML reports
- Automatic performance charts
- Strict static typing (Mypy)
- Ruff formatting & linting
- Comprehensive unit testing
- Production-ready project structure

---

# Supported Databases

| Database | Category | Status |
|-----------|----------|--------|
| PostgreSQL | Relational | ✅ |
| MySQL | Relational | ✅ |
| TimescaleDB | Time-Series | ✅ |
| QuestDB | Time-Series | ✅ |
| ClickHouse | OLAP | ✅ |
| InfluxDB | Time-Series | ✅ |
| MongoDB | Document | ✅ |
| DynamoDB Local | Key-Value | ✅ |

---

# High-Level Architecture

```text
                     benchmark.yaml
                            │
                            ▼
                Configuration Loader
                            │
                            ▼
                Benchmark Orchestrator
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   Workload Engine    Database Adapters   Resource Monitor
        │                   │                   │
        └───────────────────┼───────────────────┘
                            ▼
                  Metrics Collection
                            │
                            ▼
                    Scoring Engine
                            │
                            ▼
      JSON Reports • Markdown • HTML • Charts
```

---

# Repository Structure

```text
drone-storage-bench/

├── src/
│   └── benchmark/
│       ├── config/
│       ├── core/
│       ├── databases/
│       ├── generators/
│       ├── metrics/
│       ├── reporting/
│       ├── runners/
│       ├── scoring/
│       ├── utils/
│       └── workloads/
│
├── tests/
│
├── docker/
│
├── docs/
│
├── results/
│   ├── raw/
│   ├── reports/
│   └── charts/
│
├── Dockerfile
├── docker-compose.yml
├── benchmark.yaml
├── pyproject.toml
└── README.md
```

---

# Benchmark Workloads

The benchmark framework currently evaluates databases using four primary workload categories.

## 1. Write Heavy Ingestion

Simulates continuous ingestion of high-frequency drone telemetry.

Measured metrics:

- Throughput
- Average write latency
- Peak latency
- Failed batches

---

## 2. Mixed Telemetry Load

Simulates concurrent reads while telemetry is continuously written.

Measured metrics:

- Read latency
- Write latency
- Throughput
- Concurrent stability

---

## 3. Analytical Aggregation Queries

Executes analytical SQL/NoSQL aggregation workloads over stored telemetry.

Examples include:

- Average battery consumption
- Altitude statistics
- Vehicle grouping
- Mission aggregation

Measured metrics:

- Query latency
- Rows processed
- Query throughput

---

## 4. Storage Compression Evaluation

Measures storage efficiency after telemetry ingestion.

Measured metrics:

- Logical dataset size
- Physical storage size
- Compression ratio
- Compression percentage
- Compression duration
---

# Installation

Clone the repository:

```bash
git clone https://github.com/TagoreNandan/drone-storage-bench.git

cd drone-storage-bench
```

Install project dependencies using **uv**:

```bash
uv sync
```

---

# Docker Support

The project is fully containerized using Docker Compose.

Running a single command automatically:

- Builds the benchmark runner image
- Starts every supported database
- Waits until all databases become healthy
- Executes the benchmark suite
- Generates reports and charts
- Stores results on the host machine

No manual database installation is required.

---

# Running the Benchmark

## Option 1 — Fully Containerized (Recommended)

Build the benchmark runner and all database services:

```bash
docker compose up --build
```

This command automatically:

- Builds the Docker image
- Starts PostgreSQL
- Starts MySQL
- Starts TimescaleDB
- Starts QuestDB
- Starts ClickHouse
- Starts MongoDB
- Starts InfluxDB
- Starts DynamoDB Local
- Waits for health checks
- Executes all enabled benchmark workloads
- Generates benchmark reports

After completion the generated artifacts are available inside:

```text
results/
```

---

## Option 2 — Local Development using uv

Start only the databases:

```bash
docker compose up -d
```

Run the benchmark locally:

```bash
uv run python -m benchmark.runners.cli run
```

This mode is useful while developing or debugging workloads without rebuilding the benchmark container.

---

# Benchmark Configuration

The benchmark behavior is controlled entirely through:

```text
benchmark.yaml
```

Configuration options include:

- Benchmark duration
- Batch size
- Drone count
- Telemetry frequency
- Enabled databases
- Enabled workloads
- Concurrency
- Cooldown duration
- Scoring weights

No source code modifications are required to change benchmark behavior.

---

# Generated Reports

Each benchmark execution automatically generates multiple artifacts.

## Raw Results

```text
results/raw/
```

Contains structured JSON benchmark metrics suitable for further analysis.

---

## Markdown Report

```text
results/reports/
```

A GitHub-friendly benchmark summary is generated automatically.

The report includes:

- Database rankings
- Per-workload metrics
- Overall scores
- Summary tables

This report can be viewed directly on GitHub.

---

## Interactive HTML Report

```text
results/reports/
```

The framework also generates a responsive HTML report containing:

- Benchmark metadata
- Overall rankings
- Performance dashboards
- Interactive charts
- Storage comparisons
- Compression statistics
- Workload summaries

The HTML report can be opened in any modern browser.

---

## Performance Charts

```text
results/charts/
```

Visualization includes charts such as:

- Overall database rankings
- Throughput comparison
- Query latency comparison
- Radar comparison
- Storage footprint
- Compression efficiency

These figures are generated automatically after every benchmark execution.

---

# Running Tests

Run the complete test suite:

```bash
uv run pytest
```

Current project status:

```text
58 tests passed
```

---

# Static Analysis

## Ruff

Check linting:

```bash
uv run ruff check .
```

Format source code:

```bash
uv run ruff format .
```

---

## MyPy

Run strict type checking:

```bash
uv run mypy src
```

The project is developed with strict static typing enabled.

---

# Reproducibility

To ensure consistent benchmark execution, the framework provides:

- Deterministic random seed generation
- Declarative benchmark configuration
- Consistent telemetry generation
- Fixed workload definitions
- Automated Docker deployment
- Health-checked database startup

These features allow benchmark runs to be reproduced across different environments while keeping workload behavior consistent.

---

# Quality Assurance

The framework includes:

- 58 automated unit tests
- Ruff formatting
- Ruff linting
- Strict MyPy type checking
- Docker health checks
- Deterministic benchmark generation
- Automated report generation
- Continuous Integration workflow

---

# Future Improvements

Planned enhancements include:

- Kubernetes deployment
- Distributed benchmarking
- Grafana dashboards
- Prometheus metrics export
- Cloud-native benchmark execution
- Additional database adapters
- Extended analytical workloads

---

# License

This project is released under the MIT License.

---

# Author

**Tagore Nandan**

B.Tech Computer Science

Areas of Interest:

- Database Systems
- Distributed Systems
- Performance Engineering
- Cloud Computing
- Backend Systems

---

# Acknowledgements

This project makes use of several outstanding open-source technologies:

- PostgreSQL
- MySQL
- TimescaleDB
- QuestDB
- ClickHouse
- InfluxDB
- MongoDB
- DynamoDB Local
- Docker
- Python
- uv
- Ruff
- MyPy
- Pytest

---

<div align="center">

**Drone Storage Bench** provides a reproducible framework for evaluating modern database technologies under realistic UAV telemetry workloads, enabling fair, configurable, and repeatable performance comparisons.

</div>
