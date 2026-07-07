# Telemetry Generator & Dataset Validation Report

We audited the dataset generation, seed distribution, batching mechanism, and orchestrator execution loops to ensure that all database targets receive 100% identical data inputs, timestamps, batch sizes, warmup phases, cooldown phases, and query parameters.

---

## 🔍 Validation Checklist & Status

| Validation Dimension | Verification Metric | Status | Implementation Details |
| :--- | :--- | :--- | :--- |
| **Identical Records** | Telemetry coordinates, values, and attributes | **✅ Passed** | Generated via `DeterministicTelemetryGenerator` using a global static dataset profile seed (`dataset_profile.seed`) for all database runs. |
| **Identical Timestamps** | Epoch timestamps in milliseconds/microseconds | **✅ Passed** | Strictly deterministic steps (`elapsed_time = step * dt`) centered at the static base timestamp: `datetime(2026, 7, 4, 0, 0, 0, tzinfo=UTC)`. |
| **Identical Batch Sizes** | Telemetry records per client write call | **✅ Passed** | Derived directly from scenario settings (`dataset_profile.batch_size` or default 1,000) using a shared batch iterator. |
| **Identical Warmup** | Telemetry writes prior to benchmark timing | **✅ Passed** | Warmup duration is read from scenario properties (`scenario.warmup_duration_seconds`) and applied identically across targets. |
| **Identical Cooldown** | Sleep duration between database scenario executions | **✅ Passed** | Handled globally via `asyncio.sleep(self.settings.cooldown_seconds)` in the orchestrator runner loop. |
| **Identical Query Windows** | Time windows, vehicle IDs, and iterations | **✅ Passed** | Query generator seeded deterministically with `random.Random(scenario.deterministic_random_seed)` ensuring identical sequence of inputs. |

---

## 📊 Technical Verification & Determinism Details

### 1. Seed Manager and Interleaved Generation
The `DeterministicSeedManager` provides the sub-seed generator stream:
```python
subseed_gen = self.seed_manager.get_subseed_generator()
for i in range(self.num_drones):
    drone_subseed = next(subseed_gen)
    rng = random.Random(drone_subseed)
```
Because the initial seed is identical across all database executions of the same scenario, the generated fleet coordinate equations (Lissajous curves), altitude limits, and discharge parameters are exactly identical.

### 2. Time Window Query Determinism
In `TimeRangeQueryWorkload`, `AggregationQueryWorkload`, `HistoricalReplayWorkload`, and `JoinEvaluationWorkload`, the parameters for querying are selected using `local_random` seeded with the static `deterministic_random_seed`:
```python
local_random = random.Random(self.scenario.deterministic_random_seed)
```
This guarantees that:
* The sequence of randomly selected query time windows (`window_start` to `window_end`) is identical.
* The sequence of queried `vehicle_id`s (e.g., `drone_0042`) is identical.
* The number of iterations matches precisely.

This ensures complete benchmarking fairness across all 8 target databases.

---

## 🔍 Validation Conclusions

* **Absolute Fair Ingestion**: No database target receives more data, different timestamps, or different batch partitions than another.
* **Absolute Fair Querying**: The databases are tested with identical query payloads, filtering ranges, and constraints.
* **Deterministic Replicability**: Run validation is 100% deterministic and replicable.
