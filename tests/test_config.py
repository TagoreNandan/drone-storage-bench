from benchmark.config.settings import AppSettings, BenchmarkYamlConfig


def test_app_settings_defaults(app_settings: AppSettings) -> None:
    """Verifies that default settings properties instantiate correctly."""
    assert app_settings.log_level == "DEBUG"
    assert app_settings.random_seed == 42
    assert app_settings.postgres.host == "localhost"
    assert app_settings.timescaledb.port == 5433
    assert app_settings.clickhouse.user == "default"


def test_yaml_config_parsing(yaml_config: BenchmarkYamlConfig) -> None:
    """Verifies that the benchmark.yaml file parses into Pydantic models correctly."""
    assert yaml_config.metadata.random_seed == 42
    assert yaml_config.global_config.duration_seconds == 300
    assert "timescaledb" in yaml_config.targets
    assert yaml_config.targets["timescaledb"].enabled is True
    assert len(yaml_config.workloads) > 0

    # Verify workload properties parse correctly
    ingest_wl = next(wl for wl in yaml_config.workloads if wl.type == "ingestion")
    assert ingest_wl.enabled is True
    assert "simulated_drones" in ingest_wl.params
