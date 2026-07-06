from typing import Any

import asyncpg
import structlog

from benchmark.config.settings import AppSettings
from benchmark.core.database import BaseDatabaseClient
from benchmark.core.specification import TelemetryRecord

logger = structlog.get_logger()


class QuestDBClient(BaseDatabaseClient):
    """QuestDB client implementation.

    Optimized for high-speed timeseries storage utilizing memory-mapped files,
    supporting Influx Line Protocol (ILP) and Postgres Wire Protocol query features.
    """

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)
        self.connection_config = settings.questdb
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        logger.info("Connecting to QuestDB", host=self.connection_config.host)

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
        logger.info("Disconnecting from QuestDB")

        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def is_healthy(self) -> bool:
        if self.pool is None:
            return False

        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception as exc:
            logger.exception("QuestDB health check failed", error=str(exc))
            return False

    async def setup_schema(self) -> None:
        """Creates the QuestDB telemetry table."""

        if self.pool is None:
            raise RuntimeError("QuestDB connection pool has not been initialized.")

        logger.info("Initializing QuestDB schema")

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telemetry (
                timestamp TIMESTAMP,
                vehicle_id SYMBOL,
                mission_id SYMBOL,
                latitude DOUBLE,
                longitude DOUBLE,
                altitude DOUBLE,
                roll DOUBLE,
                pitch DOUBLE,
                yaw DOUBLE,
                velocity DOUBLE,
                battery_percentage DOUBLE
            ) TIMESTAMP(timestamp)
            PARTITION BY DAY;
            """
            )

    async def cleanup_data(self) -> None:
        """Removes all telemetry data."""

        if self.pool is None:
            raise RuntimeError("QuestDB connection pool has not been initialized.")

        logger.info("Cleaning QuestDB benchmark data")

        async with self.pool.acquire() as conn:
            await conn.execute("TRUNCATE TABLE telemetry;")

    async def write_telemetry_batch(
        self,
        batch: list[TelemetryRecord],
    ) -> dict[str, Any]:
        """Writes telemetry batches to QuestDB using PGWire."""

        if self.pool is None:
            raise RuntimeError("QuestDB connection pool has not been initialized.")

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
        """Executes benchmark queries against QuestDB."""

        if self.pool is None:
            raise RuntimeError("QuestDB connection pool has not been initialized.")

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
                start_time = params["start_time"].replace(tzinfo=None)
                end_time = params["end_time"].replace(tzinfo=None)

                rows = await conn.fetch(
                    query_map[query_name],
                    start_time,
                    end_time,
                )
                row_count = len(rows)

        latency = time.perf_counter() - start

        return {
            "latency_seconds": latency,
            "row_count": row_count,
        }

    async def get_storage_size_bytes(self) -> int:
        """Returns storage consumed by QuestDB benchmark tables."""
        logger.warning("QuestDB storage size retrieval is not yet implemented.")

        return 0
