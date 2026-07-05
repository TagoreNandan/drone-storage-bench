import asyncio
from pathlib import Path

import click

from benchmark.config.settings import AppSettings, BenchmarkYamlConfig
from benchmark.runners.orchestrator import BenchmarkOrchestrator
from benchmark.utils.logging import configure_logging


@click.group()
def cli() -> None:
    """Drone Storage Bench CLI.

    A tool to benchmark TimescaleDB, QuestDB, ClickHouse, and InfluxDB 3.
    """
    pass


@cli.command()
@click.option(
    "--config",
    "-c",
    default="benchmark.yaml",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to the declarative benchmark.yaml configuration file.",
)
def run(config: Path) -> None:
    """Runs the benchmark suite using the provided configuration file."""
    # Initialize global settings from environment variables
    settings = AppSettings()

    # Configure structured logging
    configure_logging(settings.log_level)

    # Load and validate the YAML file
    yaml_config = BenchmarkYamlConfig.load_from_yaml(config)

    # Run the orchestrator asynchronously
    asyncio.run(_async_run(settings, yaml_config))


async def _async_run(settings: AppSettings, yaml_config: BenchmarkYamlConfig) -> None:
    """Internal helper to orchestrate execution asynchronously."""
    orchestrator = BenchmarkOrchestrator(settings, yaml_config)
    await orchestrator.execute_suite()


if __name__ == "__main__":
    cli()
