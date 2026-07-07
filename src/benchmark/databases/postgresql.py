from typing import Any

import asyncpg
import structlog

from benchmark.config.settings import AppSettings
from benchmark.core.database import BaseDatabaseClient
from benchmark.core.specification import TelemetryRecord

logger = structlog.get_logger()


class PostgreSQLClient(BaseDatabaseClient):
    """PostgreSQL client implementation.

    Used strictly as a control-plane reference database for relational JOIN
    benchmarking alongside standard timeseries workloads.
    """

    def __init__(self, settings: AppSettings) -> None:
        """Initialize PostgreSQL Client using global AppSettings."""
        super().__init__(settings)
        self.connection_config = settings.postgres
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        logger.info("Connecting to PostgreSQL", host=self.connection_config.host)

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
        logger.info("Disconnecting from PostgreSQL")
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
            logger.exception("PostgreSQL health check failed", error=str(exc))
            return False

    async def setup_schema(self) -> None:
        """Creates the benchmark tables if they do not already exist."""
        if self.pool is None:
            raise RuntimeError("PostgreSQL connection pool has not been initialized.")
        logger.info("Initializing PostgreSQL schema")

        async with self.pool.acquire() as conn:
            # Create telemetry table
            await conn.execute(
                """
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
            # Create vehicles table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vehicles (
                    vehicle_id VARCHAR(50) PRIMARY KEY,
                    model VARCHAR(100),
                    manufacturer VARCHAR(100)
                );
                """
            )
            # Check if vehicles table is empty, if so populate it
            count = await conn.fetchval("SELECT COUNT(*) FROM vehicles;")
            if count == 0:
                vehicles_data = [
                    (f"drone_{i:04d}", f"Model-{i%5}", f"Manufacturer-{i%3}")
                    for i in range(200)
                ]
                await conn.executemany(
                    """
                    INSERT INTO vehicles (vehicle_id, model, manufacturer)
                    VALUES ($1, $2, $3);
                    """,
                    vehicles_data,
                )

    async def cleanup_data(self) -> None:
        """Removes all benchmark data."""
        if self.pool is None:
            raise RuntimeError("PostgreSQL connection pool has not been initialized.")

        logger.info("Cleaning PostgreSQL benchmark data")

        async with self.pool.acquire() as conn:
            await conn.execute("TRUNCATE TABLE telemetry;")

    async def write_telemetry_batch(self, batch: list[TelemetryRecord]) -> dict[str, Any]:
        """Writes a batch of telemetry records into PostgreSQL."""

        if self.pool is None:
            raise RuntimeError("PostgreSQL connection pool has not been initialized.")

        import time

        # 1. Format/Serialize outside of the timed block
        rows = [
            (
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
            )
            for r in batch
        ]

        # 2. Acquire connection outside of the timed block
        async with self.pool.acquire() as conn:
            # 3. Time only the actual query execution
            start = time.perf_counter()
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
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
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

    async def execute_query(self, query_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Executes benchmark queries against PostgreSQL."""

        if query_name == "compress":
            return {}

        if self.pool is None:
            raise RuntimeError("PostgreSQL connection pool has not been initialized.")

        import time

        query_map = {
            "total_row_count": "SELECT COUNT(*) FROM telemetry;",
            "time_range_query": """
                SELECT *
                FROM telemetry
                WHERE vehicle_id = $1 AND timestamp BETWEEN $2 AND $3
                ORDER BY timestamp;
            """,
            "aggregation_query": """
                SELECT to_timestamp(floor(extract(epoch from timestamp) / $2) * $2) AS bucket,
                       AVG(battery_percentage) as avg_value
                FROM telemetry
                WHERE vehicle_id = $1 AND timestamp BETWEEN $3 AND $4
                GROUP BY bucket
                ORDER BY bucket;
            """,
            "historical_replay_query": """
                SELECT *
                FROM telemetry
                WHERE mission_id = $1
                ORDER BY timestamp ASC;
            """,
            "join_query": """
                SELECT t.*, v.model, v.manufacturer
                FROM telemetry t
                JOIN vehicles v ON t.vehicle_id = v.vehicle_id
                WHERE t.vehicle_id = $1 AND t.timestamp BETWEEN $2 AND $3
                ORDER BY t.timestamp;
            """,
        }

        if query_name not in query_map:
            raise ValueError(f"Unsupported query: {query_name}")

        start = time.perf_counter()

        async with self.pool.acquire() as conn:
            if query_name == "total_row_count":
                result = await conn.fetchval(query_map[query_name])
                row_count = int(result)
            elif query_name == "time_range_query":
                rows = await conn.fetch(
                    query_map[query_name],
                    params["vehicle_id"],
                    params["start_time"],
                    params["end_time"],
                )
                row_count = len(rows)
            elif query_name == "aggregation_query":
                interval = float(params.get("aggregation_interval_seconds", 60.0))
                rows = await conn.fetch(
                    query_map[query_name],
                    params["vehicle_id"],
                    interval,
                    params["start_time"],
                    params["end_time"],
                )
                row_count = len(rows)
                latency = time.perf_counter() - start
                return {
                    "latency_seconds": latency,
                    "groups_returned": row_count,
                }
            elif query_name == "historical_replay_query":
                rows = await conn.fetch(
                    query_map[query_name],
                    params["mission_id"],
                )
                row_count = len(rows)
            elif query_name == "join_query":
                rows = await conn.fetch(
                    query_map[query_name],
                    params["vehicle_id"],
                    params["start_time"],
                    params["end_time"],
                )
                row_count = len(rows)
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
        """Retrieves total disk storage size consumed by benchmark tables in bytes."""
        if self.pool is None:
            return 0
        try:
            async with self.pool.acquire() as conn:
                size = await conn.fetchval(
                    "SELECT COALESCE(SUM(pg_total_relation_size(c.oid)), 0) "
                    "FROM pg_class c WHERE c.relname IN ('telemetry', 'vehicles');"
                )
                return int(size)
        except Exception:
            return 0
