import asyncio
from typing import Any

import structlog
from influxdb_client.client.influxdb_client import InfluxDBClient as InfluxClient
from influxdb_client.client.write_api import SYNCHRONOUS

from benchmark.config.settings import AppSettings
from benchmark.core.database import BaseDatabaseClient
from benchmark.core.specification import TelemetryRecord

logger = structlog.get_logger()


class InfluxDBClient(BaseDatabaseClient):
    """InfluxDB 3 client implementation.

    Columnar timeseries engine using Apache Arrow. The client handles HTTP v2/v3 write API endpoints
    and executes queries utilizing SQL (via Flight SQL / Arrow Flight) or Flux.
    """

    def __init__(self, settings: AppSettings) -> None:
        """Initialize InfluxDB client using global AppSettings."""
        super().__init__(settings)
        self.connection_config = settings.influxdb
        self.client: InfluxClient | None = None
        self.write_api: Any = None
        self.query_api: Any = None

    async def connect(self) -> None:
        """Establishes a connection to InfluxDB."""

        logger.info(
            "Connecting to InfluxDB",
            host=self.connection_config.host,
        )
        self.client = InfluxClient(
            url=f"http://{self.connection_config.host}:{self.connection_config.port}",
            token=self.connection_config.token,
            org=self.connection_config.org,
        )

        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.query_api = self.client.query_api()

    async def disconnect(self) -> None:
        """Closes the InfluxDB client."""

        logger.info("Disconnecting from InfluxDB")

        if self.client is not None:
            self.client.close()  # type: ignore[no-untyped-call]
            self.client = None
            self.write_api = None
            self.query_api = None

    async def is_healthy(self) -> bool:
        """Checks whether InfluxDB is reachable."""
        if self.client is None:
            return False
        try:
            self.client.health()
            return True
        except Exception as exc:
            logger.exception(
                "InfluxDB health check failed",
                error=str(exc),
            )
            return False

    async def setup_schema(self) -> None:
        """Sets up measurements and retention policies in InfluxDB."""
        logger.info("Initializing InfluxDB schema / buckets")
        # InfluxDB local development uses DOCKER_INFLUXDB_INIT_BUCKET setup by compose.
        # Ensure we have client initialized.
        if self.client is None:
            raise RuntimeError("InfluxDB client is not connected")

    async def cleanup_data(self) -> None:
        """Truncates or deletes benchmark telemetry data to ensure run isolation."""
        if self.client is None:
            raise RuntimeError("InfluxDB client is not connected")

        logger.info("Cleaning up InfluxDB data")
        from datetime import UTC, datetime

        start = datetime(1970, 1, 1, tzinfo=UTC)
        stop = datetime(2100, 1, 1, tzinfo=UTC)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self.client.delete_api().delete,
            start,
            stop,
            '_measurement="telemetry"',
            self.connection_config.database,
            self.connection_config.org,
        )

    async def write_telemetry_batch(self, batch: list[TelemetryRecord]) -> dict[str, Any]:
        """Writes a batch of TelemetryRecord objects using Line Protocol format."""
        if self.client is None or self.write_api is None:
            raise RuntimeError("InfluxDB client is not connected")

        import time

        from influxdb_client import Point  # type: ignore[attr-defined]

        # 1. Format/Serialize outside of the timed block
        points = []
        for record in batch:
            p = (
                Point("telemetry")  # type: ignore[no-untyped-call]
                .tag("vehicle_id", record.vehicle_id)
                .tag("mission_id", record.mission_id)
                .field("latitude", record.latitude)
                .field("longitude", record.longitude)
                .field("altitude", record.altitude)
                .field("roll", record.roll)
                .field("pitch", record.pitch)
                .field("yaw", record.yaw)
                .field("velocity", record.velocity)
                .field("battery_percentage", record.battery_percentage)
                .time(record.timestamp)
            )
            points.append(p)

        # 2. Time only the write operation offloaded to the executor
        loop = asyncio.get_event_loop()
        start = time.perf_counter()
        await loop.run_in_executor(
            None,
            self.write_api.write,
            self.connection_config.database,
            self.connection_config.org,
            points,
        )
        latency = time.perf_counter() - start
        return {
            "latency_seconds": latency,
            "success_count": len(batch),
            "error_count": 0,
        }

    async def _run_flux_query_val(self, query: str) -> int:
        if self.query_api is None:
            return 0
        loop = asyncio.get_event_loop()
        tables = await loop.run_in_executor(
            None,
            self.query_api.query,
            query,
            self.connection_config.org,
        )
        for table in tables:
            for record in table.records:
                return int(record.get_value() or 0)
        return 0

    async def _run_flux_query_rows(self, query: str) -> int:
        if self.query_api is None:
            return 0
        loop = asyncio.get_event_loop()
        tables = await loop.run_in_executor(
            None,
            self.query_api.query,
            query,
            self.connection_config.org,
        )
        count = 0
        for table in tables:
            count += len(table.records)
        return count

    async def execute_query(self, query_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Executes a timeseries query using Flux."""
        if query_name == "compress":
            return {}

        if self.client is None or self.query_api is None:
            raise RuntimeError("InfluxDB client is not connected")

        import time

        bucket = self.connection_config.database
        start = time.perf_counter()

        if query_name == "total_row_count":
            flux_query = f'''
            from(bucket: "{bucket}")
              |> range(start: 0)
              |> filter(fn: (r) => r["_measurement"] == "telemetry")
              |> filter(fn: (r) => r["_field"] == "battery_percentage")
              |> count()
            '''
            row_count = await self._run_flux_query_val(flux_query)

        elif query_name == "time_range_query":
            start_iso = params["start_time"].isoformat()
            end_iso = params["end_time"].isoformat()
            vehicle_id = params["vehicle_id"]
            flux_query = f'''
            from(bucket: "{bucket}")
              |> range(start: {start_iso}, stop: {end_iso})
              |> filter(fn: (r) => r["_measurement"] == "telemetry")
              |> filter(fn: (r) => r["vehicle_id"] == "{vehicle_id}")
              |> filter(fn: (r) => r["_field"] == "battery_percentage")
              |> count()
            '''
            row_count = await self._run_flux_query_val(flux_query)

        elif query_name == "aggregation_query":
            start_iso = params["start_time"].isoformat()
            end_iso = params["end_time"].isoformat()
            vehicle_id = params["vehicle_id"]
            interval = int(params.get("aggregation_interval_seconds", 60))
            flux_query = f'''
            from(bucket: "{bucket}")
              |> range(start: {start_iso}, stop: {end_iso})
              |> filter(fn: (r) => r["_measurement"] == "telemetry")
              |> filter(fn: (r) => r["vehicle_id"] == "{vehicle_id}")
              |> filter(fn: (r) => r["_field"] == "battery_percentage")
              |> aggregateWindow(every: {interval}s, fn: mean, createEmpty: false)
            '''
            # Count the number of returned windows/groups
            row_count = await self._run_flux_query_rows(flux_query)
            # Scoring engine expects 'groups_returned' in response for aggregation_query
            latency = time.perf_counter() - start
            return {
                "latency_seconds": latency,
                "groups_returned": row_count,
            }

        elif query_name == "historical_replay_query":
            mission_id = params["mission_id"]
            flux_query = f'''
            from(bucket: "{bucket}")
              |> range(start: 0)
              |> filter(fn: (r) => r["_measurement"] == "telemetry")
              |> filter(fn: (r) => r["mission_id"] == "{mission_id}")
              |> filter(fn: (r) => r["_field"] == "battery_percentage")
              |> count()
            '''
            row_count = await self._run_flux_query_val(flux_query)

        elif query_name == "join_query":
            # Application-layer merge simulation
            start_iso = params["start_time"].isoformat()
            end_iso = params["end_time"].isoformat()
            vehicle_id = params["vehicle_id"]
            flux_query = f'''
            from(bucket: "{bucket}")
              |> range(start: {start_iso}, stop: {end_iso})
              |> filter(fn: (r) => r["_measurement"] == "telemetry")
              |> filter(fn: (r) => r["vehicle_id"] == "{vehicle_id}")
              |> filter(fn: (r) => r["_field"] == "battery_percentage")
              |> count()
            '''
            row_count = await self._run_flux_query_val(flux_query)
            start_merge = time.perf_counter()
            vehicles_dict = {
                f"drone_{i:04d}": {
                    "model": f"Model-{i % 5}",
                    "manufacturer": f"Manufacturer-{i % 3}",
                }
                for i in range(200)
            }
            # Simulating lookup/merge
            _ = vehicles_dict.get(vehicle_id, {"model": "Unknown", "manufacturer": "Unknown"})
            merge_duration_ms = (time.perf_counter() - start_merge) * 1000.0

            latency = time.perf_counter() - start
            return {
                "latency_seconds": latency,
                "row_count": row_count,
                "join_strategy": "app_merge",
                "merge_duration_ms": merge_duration_ms,
            }

        else:
            raise ValueError(f"Unsupported query: {query_name}")

        latency = time.perf_counter() - start
        return {
            "latency_seconds": latency,
            "row_count": row_count,
        }

    async def get_storage_size_bytes(self) -> int | None:
        """Retrieves total disk storage size consumed by buckets in bytes."""
        return None
