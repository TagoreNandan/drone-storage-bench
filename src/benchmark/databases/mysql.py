from typing import Any

import aiomysql
import structlog

from benchmark.config.settings import AppSettings
from benchmark.core.database import BaseDatabaseClient
from benchmark.core.specification import TelemetryRecord

logger = structlog.get_logger()


class MySQLClient(BaseDatabaseClient):
    """MySQL client implementation."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)
        self.connection_config = settings.mysql
        self.pool: aiomysql.Pool | None = None

    async def connect(self) -> None:
        """Connect to MySQL."""

        logger.info(
            "Connecting to MySQL",
            host=self.connection_config.host,
        )

        self.pool = await aiomysql.create_pool(
            host=self.connection_config.host,
            port=self.connection_config.port,
            user=self.connection_config.user,
            password=self.connection_config.password,
            db=self.connection_config.database,
            minsize=1,
            maxsize=10,
            autocommit=True,
        )

    async def disconnect(self) -> None:
        """Disconnect from MySQL."""

        logger.info("Disconnecting from MySQL")

        if self.pool is not None:
            self.pool.close()
            await self.pool.wait_closed()
            self.pool = None

    async def is_healthy(self) -> bool:
        """Check database connectivity."""

        if self.pool is None:
            return False

        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1;")
                    await cur.fetchone()

            return True

        except Exception as exc:
            logger.exception(
                "MySQL health check failed",
                error=str(exc),
            )
            return False

    async def setup_schema(self) -> None:
        """Creates the benchmark tables if they do not already exist."""
        if self.pool is None:
            raise RuntimeError("MySQL connection pool has not been initialized.")

        logger.info("Initializing MySQL schema")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS telemetry (
                        timestamp DATETIME(6),
                        vehicle_id VARCHAR(64),
                        mission_id VARCHAR(64),
                        latitude DOUBLE,
                        longitude DOUBLE,
                        altitude DOUBLE,
                        roll DOUBLE,
                        pitch DOUBLE,
                        yaw DOUBLE,
                        velocity DOUBLE,
                        battery_percentage DOUBLE
                    );
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS vehicles (
                        vehicle_id VARCHAR(50) PRIMARY KEY,
                        model VARCHAR(100),
                        manufacturer VARCHAR(100)
                    );
                    """
                )
                # Check if vehicles table is empty, if so populate it
                await cur.execute("SELECT COUNT(*) FROM vehicles;")
                result = await cur.fetchone()
                count = int(result[0])
                if count == 0:
                    vehicles_data = [
                        (f"drone_{i:04d}", f"Model-{i % 5}", f"Manufacturer-{i % 3}")
                        for i in range(200)
                    ]
                    await cur.executemany(
                        """
                        INSERT INTO vehicles (vehicle_id, model, manufacturer)
                        VALUES (%s, %s, %s);
                        """,
                        vehicles_data,
                    )

    async def cleanup_data(self) -> None:
        """Remove all benchmark data."""

        if self.pool is None:
            raise RuntimeError("MySQL connection pool has not been initialized.")

        logger.info("Cleaning MySQL benchmark data")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("TRUNCATE TABLE telemetry;")

    async def write_telemetry_batch(
        self,
        batch: list[TelemetryRecord],
    ) -> dict[str, Any]:
        """Write a batch of telemetry records into MySQL."""

        if self.pool is None:
            raise RuntimeError("MySQL connection pool has not been initialized.")

        import time

        # 1. Format/Serialize outside of the timed block
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

        # 2. Acquire connection and cursor outside of the timed block
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 3. Time only SQL execution
                start = time.perf_counter()
                await cur.executemany(
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
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
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

        if query_name == "compress":
            return {}

        if self.pool is None:
            raise RuntimeError("MySQL connection pool has not been initialized.")

        import time

        query_map = {
            "total_row_count": "SELECT COUNT(*) FROM telemetry;",
            "time_range_query": """
                SELECT *
                FROM telemetry
                WHERE vehicle_id = %s AND timestamp BETWEEN %s AND %s
                ORDER BY timestamp;
            """,
            "aggregation_query": """
                SELECT FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP(timestamp) / %s) * %s) AS bucket,
                       AVG(battery_percentage) as avg_value
                FROM telemetry
                WHERE vehicle_id = %s AND timestamp BETWEEN %s AND %s
                GROUP BY bucket
                ORDER BY bucket;
            """,
            "historical_replay_query": """
                SELECT *
                FROM telemetry
                WHERE mission_id = %s
                ORDER BY timestamp ASC;
            """,
            "join_query": """
                SELECT t.*, v.model, v.manufacturer
                FROM telemetry t
                JOIN vehicles v ON t.vehicle_id = v.vehicle_id
                WHERE t.vehicle_id = %s AND t.timestamp BETWEEN %s AND %s
                ORDER BY t.timestamp;
            """,
        }

        if query_name not in query_map:
            raise ValueError(f"Unsupported query: {query_name}")

        start = time.perf_counter()

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                if query_name == "total_row_count":
                    await cur.execute(query_map[query_name])
                    result = await cur.fetchone()
                    row_count = int(result[0])
                elif query_name == "time_range_query":
                    await cur.execute(
                        query_map[query_name],
                        (
                            params["vehicle_id"],
                            params["start_time"],
                            params["end_time"],
                        ),
                    )
                    rows = await cur.fetchall()
                    row_count = len(rows)
                elif query_name == "aggregation_query":
                    interval = float(params.get("aggregation_interval_seconds", 60.0))
                    await cur.execute(
                        query_map[query_name],
                        (
                            interval,
                            interval,
                            params["vehicle_id"],
                            params["start_time"],
                            params["end_time"],
                        ),
                    )
                    rows = await cur.fetchall()
                    row_count = len(rows)
                    latency = time.perf_counter() - start
                    return {
                        "latency_seconds": latency,
                        "groups_returned": row_count,
                    }
                elif query_name == "historical_replay_query":
                    await cur.execute(
                        query_map[query_name],
                        (params["mission_id"],),
                    )
                    rows = await cur.fetchall()
                    row_count = len(rows)
                elif query_name == "join_query":
                    await cur.execute(
                        query_map[query_name],
                        (
                            params["vehicle_id"],
                            params["start_time"],
                            params["end_time"],
                        ),
                    )
                    rows = await cur.fetchall()
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
        """Return storage used by the telemetry and vehicles tables."""

        if self.pool is None:
            raise RuntimeError("MySQL connection pool has not been initialized.")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT
                        COALESCE(SUM(DATA_LENGTH + INDEX_LENGTH), 0)
                    FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME IN ('telemetry', 'vehicles');
                    """
                )

                result = await cur.fetchone()

        return int(result[0] or 0)
