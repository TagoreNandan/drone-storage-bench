from typing import Any

import clickhouse_connect
import structlog
from clickhouse_connect.driver import Client

from benchmark.config.settings import AppSettings
from benchmark.core.database import BaseDatabaseClient
from benchmark.core.specification import TelemetryRecord

logger = structlog.get_logger()


class ClickHouseClient(BaseDatabaseClient):
    """ClickHouse client implementation.

    High-performance columnar database client supporting clickhouse-connect (HTTP)
    or native TCP/IP socket connections.
    """

    def __init__(self, settings: AppSettings) -> None:
        """Initialize ClickHouse client using global AppSettings."""
        super().__init__(settings)
        self.connection_config = settings.clickhouse
        self.client: Client | None = None

    async def connect(self) -> None:
        """Establishes a ClickHouse connection."""

        logger.info(
            "Connecting to ClickHouse",
            host=self.connection_config.host,
        )

        self.client = clickhouse_connect.get_client(
            host=self.connection_config.host,
            port=self.connection_config.port_http,
            username=self.connection_config.user,
            password=self.connection_config.password,
            database=self.connection_config.database,
        )

    async def disconnect(self) -> None:
        """Gracefully closes the ClickHouse client."""
        logger.info("Disconnecting from ClickHouse")

        if self.client is not None:
            self.client.close()
            self.client = None

    async def is_healthy(self) -> bool:
        """Checks ClickHouse connectivity."""

        if self.client is None:
            return False

        try:
            self.client.query("SELECT 1")
            return True
        except Exception as exc:
            logger.exception(
                "ClickHouse health check failed",
                error=str(exc),
            )
            return False

    async def setup_schema(self) -> None:
        """Creates the telemetry table."""

        if self.client is None:
            raise RuntimeError("ClickHouse client has not been initialized.")

        logger.info("Initializing ClickHouse schema")

        self.client.command(
            """
        CREATE TABLE IF NOT EXISTS telemetry
        (
            timestamp DateTime64(3),
            vehicle_id String,
            mission_id String,
            latitude Float64,
            longitude Float64,
            altitude Float64,
            roll Float64,
            pitch Float64,
            yaw Float64,
            velocity Float64,
            battery_percentage Float64
        )
        ENGINE = MergeTree
        ORDER BY (vehicle_id, timestamp)
        """
        )

    async def cleanup_data(self) -> None:
        """Removes benchmark telemetry."""

        if self.client is None:
            raise RuntimeError("ClickHouse client has not been initialized.")

        logger.info("Cleaning ClickHouse benchmark data")
        self.client.command("TRUNCATE TABLE telemetry")

    async def write_telemetry_batch(
        self,
        batch: list[TelemetryRecord],
    ) -> dict[str, Any]:
        """Writes telemetry records using ClickHouse block inserts."""

        if self.client is None:
            raise RuntimeError("ClickHouse client has not been initialized.")

        import time

        start = time.perf_counter()

        rows = [
            [
                record.timestamp,
                record.vehicle_id,
                record.mission_id,
                record.latitude,
                record.longitude,
                record.altitude,
                record.roll,
                record.pitch,
                record.yaw,
                record.velocity,
                record.battery_percentage,
            ]
            for record in batch
        ]

        self.client.insert(
            table="telemetry",
            data=rows,
            column_names=[
                "timestamp",
                "vehicle_id",
                "mission_id",
                "latitude",
                "longitude",
                "altitude",
                "roll",
                "pitch",
                "yaw",
                "velocity",
                "battery_percentage",
            ],
        )
        latency = time.perf_counter() - start
        return {
            "latency_seconds": latency,
            "success_count": len(batch),
            "error_count": 0,
        }

    async def execute_query(
        self,
        query_name: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Executes benchmark queries against ClickHouse."""

        if self.client is None:
            raise RuntimeError("ClickHouse client has not been initialized.")
        import time

        query_map = {
            "total_row_count": "SELECT COUNT(*) FROM telemetry",
            "time_range_query": """
                SELECT *
                FROM telemetry
                WHERE timestamp BETWEEN %(start)s AND %(end)s
                ORDER BY timestamp
            """,
        }

        if query_name not in query_map:
            raise ValueError(f"Unsupported query: {query_name}")

        start = time.perf_counter()
        if query_name == "total_row_count":
            result = self.client.query(query_map[query_name])
            row_count = int(result.result_rows[0][0])
        else:
            result = self.client.query(
                query_map[query_name],
                parameters={
                    "start": params["start_time"],
                    "end": params["end_time"],
                },
            )
        row_count = len(result.result_rows)

        latency = time.perf_counter() - start

        return {
            "latency_seconds": latency,
            "row_count": row_count,
        }

    async def get_storage_size_bytes(self) -> int:
        """Returns storage used by the telemetry table."""

        if self.client is None:
            raise RuntimeError("ClickHouse client has not been initialized.")

        result = self.client.query(
            """
            SELECT sum(bytes_on_disk)
            FROM system.parts
            WHERE database = currentDatabase()
              AND table = 'telemetry'
              AND active
            """
        )

        value = result.result_rows[0][0]

        return int(value or 0)
