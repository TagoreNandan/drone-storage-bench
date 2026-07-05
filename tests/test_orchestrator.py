import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from benchmark.config.settings import AppSettings, BenchmarkYamlConfig
from benchmark.core.database import BaseDatabaseClient
from benchmark.core.specification import TelemetryRecord
from benchmark.runners.orchestrator import BenchmarkOrchestrator


class MockHealthyClient(BaseDatabaseClient):
    """Mock client representing a healthy database adapter."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)
        self.connected = False
        self.disconnected = False
        self.schema_setup = False
        self.cleaned_up = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.disconnected = True

    async def is_healthy(self) -> bool:
        return True

    async def setup_schema(self) -> None:
        self.schema_setup = True

    async def cleanup_data(self) -> None:
        self.cleaned_up = True

    async def write_telemetry_batch(self, batch: list[TelemetryRecord]) -> dict[str, Any]:
        return {"latency_seconds": 0.01, "success_count": len(batch), "error_count": 0}

    async def execute_query(self, query_name: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"latency_seconds": 0.02, "row_count": 10}

    async def get_storage_size_bytes(self) -> int:
        return 1000


class MockUnhealthyClient(MockHealthyClient):
    """Mock client representing an unhealthy database adapter."""

    async def is_healthy(self) -> bool:
        return False


@pytest.fixture
def temp_results_dir(tmp_path: Path) -> Path:
    """Fixture providing a temporary results directory."""
    return tmp_path / "results"


def test_orchestrator_suite_mapping(
    app_settings: AppSettings, yaml_config: BenchmarkYamlConfig
) -> None:
    """Verifies that the orchestrator translates configurations to specifications correctly."""
    orchestrator = BenchmarkOrchestrator(app_settings, yaml_config)
    suite = orchestrator._map_config_to_suite()

    assert suite.name == "standard-drone-telemetry-run"
    assert len(suite.scenarios) == len(yaml_config.workloads)
    assert suite.global_seed == yaml_config.metadata.random_seed


def test_orchestrator_execution_flow(
    temp_results_dir: Path, yaml_config: BenchmarkYamlConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies sequential scenario executions, health checking, and structured outputs."""
    settings = AppSettings(results_dir=str(temp_results_dir))

    # Mock DB registry with mock clients
    mock_registry = {
        "postgres": MockHealthyClient,
        "timescaledb": MockUnhealthyClient,  # Unhealthy DB should be bypassed
        "questdb": MockHealthyClient,
    }
    monkeypatch.setattr("benchmark.runners.orchestrator.DB_CLIENT_REGISTRY", mock_registry)

    orchestrator = BenchmarkOrchestrator(settings, yaml_config)
    summary = asyncio.run(orchestrator.execute_suite())

    # Verify return schema
    assert summary["suite_name"] == "standard-drone-telemetry-run"
    results = summary["results"]
    assert len(results) > 0

    # TimescaleDB is unhealthy, so it should have been disconnected and bypassed.
    databases_tested = {r["database_name"] for r in results}
    assert "MockUnhealthyClient" not in databases_tested
    assert "MockHealthyClient" in databases_tested

    # Verify cleanup was triggered
    # Check that directories and files are written to the temp results folder
    raw_dir = temp_results_dir / "raw"
    reports_dir = temp_results_dir / "reports"
    assert raw_dir.exists()
    assert reports_dir.exists()

    # Check JSON reports serialization
    json_files = list(raw_dir.glob("*.json"))
    assert len(json_files) == 1
    with json_files[0].open() as f:
        data = json.load(f)
    assert "results" in data
    assert len(data["results"]) == len(results)

    # Check Markdown summaries compilation
    md_files = list(reports_dir.glob("*.md"))
    assert len(md_files) == 1
    md_content = md_files[0].read_text()
    assert "# Drone Storage Bench" in md_content
    assert "MockHealthyClient" in md_content


class MockCrashingWorkloadClient(MockHealthyClient):
    """Mock client that causes schema setup to crash, testing error boundaries containment."""

    async def setup_schema(self) -> None:
        raise RuntimeError("Disk Write Failure")


def test_orchestrator_failure_containment(
    temp_results_dir: Path, yaml_config: BenchmarkYamlConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies that orchestrator contains adapter exceptions gracefully without crashing."""
    settings = AppSettings(results_dir=str(temp_results_dir))

    # Mock DB registry with crashing client
    mock_registry = {"postgres": MockCrashingWorkloadClient}
    monkeypatch.setattr("benchmark.runners.orchestrator.DB_CLIENT_REGISTRY", mock_registry)

    orchestrator = BenchmarkOrchestrator(settings, yaml_config)
    summary = asyncio.run(orchestrator.execute_suite())

    results = summary["results"]
    assert len(results) > 0
    # Every scenario should report success as False and contain the isolated error message
    for res in results:
        assert res["success"] is False
        assert "Disk Write Failure" in res["error_message"]
