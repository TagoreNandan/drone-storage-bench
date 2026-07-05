"""Telemetry Generation components for drone-storage-bench.

This package defines the interfaces and placeholders for deterministic telemetry
generators. Generators use seed streams to emit identical telemetry shapes and values
across database benchmark trials.
"""

from benchmark.generators.telemetry import (
    BaseTelemetryGenerator,
    DeterministicTelemetryGenerator,
)

__all__ = ["BaseTelemetryGenerator", "DeterministicTelemetryGenerator"]
