from abc import ABC, abstractmethod

from benchmark.config.settings import AppSettings, BenchmarkYamlConfig
from benchmark.core.database import BaseDatabaseClient
from benchmark.core.specification import BenchmarkResult
from benchmark.core.workload import BaseWorkload


class BaseWorkloadRunner(ABC):
    """Abstract Base Class for orchestrating benchmark runs.

    Coordinates database setup, cooldowns, environment checks, and executions
    of configured workloads against target databases.
    """

    def __init__(self, settings: AppSettings, run_config: BenchmarkYamlConfig) -> None:
        """Initialize orchestrating runner with settings and YAML execution profiles."""
        self.settings = settings
        self.run_config = run_config

    @abstractmethod
    async def run(self, client: BaseDatabaseClient, workload: BaseWorkload) -> BenchmarkResult:
        """Runs the specified workload against a database target.

        Args:
            client: The target database client.
            workload: The workload definition to run.

        Returns:
            A BenchmarkResult containing aggregated test metrics.

        TODO: Implement warm-up phases, connection pre-allocations, and cooldown timers.
        """
        pass
