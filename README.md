<div align="center">

# 🚁 Drone Storage Bench

### Production-Grade Database Benchmarking Framework for High-Frequency Drone Telemetry Workloads

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/Tests-55%20Passing-success.svg)]()
[![Ruff](https://img.shields.io/badge/Ruff-Passing-success.svg)]()
[![Mypy](https://img.shields.io/badge/Mypy-Strict-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()

Compare SQL, NoSQL, and Time-Series databases under identical drone telemetry workloads using a unified benchmarking framework.

</div>

---

# Overview

Drone Storage Bench is a production-quality benchmarking framework designed to evaluate database technologies under realistic, high-frequency drone telemetry workloads.

Modern UAV systems continuously generate large volumes of telemetry data including GPS coordinates, altitude, orientation, velocity, battery statistics, and mission metadata. Selecting an appropriate database for storing and querying this information requires objective performance evaluation rather than assumptions.

This framework executes identical benchmark scenarios across multiple database systems using a common abstraction layer, ensuring fair comparison of ingestion performance, query latency, analytical workloads, storage efficiency, and overall database behavior.

---

# Key Features

- Modular adapter-based architecture
- Unified database interface
- Asynchronous benchmark execution
- Dockerized deployment
- Configurable benchmark scenarios
- Automated scoring engine
- JSON report generation
- Markdown report generation
- Automatic visualization support
- Strict static typing (Mypy)
- Ruff linting
- Comprehensive unit testing
- Production-ready project structure

---

# Supported Databases

| Database | Type | Status |
|-----------|------|--------|
| PostgreSQL | Relational | ✅ |
| MySQL | Relational | ✅ |
| TimescaleDB | Time-Series Extension | ✅ |
| QuestDB | Time-Series | ✅ |
| ClickHouse | Analytical OLAP | ✅ |
| InfluxDB | Time-Series | ✅ |
| MongoDB | Document | ✅ |
| DynamoDB Local | NoSQL Key-Value | ✅ |

---

# Architecture

```
                 benchmark.yaml
                        │
                        ▼
              Configuration Loader
                        │
                        ▼
             Benchmark Orchestrator
                        │
      ┌─────────────────┼──────────────────┐
      ▼                 ▼                  ▼
 Workloads        Database Adapter     Resource Monitor
      │                 │                  │
      └─────────────────┼──────────────────┘
                        ▼
                Metrics Collection
                        │
                        ▼
                 Scoring Engine
                        │
                        ▼
        JSON Reports • Markdown Reports • Charts
```

---

# Project Structure

```
src/
└── benchmark/
    ├── config/
    ├── core/
    ├── databases/
    ├── workloads/
    ├── metrics/
    ├── reporting/
    ├── scoring/
    └── runners/

tests/

results/
├── raw/
├── reports/
└── charts/

docker-compose.benchmark.yml
benchmark.yaml
pyproject.toml
```

---

# Benchmark Workloads

## Sustained Write Throughput

Evaluates continuous telemetry ingestion performance under high write loads.

Metrics

- Throughput
- Average latency
- Peak latency

---

## Burst Load

Measures database performance during sudden spikes in incoming telemetry.

Metrics

- Burst latency
- Throughput stability

---

## Time Range Queries

Simulates querying telemetry over configurable time intervals.

Metrics

- Query latency
- Throughput

---

## Aggregation Queries

Evaluates analytical operations such as averages, counts, and grouped statistics.

Metrics

- Aggregation latency

---

## Historical Replay

Measures sequential replay performance for historical telemetry analysis.

Metrics

- Replay throughput

---

## Compression Evaluation

Evaluates physical storage efficiency.

Metrics

- Compression ratio
- Storage footprint

---

## Join Evaluation

Benchmarks relational joins between telemetry and metadata.

Metrics

- Join latency

---

# Scoring Methodology

Each workload contributes to the final score using configurable weights defined in `benchmark.yaml`.

Example:

| Scenario | Weight |
|----------|-------:|
| Sustained Write | 20% |
| Burst Load | 15% |
| Time Range Queries | 15% |
| Aggregation | 15% |
| Historical Replay | 15% |
| Compression | 10% |
| Join Evaluation | 10% |

The scoring engine normalizes workload metrics and generates an overall database ranking.

---

# Technology Stack

## Languages

- Python 3.13

## Databases

- PostgreSQL
- MySQL
- TimescaleDB
- QuestDB
- ClickHouse
- InfluxDB
- MongoDB
- DynamoDB Local

## Tooling

- Docker
- Docker Compose
- uv
- Ruff
- Mypy
- Pytest
- Structlog
- AsyncIO

---

# Installation

Clone the repository

```bash
git clone https://github.com/TagoreNandan/drone-storage-bench.git

cd drone-storage-bench
```

Install dependencies

```bash
uv sync
```

---

# Running the Benchmark

Start the database services

```bash
docker compose -f docker-compose.benchmark.yml up -d
```

Execute the benchmark suite

```bash
uv run python -m benchmark.runners.cli run
```

---

# Running Tests

```bash
uv run pytest
```

Current status

```
55 tests passed
```

---

# Static Analysis

Ruff

```bash
uv run ruff check .
```

Mypy

```bash
uv run mypy src
```

Both tools are configured in strict mode.

---

# Sample Benchmark Results

| Database | Overall Score |
|-----------|--------------:|
| PostgreSQL | 70.00 |
| InfluxDB | 59.39 |
| MySQL | 28.05 |
| MongoDB | 26.07 |
| TimescaleDB | 23.54 |
| QuestDB | 21.56 |
| ClickHouse | 6.07 |
| DynamoDB Local | 4.34 |

> **Note:** These results reflect the benchmark configuration and hardware used for this project. They should be interpreted as comparative measurements under identical workloads rather than absolute rankings for all deployment environments.

---

# Quality Assurance

- 55 Unit Tests
- Strict Type Checking
- Linting
- Deterministic Seed Generation
- Docker Health Checks
- Reproducible Benchmarks

---

# Future Improvements

- AWS DynamoDB benchmarking
- Grafana dashboard integration
- HTML reporting
- Kubernetes deployment
- Distributed benchmarking
- Additional database adapters
- Cloud-native benchmark execution

---

# Lessons Learned

During development, several engineering challenges were addressed:

- Designing a common abstraction layer across heterogeneous databases
- Managing asynchronous database clients
- Ensuring reproducible benchmark execution
- Maintaining strict type safety
- Supporting SQL, NoSQL, and time-series databases through a unified interface
- Producing consistent benchmark reports across multiple database engines

---

# License

This project is released under the MIT License.

---

# Author

**Tagore Nandan**

B.Tech Computer Science

Database Systems • Distributed Systems • Performance Engineering • Cloud Computing

---

# Acknowledgements

Special thanks to the open-source communities behind:

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
- Mypy
- Pytest

---

<div align="center">

⭐ If you found this project interesting, consider giving it a star!

</div>
