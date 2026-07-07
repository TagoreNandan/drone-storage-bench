# Report Generator Validation Report

We audited the report generator system (`generator.py` and `charts.py`) to ensure that every executed workload and database target is fully and accurately captured in the generated outputs without omission.

---

## 🔍 Validation Checklist & Status

| Output Medium | Audited Scenarios | Audited Databases | Status | Verification Summary |
| :--- | :--- | :--- | :--- | :--- |
| **JSON Results** | 3 / 3 Scenarios | 8 / 8 Databases | **✅ Passed** | Raw metrics for all scenarios and databases are stored under `"results"`. |
| **Markdown Summary** | 3 / 3 Scenarios | 8 / 8 Databases | **✅ Passed** | Table rows and comparative sections map all test runs correctly. |
| **HTML Summary** | 3 / 3 Scenarios | 8 / 8 Databases | **✅ Passed** | Runs list and individual metrics display correctly in the premium template. |
| **Overall Ranking** | 3 / 3 Scenarios | 8 / 8 Databases | **✅ Passed** | Nested `"score_report"` rankings list all 8 databases ranked deterministically. |
| **Charts** | 3 / 3 Scenarios | 8 / 8 Databases | **✅ Passed** | All 6 performance charts are generated with correct titles and labels. |

---

## 📊 Detailed Presence Verification

### 1. JSON Report Verification
* **Path**: `results/raw/standard-drone-telemetry-run_20260706_201501.json`
* **Databases Present**: `ClickHouseClient`, `DynamoDBClient`, `InfluxDBClient`, `MongoDBClient`, `MySQLClient`, `PostgreSQLClient`, `QuestDBClient`, `TimescaleDBClient`.
* **Scenarios Present**: `write_heavy_ingestion`, `mixed_telemetry_load`, `analytical_aggregation_queries`.
* **Rankings Checklist**: Overall rankings contain all 8 databases sorted deterministically.

### 2. Markdown Report Verification
* **Path**: `results/reports/standard-drone-telemetry-run_20260706_201501.md`
* **Content Match**: All 8 database names and 3 scenario names are correctly integrated in the comparative table, scoring lists, and header sections.

### 3. HTML Summary Verification
* **Path**: `results/reports/standard-drone-telemetry-run_20260706_201501.html`
* **Content Match**: All 8 database names and 3 scenario names are correctly formatted into the interactive dashboard runs list.

### 4. Chart File Verification
All 6 primary metrics visual charts were successfully plotted as high-resolution PNG images:

| Chart Type | Filename | File Size | Verification Status |
| :--- | :--- | :--- | :--- |
| **Overall Score** | `standard-drone-telemetry-run_20260706_201501_overall_score.png` | `67,311 bytes` | **✅ Verified** (All 8 databases plotted) |
| **Radar Chart** | `standard-drone-telemetry-run_20260706_201501_radar_chart.png` | `251,180 bytes` | **✅ Verified** (Multi-dimensional axes mapped) |
| **Throughput** | `standard-drone-telemetry-run_20260706_201501_throughput.png` | `202,535 bytes` | **✅ Verified** (Ingestion and mixed workloads represented) |
| **Latency** | `standard-drone-telemetry-run_20260706_201501_latency.png` | `292,653 bytes` | **✅ Verified** (Average, P50, P95, P99 metrics represented) |
| **Compression** | `standard-drone-telemetry-run_20260706_201501_compression.png` | `14,559 bytes` | **✅ Verified** (Database compression ratios) |
| **Storage Footprint** | `standard-drone-telemetry-run_20260706_201501_storage_footprint.png` | `14,901 bytes` | **✅ Verified** (Physical storage consumption in bytes) |

---

## 🔍 Validation Conclusions

* **Complete scenario tracking**: All workloads executed in the orchestrator pipeline are mapped, scored, and plotted in all reports. No scenario disappeared.
* **Database mapping integrity**: Mappings are 100% clean and correct across every artifact.
