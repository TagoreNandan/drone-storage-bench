from typing import Any

import asyncpg
import structlog

from benchmark.config.settings import AppSettings
from benchmark.core.database import BaseDatabaseClient
from benchmark.core.specification import TelemetryRecord

logger = structlog.get_logger()


class TimescaleDBClient(BaseDatabaseClient):
    """TimescaleDB client implementation.

    Extends standard PostgreSQL functionality with Hypertable optimizations,
    chunk partitions, compression, and advanced time-series functions.
    """

    def __init__(self, settings: AppSettings) -> None:
        """Initialize TimescaleDB client using global AppSettings."""
        super().__init__(settings)
        self.connection_config = settings.timescaledb
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Establishes a connection pool to TimescaleDB."""

        logger.info("Connecting to TimescaleDB", host=self.connection_config.host)

        self.pool = await asyncpg.create_pool(
            host=self.connection_config.host,
            port=self.connection_config.port,
            user=self.connection_config.user,
            password=self.connection_config.password,
            database=self.connection_config.database,
            min_size=1,
            max_size=10,
        )

    async def disconnect(self) -> None:
        """Gracefully closes the TimescaleDB connection pool."""
        logger.info("Disconnecting from TimescaleDB")

        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def is_healthy(self) -> bool:
        """Checks whether TimescaleDB is reachable."""

        if self.pool is None:
            return False

        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception as exc:
            logger.exception("TimescaleDB health check failed", error=str(exc))
            return False

    async def setup_schema(self) -> None:
        """Creates the telemetry hypertable."""

        if self.pool is None:
            raise RuntimeError("TimescaleDB connection pool has not been initialized.")

        logger.info("Initializing TimescaleDB schema")

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE EXTENSION IF NOT EXISTS timescaledb;

                CREATE TABLE IF NOT EXISTS telemetry (
                    timestamp TIMESTAMPTZ NOT NULL,
                    vehicle_id TEXT NOT NULL,
                    mission_id TEXT NOT NULL,
                    latitude DOUBLE PRECISION NOT NULL,
                    longitude DOUBLE PRECISION NOT NULL,
                    altitude DOUBLE PRECISION NOT NULL,
                    roll DOUBLE PRECISION NOT NULL,
                    pitch DOUBLE PRECISION NOT NULL,
                    yaw DOUBLE PRECISION NOT NULL,
                    velocity DOUBLE PRECISION NOT NULL,
                    battery_percentage DOUBLE PRECISION NOT NULL
                );
                """
            )

            await conn.execute(
                """
                SELECT create_hypertable(
                    'telemetry',
                    'timestamp',
                    if_not_exists => TRUE
                );
                """
            )

    async def cleanup_data(self) -> None:
        """Removes all benchmark data."""

        if self.pool is None:
            raise RuntimeError("TimescaleDB connection pool has not been initialized.")

        logger.info("Cleaning TimescaleDB benchmark data")

        async with self.pool.acquire() as conn:
            await conn.execute("TRUNCATE TABLE telemetry;")

    async def write_telemetry_batch(
        self,
        batch: list[TelemetryRecord],
    ) -> dict[str, Any]:
        """Writes a batch of telemetry records into TimescaleDB."""

        if self.pool is None:
            raise RuntimeError("TimescaleDB connection pool has not been initialized.")

        import time

        start = time.perf_counter()

        rows = [
            (
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
            )
            for record in batch
        ]

        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
            INSERT INTO telemetry (
                timestamp,
                vehicle_id,
                mission_id,
                latitude,
                longitude,
                altitude,
                roll,
                pitch,
                yaw,
                velocity,
                battery_percentage
            )
            VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11
            )
            """,
                rows,
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
        """Executes benchmark queries."""

        if self.pool is None:
            raise RuntimeError("TimescaleDB connection pool has not been initialized.")

        import time

        query_map = {
            "total_row_count": "SELECT COUNT(*) FROM telemetry;",
            "time_range_query": """
                SELECT *
                FROM telemetry
                WHERE timestamp BETWEEN $1 AND $2
                ORDER BY timestamp;
            """,
        }

        if query_name not in query_map:
            raise ValueError(f"Unsupported query: {query_name}")

        start = time.perf_counter()

        async with self.pool.acquire() as conn:
            if query_name == "total_row_count":
                result = await conn.fetchval(query_map[query_name])
                row_count = int(result)
            else:
                rows = await conn.fetch(
                    query_map[query_name],
                    params["start_time"],
                    params["end_time"],
                )
                row_count = len(rows)

        latency = time.perf_counter() - start

        return {
            "latency_seconds": latency,
            "row_count": row_count,
        }

    async def get_storage_size_bytes(self) -> int:
        """Returns the storage used by the telemetry hypertable."""

        if self.pool is None:
            raise RuntimeError("TimescaleDB connection pool has not been initialized.")

        async with self.pool.acquire() as conn:
            size = await conn.fetchval(
                """
                SELECT pg_total_relation_size('telemetry');
                """
            )

        return int(size)
