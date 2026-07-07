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
        import asyncio
        self.lock = asyncio.Lock()

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
        """Creates the telemetry and vehicles tables."""

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

        self.client.command(
            """
        CREATE TABLE IF NOT EXISTS vehicles
        (
            vehicle_id String,
            model String,
            manufacturer String
        )
        ENGINE = MergeTree
        ORDER BY vehicle_id
        """
        )

        # Populate vehicles if empty
        res = self.client.query("SELECT count() FROM vehicles")
        if res.result_rows[0][0] == 0:
            vehicles_data = [
                (f"drone_{i:04d}", f"Model-{i%5}", f"Manufacturer-{i%3}")
                for i in range(200)
            ]
            self.client.insert(
                "vehicles",
                vehicles_data,
                column_names=["vehicle_id", "model", "manufacturer"],
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

        import asyncio
        import time

        # 1. Format/Serialize outside of the timed block
        data = [
            [
                r.timestamp,
                r.vehicle_id,
                r.mission_id,
                r.latitude,
                r.longitude,
                r.altitude,
                r.roll,
                r.pitch,
                r.yaw,
                r.velocity,
                r.battery_percentage,
            ]
            for r in batch
        ]

        column_names = [
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
        ]

        # 2. Time only the database insert operation, executing on a worker thread
        loop = asyncio.get_event_loop()
        async with self.lock:
            start = time.perf_counter()
            await loop.run_in_executor(
                None,
                self.client.insert,
                "telemetry",
                data,
                column_names,
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

        if query_name == "compress":
            return {}

        if self.client is None:
            raise RuntimeError("ClickHouse client has not been initialized.")
        import time

        query_map = {
            "total_row_count": "SELECT count() FROM telemetry",
            "time_range_query": """
                SELECT *
                FROM telemetry
                WHERE vehicle_id = %(vehicle_id)s AND timestamp BETWEEN %(start)s AND %(end)s
                ORDER BY timestamp
            """,
            "aggregation_query": """
                SELECT toStartOfInterval(timestamp, INTERVAL %(interval_sec)s SECOND) AS bucket,
                       avg(battery_percentage) as avg_value
                FROM telemetry
                WHERE vehicle_id = %(vehicle_id)s AND timestamp BETWEEN %(start)s AND %(end)s
                GROUP BY bucket
                ORDER BY bucket
            """,
            "historical_replay_query": """
                SELECT *
                FROM telemetry
                WHERE mission_id = %(mission_id)s
                ORDER BY timestamp ASC
            """,
            "join_query": """
                SELECT t.*, v.model, v.manufacturer
                FROM telemetry t
                JOIN vehicles v ON t.vehicle_id = v.vehicle_id
                WHERE t.vehicle_id = %(vehicle_id)s AND t.timestamp BETWEEN %(start)s AND %(end)s
                ORDER BY t.timestamp
            """,
        }

        if query_name not in query_map:
            raise ValueError(f"Unsupported query: {query_name}")

        async with self.lock:
            start = time.perf_counter()
            if query_name == "total_row_count":
                result = self.client.query(query_map[query_name])
                row_count = int(result.result_rows[0][0])
            elif query_name == "time_range_query":
                result = self.client.query(
                    query_map[query_name],
                    parameters={
                        "vehicle_id": params["vehicle_id"],
                        "start": params["start_time"],
                        "end": params["end_time"],
                    },
                )
                row_count = len(result.result_rows)
            elif query_name == "aggregation_query":
                interval = int(params.get("aggregation_interval_seconds", 60))
                result = self.client.query(
                    query_map[query_name],
                    parameters={
                        "vehicle_id": params["vehicle_id"],
                        "interval_sec": interval,
                        "start": params["start_time"],
                        "end": params["end_time"],
                    },
                )
                row_count = len(result.result_rows)
                latency = time.perf_counter() - start
                return {
                    "latency_seconds": latency,
                    "groups_returned": row_count,
                }
            elif query_name == "historical_replay_query":
                result = self.client.query(
                    query_map[query_name],
                    parameters={
                        "mission_id": params["mission_id"],
                    },
                )
                row_count = len(result.result_rows)
            elif query_name == "join_query":
                result = self.client.query(
                    query_map[query_name],
                    parameters={
                        "vehicle_id": params["vehicle_id"],
                        "start": params["start_time"],
                        "end": params["end_time"],
                    },
                )
                row_count = len(result.result_rows)
                latency = time.perf_counter() - start
                return {
                    "latency_seconds": latency,
                    "row_count": row_count,
                    "join_strategy": "native",
                    "merge_duration_ms": 0.0,
                }

            latency = time.perf_counter() - start

        return {
            "latency_seconds": latency,
            "row_count": row_count,
        }

    async def get_storage_size_bytes(self) -> int | None:
        """Returns storage used by the telemetry and vehicles tables."""

        if self.client is None:
            raise RuntimeError("ClickHouse client has not been initialized.")

        async with self.lock:
            result = self.client.query(
                """
                SELECT sum(bytes_on_disk)
                FROM system.parts
                WHERE database = currentDatabase()
                  AND table IN ('telemetry', 'vehicles')
                  AND active
                """
            )

            value = result.result_rows[0][0]

        return int(value or 0)
