# Scoring Engine Validation Report

We audited the scoring engine implementation (`engine.py`) to verify that all executed workloads contribute fairly and correctly to the final score and rankings.

---

## 🔍 Scoring Mappings and Weight Normalization

The suite executed 3 active workloads, which map to the following weights and metrics:

| Scenario / Workload | Scenario Type (Enum) | Weight Key | Weight Value | Normalized Weight | Primary Metric |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `write_heavy_ingestion` | `ScenarioType.WRITE_THROUGHPUT` | `sustained_write_throughput` | 0.20 | **40%** (`0.20 / 0.50`) | `rows_per_second` (Higher is Better) |
| `mixed_telemetry_load` | `ScenarioType.BURST_WRITE_LATENCY` | `burst_latency` | 0.15 | **30%** (`0.15 / 0.50`) | `average_latency_ms` (Lower is Better) |
| `analytical_aggregation_queries` | `ScenarioType.TIME_RANGE_QUERIES` | `time_range_queries` | 0.15 | **30%** (`0.15 / 0.50`) | `average_latency_ms` (Lower is Better) |

**Total Active Weights Sum**: `0.20 + 0.15 + 0.15 = 0.50`.
The scoring engine correctly normalizes these weights to sum to `1.0` (or 100%) so that the final scores scale from `0` to `100.0`.

---

## 📊 Detailed Metric Breakdown (Latest Run Validation)

Here is the step-by-step breakdown of produced metrics, extracted metrics, normalized scores, and weighted scores computed by the engine for each database target.

### 1. Workload: `write_heavy_ingestion` (Weight: 40%)
* **Target Metric**: `rows_per_second` (higher is better)
* **Limits**: Min = 377.37 rows/s (DynamoDB), Max = 76,336.46 rows/s (ClickHouse)

| Database Client | Produced Metric | Extracted Metric | Normalized Score | Weighted Score contribution |
| :--- | :--- | :--- | :--- | :--- |
| **ClickHouseClient** | `76336.46` rows/s | `rows_per_second` | **100.00** | **40.00** |
| **PostgreSQLClient** | `58748.34` rows/s | `rows_per_second` | **76.85** | **30.74** |
| **MongoDBClient** | `44354.23` rows/s | `rows_per_second` | **57.90** | **23.16** |
| **MySQLClient** | `19426.25` rows/s | `rows_per_second` | **25.08** | **10.03** |
| **QuestDBClient** | `18486.01` rows/s | `rows_per_second` | **23.84** | **9.54** |
| **InfluxDBClient** | `17284.59` rows/s | `rows_per_second` | **22.26** | **8.90** |
| **TimescaleDBClient** | `12342.21` rows/s | `rows_per_second` | **15.75** | **6.30** |
| **DynamoDBClient** | `377.37` rows/s | `rows_per_second` | **0.00** | **0.00** |

---

### 2. Workload: `mixed_telemetry_load` (Weight: 30%)
* **Target Metric**: `average_latency_ms` (lower is better)
* **Limits**: Min = 13.57 ms (PostgreSQL), Max = 2,647.22 ms (DynamoDB)

| Database Client | Produced Metric | Extracted Metric | Normalized Score | Weighted Score contribution |
| :--- | :--- | :--- | :--- | :--- |
| **PostgreSQLClient** | `13.57` ms | `average_latency_ms` | **100.00** | **30.00** |
| **MongoDBClient** | `14.74` ms | `average_latency_ms` | **99.96** | **29.99** |
| **ClickHouseClient** | `22.23` ms | `average_latency_ms` | **99.67** | **29.90** |
| **MySQLClient** | `37.60` ms | `average_latency_ms` | **99.09** | **29.73** |
| **InfluxDBClient** | `64.37` ms | `average_latency_ms` | **98.07** | **29.42** |
| **TimescaleDBClient** | `72.41` ms | `average_latency_ms` | **97.77** | **29.33** |
| **QuestDBClient** | `99.60` ms | `average_latency_ms` | **96.73** | **29.02** |
| **DynamoDBClient** | `2647.22` ms | `average_latency_ms` | **0.00** | **0.00** |

---

### 3. Workload: `analytical_aggregation_queries` (Weight: 30%)
* **Target Metric**: `average_latency_ms` (lower is better)
* **Limits**: Min = 2.14 ms (MongoDB), Max = 71.95 ms (MySQL)

| Database Client | Produced Metric | Extracted Metric | Normalized Score | Weighted Score contribution |
| :--- | :--- | :--- | :--- | :--- |
| **MongoDBClient** | `2.14` ms | `average_latency_ms` | **100.00** | **30.00** |
| **TimescaleDBClient** | `3.64` ms | `average_latency_ms` | **97.85** | **29.36** |
| **DynamoDBClient** | `5.04` ms | `average_latency_ms` | **95.84** | **28.75** |
| **ClickHouseClient** | `6.21` ms | `average_latency_ms` | **94.18** | **28.25** |
| **InfluxDBClient** | `7.08` ms | `average_latency_ms` | **92.92** | **27.88** |
| **PostgreSQLClient** | `9.01` ms | `average_latency_ms` | **90.17** | **27.05** |
| **QuestDBClient** | `17.28` ms | `average_latency_ms` | **78.32** | **23.50** |
| **MySQLClient** | `71.95` ms | `average_latency_ms` | **0.00** | **0.00** |

---

## 🔍 Validation Conclusions

* **Complete Contribution**: Every active scenario workload runs successfully, collects its primary target metric, and contributes directly to the total score. No workload is ignored.
* **Extraction Correctness**: Extracted metrics (`rows_per_second` for sustained throughput, `average_latency_ms` for mixed load and time-range query load) match the exact naming and values produced by the workload runners.
* **Typographical correctness**: Mappings are 100% clean and correct.
