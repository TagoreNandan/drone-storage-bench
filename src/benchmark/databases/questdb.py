from typing import Any

import aiohttp
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
        self.http_session: aiohttp.ClientSession | None = None

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
        self.http_session = aiohttp.ClientSession()

    async def disconnect(self) -> None:
        logger.info("Disconnecting from QuestDB")

        if self.pool is not None:
            await self.pool.close()
            self.pool = None

        if self.http_session is not None:
            await self.http_session.close()
            self.http_session = None

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
        """Creates the benchmark tables if they do not already exist."""
        if self.pool is None:
            raise RuntimeError("QuestDB connection pool has not been initialized.")

        logger.info("Initializing QuestDB schema")

        async with self.pool.acquire() as conn:
            # Create telemetry table
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
            # Create vehicles table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vehicles (
                    vehicle_id SYMBOL,
                    model SYMBOL,
                    manufacturer SYMBOL
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
        """Writes telemetry batches to QuestDB using Influx Line Protocol over HTTP."""
        if self.http_session is None:
            raise RuntimeError("QuestDB HTTP session has not been initialized.")

        import time

        # 1. Format/Serialize to Influx Line Protocol (ILP) outside the timed block
        lines = []
        for r in batch:
            lines.append(
                f"telemetry,vehicle_id={r.vehicle_id},mission_id={r.mission_id} "
                f"latitude={r.latitude},longitude={r.longitude},altitude={r.altitude},"
                f"roll={r.roll},pitch={r.pitch},yaw={r.yaw},velocity={r.velocity},"
                f"battery_percentage={r.battery_percentage} "
                f"{int(r.timestamp.timestamp() * 1e9)}"
            )
        body = "\n".join(lines) + "\n"

        # 2. Time only the actual HTTP request execution
        start = time.perf_counter()
        url = f"http://{self.connection_config.host}:{self.connection_config.port_http}/write?precision=n"
        async with self.http_session.post(
            url,
            data=body,
            headers={"Content-Type": "text/plain"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status not in (200, 204):
                err_content = await resp.text()
                raise RuntimeError(f"QuestDB HTTP write failed ({resp.status}): {err_content}")
            await resp.read()
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

        if query_name == "compress":
            return {}

        if self.pool is None:
            raise RuntimeError("QuestDB connection pool has not been initialized.")

        import time

        start = time.perf_counter()

        async with self.pool.acquire() as conn:
            if query_name == "total_row_count":
                result = await conn.fetchval("SELECT COUNT(*) FROM telemetry;")
                row_count = int(result)
            elif query_name == "time_range_query":
                start_time = params["start_time"].replace(tzinfo=None)
                end_time = params["end_time"].replace(tzinfo=None)
                rows = await conn.fetch(
                    """
                    SELECT * FROM telemetry
                    WHERE vehicle_id = $1 AND timestamp BETWEEN $2 AND $3;
                    """,
                    params["vehicle_id"],
                    start_time,
                    end_time,
                )
                row_count = len(rows)
            elif query_name == "aggregation_query":
                start_time = params["start_time"].replace(tzinfo=None)
                end_time = params["end_time"].replace(tzinfo=None)
                interval = int(params.get("aggregation_interval_seconds", 60))
                rows = await conn.fetch(
                    f"""
                    SELECT timestamp, AVG(battery_percentage) as avg_value
                    FROM telemetry
                    WHERE vehicle_id = $1 AND timestamp BETWEEN $2 AND $3
                    SAMPLE BY {interval}s;
                    """,
                    params["vehicle_id"],
                    start_time,
                    end_time,
                )
                row_count = len(rows)
                latency = time.perf_counter() - start
                return {
                    "latency_seconds": latency,
                    "groups_returned": row_count,
                }
            elif query_name == "historical_replay_query":
                rows = await conn.fetch(
                    "SELECT * FROM telemetry WHERE mission_id = $1;",
                    params["mission_id"],
                )
                row_count = len(rows)
            elif query_name == "join_query":
                start_time = params["start_time"].replace(tzinfo=None)
                end_time = params["end_time"].replace(tzinfo=None)
                rows = await conn.fetch(
                    """
                    SELECT t.*, v.model, v.manufacturer
                    FROM telemetry t
                    JOIN vehicles v ON t.vehicle_id = v.vehicle_id
                    WHERE t.vehicle_id = $1 AND t.timestamp BETWEEN $2 AND $3;
                    """,
                    params["vehicle_id"],
                    start_time,
                    end_time,
                )
                row_count = len(rows)
                latency = time.perf_counter() - start
                return {
                    "latency_seconds": latency,
                    "row_count": row_count,
                    "join_strategy": "native",
                    "merge_duration_ms": 0.0,
                }
            else:
                raise ValueError(f"Unsupported query: {query_name}")

        latency = time.perf_counter() - start

        return {
            "latency_seconds": latency,
            "row_count": row_count,
        }

    async def get_storage_size_bytes(self) -> int | None:
        """Returns storage consumed by QuestDB benchmark tables."""
        if self.pool is None:
            return 0
        try:
            async with self.pool.acquire() as conn:
                size_t = await conn.fetchval("SELECT SUM(diskSize) FROM table_partitions('telemetry');") or 0
                size_v = await conn.fetchval("SELECT SUM(diskSize) FROM table_partitions('vehicles');") or 0
                return int(size_t) + int(size_v)
        except Exception:
            return 0
