from datetime import timedelta

import pytest

from benchmark.core.seed import DeterministicSeedManager
from benchmark.generators.telemetry import DeterministicTelemetryGenerator


def test_telemetry_determinism() -> None:
    """Verifies that two generators with the same seed stream identical records."""
    seed_mgr_a = DeterministicSeedManager(seed=42)
    seed_mgr_b = DeterministicSeedManager(seed=42)

    gen_a = DeterministicTelemetryGenerator(
        seed_mgr_a, num_drones=3, frequency_hz=20.0, duration_seconds=5.0
    )
    gen_b = DeterministicTelemetryGenerator(
        seed_mgr_b, num_drones=3, frequency_hz=20.0, duration_seconds=5.0
    )

    records_a = list(gen_a.stream_records())
    records_b = list(gen_b.stream_records())

    assert len(records_a) == len(records_b)
    assert len(records_a) == 3 * 20 * 5  # 3 drones * 20Hz * 5s = 300 records

    for rec_a, rec_b in zip(records_a, records_b, strict=True):
        assert rec_a == rec_b


def test_telemetry_differing_seeds() -> None:
    """Verifies that different seeds yield different records."""
    seed_mgr_a = DeterministicSeedManager(seed=42)
    seed_mgr_b = DeterministicSeedManager(seed=43)

    gen_a = DeterministicTelemetryGenerator(
        seed_mgr_a, num_drones=1, frequency_hz=10.0, duration_seconds=2.0
    )
    gen_b = DeterministicTelemetryGenerator(
        seed_mgr_b, num_drones=1, frequency_hz=10.0, duration_seconds=2.0
    )

    records_a = list(gen_a.stream_records())
    records_b = list(gen_b.stream_records())

    assert records_a != records_b


def test_telemetry_fleet_interleaving() -> None:
    """Verifies that records are yielded in chronological order, interleaved by drone."""
    seed_mgr = DeterministicSeedManager(seed=100)
    num_drones = 5
    frequency_hz = 10.0
    duration_seconds = 3.0

    generator = DeterministicTelemetryGenerator(
        seed_mgr,
        num_drones=num_drones,
        frequency_hz=frequency_hz,
        duration_seconds=duration_seconds,
    )
    records = list(generator.stream_records())

    # Check timestamps are sorted in ascending order
    timestamps = [r.timestamp for r in records]
    assert sorted(timestamps) == timestamps

    # Verify that we emit data for all drones at each timestamp
    # Step interval = 1/10 = 0.1s
    expected_steps = int(duration_seconds * frequency_hz)
    assert len(records) == num_drones * expected_steps

    for step in range(expected_steps):
        slice_start = step * num_drones
        slice_end = slice_start + num_drones
        slice_records = records[slice_start:slice_end]

        # All records in this slice must share the same timestamp
        slice_timestamps = {r.timestamp for r in slice_records}
        assert len(slice_timestamps) == 1

        # Each record in the slice should represent a unique vehicle_id
        slice_vehicles = {r.vehicle_id for r in slice_records}
        assert len(slice_vehicles) == num_drones


def test_telemetry_frequency_intervals() -> None:
    """Verifies that the time gap between steps matches the frequency config."""
    seed_mgr = DeterministicSeedManager(seed=200)
    frequency_hz = 25.0
    duration_seconds = 2.0

    generator = DeterministicTelemetryGenerator(
        seed_mgr, num_drones=1, frequency_hz=frequency_hz, duration_seconds=duration_seconds
    )
    records = list(generator.stream_records())

    # Interval should be exactly 1 / 25 = 0.04 seconds = 40 milliseconds
    expected_delta = timedelta(seconds=0.04)

    for i in range(len(records) - 1):
        delta = records[i + 1].timestamp - records[i].timestamp
        assert delta == expected_delta


def test_telemetry_evolution_smoothness() -> None:
    """Verifies that position, battery, and orientation evolve continuously and smoothly."""
    seed_mgr = DeterministicSeedManager(seed=300)
    generator = DeterministicTelemetryGenerator(
        seed_mgr, num_drones=1, frequency_hz=20.0, duration_seconds=10.0
    )
    records = list(generator.stream_records())

    for i in range(len(records) - 1):
        curr = records[i]
        nxt = records[i + 1]

        # Battery must strictly decrease (or stay at 0.0)
        assert nxt.battery_percentage <= curr.battery_percentage
        assert nxt.battery_percentage < 100.0

        # Latitude / Longitude movements are continuous (no teleportation)
        # Lat change should be small per step (theta changes up to 0.05 * 0.05rad per step)
        lat_diff = abs(nxt.latitude - curr.latitude)
        lon_diff = abs(nxt.longitude - curr.longitude)
        assert lat_diff < 0.001
        assert lon_diff < 0.001

        # Altitude evolves smoothly
        alt_diff = abs(nxt.altitude - curr.altitude)
        assert alt_diff < 1.0


def test_custom_tunnel_metrics() -> None:
    """Verifies configurable custom metrics are simulated and yielded."""
    seed_mgr = DeterministicSeedManager(seed=400)
    custom_metrics = ["tunnel_temp", "tunnel_pressure"]
    generator = DeterministicTelemetryGenerator(
        seed_mgr,
        num_drones=2,
        frequency_hz=10.0,
        duration_seconds=2.0,
        custom_metric_names=custom_metrics,
    )
    records = list(generator.stream_records())

    for r in records:
        assert "tunnel_temp" in r.custom_metrics
        assert "tunnel_pressure" in r.custom_metrics
        # Custom values should be within the simulated bounds
        assert 0.0 <= r.custom_metrics["tunnel_temp"] <= 100.0
        assert 0.0 <= r.custom_metrics["tunnel_pressure"] <= 100.0


def test_invalid_telemetry_frequency() -> None:
    """Verifies that invalid frequencies raise ValueError."""
    seed_mgr = DeterministicSeedManager(seed=500)
    with pytest.raises(ValueError):
        DeterministicTelemetryGenerator(seed_mgr, frequency_hz=5.0)
    with pytest.raises(ValueError):
        DeterministicTelemetryGenerator(seed_mgr, frequency_hz=60.0)
