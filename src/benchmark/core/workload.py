from abc import ABC, abstractmethod

from benchmark.core.database import BaseDatabaseClient
from benchmark.core.specification import BenchmarkResult, BenchmarkScenario


class BaseWorkload(ABC):
    """Abstract Base Class for defining a benchmark workload execution pattern.

    A workload represents a standard scenario (e.g., ingestion-only, read-heavy, mixed load)
    that operates on a target database using a specific generator or query pattern.
    """

    def __init__(self, scenario: BenchmarkScenario) -> None:
        """Initialize workload configuration parameters."""
        self.scenario = scenario

    @abstractmethod
    async def execute(self, client: BaseDatabaseClient) -> BenchmarkResult:
        """Runs the workload scenario against the provided database client.

        Args:
            client: An active database client implementing BaseDatabaseClient.

        Returns:
            A BenchmarkResult containing workload run performance metrics.

        TODO: Implement runner coordination, batch submission, and rate limiting logic.
        """
        pass
