from abc import ABC, abstractmethod
from typing import Any

from benchmark.config.settings import AppSettings
from benchmark.core.specification import TelemetryRecord


class BaseDatabaseClient(ABC):
    """Abstract Base Class defining the contract every database adapter must satisfy.

    Decouples benchmark workloads and runner orchestration from database-specific SQL,
    client drivers, and schema creation logic.
    """

    def __init__(self, settings: AppSettings) -> None:
        """Initialize database client using global AppSettings."""
        self.settings = settings

    @abstractmethod
    async def connect(self) -> None:
        """Establishes connections to the target database."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully closes all database connections and pools."""
        pass

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Verifies database connectivity and client health.

        Returns:
            True if database is responsive, False otherwise.
        """
        pass

    @abstractmethod
    async def setup_schema(self) -> None:
        """Initializes tables, hypertables, buckets, or collections for benchmarking."""
        pass

    @abstractmethod
    async def cleanup_data(self) -> None:
        """Truncates or deletes benchmark telemetry data to ensure run isolation."""
        pass

    @abstractmethod
    async def write_telemetry_batch(self, batch: list[TelemetryRecord]) -> dict[str, Any]:
        """Writes a batch of TelemetryRecord objects to the database.

        Args:
            batch: List of immutable TelemetryRecord items.

        Returns:
            A metadata dict containing execution metrics (e.g. latency_seconds,
            success_count, error_count).
        """
        pass

    @abstractmethod
    async def execute_query(self, query_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Executes a benchmark query pattern against the database.

        Args:
            query_name: Identifier of the query pattern.
            params: Parameters to format or inject into the query.

        Returns:
            A metadata dict containing execution metrics (e.g. latency_seconds, row_count).
        """
        pass

    @abstractmethod
    async def get_storage_size_bytes(self) -> int | None:
        """Retrieves total disk storage size consumed by benchmark tables/buckets in bytes.

        Used for compression evaluation.
        """
        pass
