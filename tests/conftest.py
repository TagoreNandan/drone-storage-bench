from pathlib import Path

import pytest

from benchmark.config.settings import AppSettings, BenchmarkYamlConfig


@pytest.fixture
def app_settings() -> AppSettings:
    """Fixture returning basic application settings."""
    return AppSettings(
        log_level="DEBUG",
        random_seed=42,
        benchmark_config_path="benchmark.yaml",
        results_dir="./results",
    )


@pytest.fixture
def sample_yaml_config_path() -> Path:
    """Fixture returning the path to the root benchmark.yaml configuration file."""
    return Path(__file__).parents[1] / "benchmark.yaml"


@pytest.fixture
def yaml_config(sample_yaml_config_path: Path) -> BenchmarkYamlConfig:
    """Fixture returning loaded configuration model from the root benchmark.yaml."""
    return BenchmarkYamlConfig.load_from_yaml(sample_yaml_config_path)
