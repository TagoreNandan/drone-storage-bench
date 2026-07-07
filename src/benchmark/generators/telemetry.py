import math
import random
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

from benchmark.core.seed import DeterministicSeedManager
from benchmark.core.specification import TelemetryRecord


class BaseTelemetryGenerator(ABC):
    """Abstract Base Class for all telemetry generators."""

    def __init__(self, seed_manager: DeterministicSeedManager) -> None:
        """Initialize base telemetry generator with seed manager."""
        self.seed_manager = seed_manager

    @abstractmethod
    def stream_records(self) -> Iterator[TelemetryRecord]:
        """Streams generated telemetry records.

        Yields:
            An iterator of immutable TelemetryRecord objects.
        """
        pass


class DroneStateConfig(NamedTuple):
    """Immutable configuration holding trajectory settings for a single simulated drone."""

    vehicle_id: str
    mission_id: str
    base_lat: float
    base_lon: float
    flight_radius: float
    angular_frequency: float
    base_altitude: float
    altitude_amplitude: float
    altitude_frequency: float
    base_velocity: float
    velocity_amplitude: float
    battery_discharge_rate: float
    custom_metric_params: dict[str, dict[str, float]]


class DeterministicTelemetryGenerator(BaseTelemetryGenerator):
    """Simulates realistic telemetry evolution for a fleet of drones.

    Ensures mathematical continuity and complete determinism based on seed sequences.
    """

    def __init__(
        self,
        seed_manager: DeterministicSeedManager,
        num_drones: int = 10,
        frequency_hz: float = 20.0,
        duration_seconds: float = 300.0,
        custom_metric_names: list[str] | None = None,
        start_time: datetime | None = None,
    ) -> None:
        """Initialize the deterministic telemetry generator.

        Args:
            seed_manager: Seed manager supplying the global seed stream.
            num_drones: Size of the drone fleet.
            frequency_hz: Recording frequency (10 to 50 Hz).
            duration_seconds: Total time duration of the simulated mission.
            custom_metric_names: Optional custom metrics to simulate (e.g. TUNNEL metrics).
            start_time: Start timestamp of the mission (defaults to fixed timestamp).
        """
        super().__init__(seed_manager)
        self.num_drones = num_drones
        self.frequency_hz = frequency_hz
        self.duration_seconds = duration_seconds
        self.custom_metric_names = custom_metric_names or []
        self.start_time = start_time or datetime(2026, 7, 4, 0, 0, 0, tzinfo=UTC)

        # Enforce frequency constraints
        if not (10.0 <= self.frequency_hz <= 50.0):
            raise ValueError("Telemetry frequency must be between 10 and 50 Hz.")

        # Build fleet configuration parameters deterministically
        self._fleet_configs: list[DroneStateConfig] = []
        subseed_gen = self.seed_manager.get_subseed_generator()

        for i in range(self.num_drones):
            drone_subseed = next(subseed_gen)
            rng = random.Random(drone_subseed)

            # Generate deterministic settings for this drone
            vehicle_id = f"drone_{i:04d}"
            mission_id = f"mission_{rng.randint(100000, 999999)}"

            # Coordinates centered around a default airfield (e.g. near SF)
            base_lat = rng.uniform(37.75, 37.80)
            base_lon = rng.uniform(-122.45, -122.35)
            flight_radius = rng.uniform(0.001, 0.005)  # ~100m to 500m radius
            angular_frequency = rng.uniform(0.01, 0.05)  # radians per second

            base_altitude = rng.uniform(60.0, 150.0)
            altitude_amplitude = rng.uniform(5.0, 15.0)
            altitude_frequency = rng.uniform(0.02, 0.08)

            base_velocity = rng.uniform(10.0, 22.0)  # m/s
            velocity_amplitude = rng.uniform(1.0, 4.0)

            # Calculate discharge rate to hit 0% battery around mission completion
            # with some variation (+- 10%)
            discharge_duration = self.duration_seconds * rng.uniform(0.9, 1.1)
            battery_discharge_rate = 100.0 / discharge_duration

            # Custom metrics dynamics
            custom_metric_params = {}
            for name in self.custom_metric_names:
                custom_metric_params[name] = {
                    "base": rng.uniform(10.0, 90.0),
                    "amplitude": rng.uniform(2.0, 8.0),
                    "frequency": rng.uniform(0.01, 0.05),
                }

            self._fleet_configs.append(
                DroneStateConfig(
                    vehicle_id=vehicle_id,
                    mission_id=mission_id,
                    base_lat=base_lat,
                    base_lon=base_lon,
                    flight_radius=flight_radius,
                    angular_frequency=angular_frequency,
                    base_altitude=base_altitude,
                    altitude_amplitude=altitude_amplitude,
                    altitude_frequency=altitude_frequency,
                    base_velocity=base_velocity,
                    velocity_amplitude=velocity_amplitude,
                    battery_discharge_rate=battery_discharge_rate,
                    custom_metric_params=custom_metric_params,
                )
            )

    def stream_records(self) -> Iterator[TelemetryRecord]:
        """Streams chronological records for the entire fleet.

        Yields:
            TelemetryRecord objects interleaved chronologically step-by-step.
        """
        total_steps = int(self.duration_seconds * self.frequency_hz)
        dt = 1.0 / self.frequency_hz

        for step in range(total_steps):
            elapsed_time = step * dt
            timestamp = self.start_time + timedelta(seconds=elapsed_time)

            for config in self._fleet_configs:
                # 1. Smooth Trajectory calculation (Lissajous figure-eight trajectory)
                theta = config.angular_frequency * elapsed_time
                lat = config.base_lat + config.flight_radius * math.sin(theta)
                lon = config.base_lon + config.flight_radius * math.cos(theta * 2.0)

                # 2. Smooth Altitude calculation
                alt_theta = config.altitude_frequency * elapsed_time
                altitude = config.base_altitude + config.altitude_amplitude * math.sin(alt_theta)

                # 3. Smooth Velocity calculation
                velocity = max(
                    0.0, config.base_velocity + config.velocity_amplitude * math.cos(theta)
                )

                # 4. Smooth Orientation calculations
                roll = 15.0 * math.cos(theta * 2.0)
                pitch = 10.0 * math.sin(theta)
                # Keep yaw between [0.0, 360.0)
                yaw = (theta * 180.0 / math.pi) % 360.0

                # 5. Gradual battery discharge
                battery_percentage = max(0.0, 100.0 - config.battery_discharge_rate * elapsed_time)

                # 6. Smooth Custom metrics evolution
                custom_metrics = {}
                for name, params in config.custom_metric_params.items():
                    custom_metrics[name] = params["base"] + params["amplitude"] * math.sin(
                        params["frequency"] * elapsed_time
                    )

                yield TelemetryRecord(
                    timestamp=timestamp,
                    vehicle_id=config.vehicle_id,
                    mission_id=config.mission_id,
                    latitude=lat,
                    longitude=lon,
                    altitude=altitude,
                    roll=roll,
                    pitch=pitch,
                    yaw=yaw,
                    velocity=velocity,
                    battery_percentage=battery_percentage,
                    custom_metrics=custom_metrics,
                )
