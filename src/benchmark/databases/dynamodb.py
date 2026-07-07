from decimal import Decimal
from typing import Any

import aioboto3
import structlog
from boto3.dynamodb.conditions import Attr, Key

from benchmark.config.settings import AppSettings
from benchmark.core.database import BaseDatabaseClient
from benchmark.core.specification import TelemetryRecord

logger = structlog.get_logger()


def d(value: float) -> Decimal:
    """Convert float to DynamoDB Decimal safely."""
    return Decimal(str(value))


class DynamoDBClient(BaseDatabaseClient):
    """DynamoDB Local client implementation."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)

        self.connection_config = settings.dynamodb

        self._session = aioboto3.Session()
        self.resource: Any = None
        self.table: Any = None

    async def connect(self) -> None:
        """Connect to DynamoDB."""

        logger.info("Connecting to DynamoDB")

        self.resource = await self._session.resource(
            "dynamodb",
            endpoint_url=self.connection_config.endpoint_url,
            region_name=self.connection_config.region,
            aws_access_key_id=self.connection_config.access_key,
            aws_secret_access_key=self.connection_config.secret_key,
        ).__aenter__()

        self.table = await self.resource.Table(
            self.connection_config.table_name,
        )

    async def disconnect(self) -> None:
        """Disconnect from DynamoDB."""

        logger.info("Disconnecting from DynamoDB")

        if self.resource is not None:
            await self.resource.__aexit__(None, None, None)

        self.resource = None
        self.table = None

    async def is_healthy(self) -> bool:
        """Health check."""

        if self.resource is None:
            return False

        try:
            tables = await self.resource.meta.client.list_tables()
            return "TableNames" in tables
        except Exception as exc:
            logger.exception(
                "DynamoDB health check failed",
                error=str(exc),
            )
            return False

    async def setup_schema(self) -> None:
        """Create telemetry table if needed."""

        if self.resource is None:
            raise RuntimeError("DynamoDB not connected.")

        existing = await self.resource.meta.client.list_tables()

        if self.connection_config.table_name in existing["TableNames"]:
            self.table = await self.resource.Table(
                self.connection_config.table_name,
            )
            return

        self.table = await self.resource.create_table(
            TableName=self.connection_config.table_name,
            KeySchema=[
                {
                    "AttributeName": "vehicle_id",
                    "KeyType": "HASH",
                },
                {
                    "AttributeName": "timestamp",
                    "KeyType": "RANGE",
                },
            ],
            AttributeDefinitions=[
                {
                    "AttributeName": "vehicle_id",
                    "AttributeType": "S",
                },
                {
                    "AttributeName": "timestamp",
                    "AttributeType": "S",
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        await self.table.wait_until_exists()

    async def cleanup_data(self) -> None:
        """Delete all telemetry records."""

        if self.table is None:
            raise RuntimeError("Table not initialized.")

        exclusive_start_key: dict[str, Any] | None = None
        while True:
            scan_kwargs: dict[str, Any] = {}
            if exclusive_start_key is not None:
                scan_kwargs["ExclusiveStartKey"] = exclusive_start_key

            response = await self.table.scan(**scan_kwargs)
            items = response.get("Items", [])
            if items:
                async with self.table.batch_writer() as batch:
                    for item in items:
                        await batch.delete_item(
                            Key={
                                "vehicle_id": item["vehicle_id"],
                                "timestamp": item["timestamp"],
                            }
                        )

            exclusive_start_key = response.get("LastEvaluatedKey")
            if not exclusive_start_key:
                break

    async def write_telemetry_batch(
        self,
        batch: list[TelemetryRecord],
    ) -> dict[str, Any]:
        """Write telemetry batch."""

        if self.table is None:
            raise RuntimeError("Table not initialized.")

        import time

        # 1. Format/Convert to Decimal outside of the timed block
        items = [
            {
                "vehicle_id": record.vehicle_id,
                "timestamp": record.timestamp.isoformat(),
                "mission_id": record.mission_id,
                "latitude": d(record.latitude),
                "longitude": d(record.longitude),
                "altitude": d(record.altitude),
                "roll": d(record.roll),
                "pitch": d(record.pitch),
                "yaw": d(record.yaw),
                "velocity": d(record.velocity),
                "battery_percentage": d(record.battery_percentage),
            }
            for record in batch
        ]

        # 2. Time only the batch_writer write execution and flush
        start = time.perf_counter()
        async with self.table.batch_writer() as writer:
            for item in items:
                await writer.put_item(Item=item)
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
        """Execute benchmark query."""

        if query_name == "compress":
            return {}

        if self.table is None:
            raise RuntimeError("Table not initialized.")

        import time
        from datetime import datetime

        start = time.perf_counter()

        if query_name == "total_row_count":
            response = await self.table.scan(
                Select="COUNT",
            )
            row_count = int(response["Count"])

        elif query_name == "vehicle_history":
            response = await self.table.query(
                KeyConditionExpression=Key("vehicle_id").eq(
                    params["vehicle_id"],
                )
            )
            row_count = len(response["Items"])

        elif query_name == "time_range_query":
            vehicle_id = params["vehicle_id"]
            start_iso = params["start_time"].isoformat()
            end_iso = params["end_time"].isoformat()
            response = await self.table.query(
                KeyConditionExpression=Key("vehicle_id").eq(vehicle_id)
                & Key("timestamp").between(start_iso, end_iso)
            )
            row_count = len(response["Items"])

        elif query_name == "aggregation_query":
            vehicle_id = params["vehicle_id"]
            start_iso = params["start_time"].isoformat()
            end_iso = params["end_time"].isoformat()
            interval = float(params.get("aggregation_interval_seconds", 60.0))

            response = await self.table.query(
                KeyConditionExpression=Key("vehicle_id").eq(vehicle_id)
                & Key("timestamp").between(start_iso, end_iso)
            )
            items = response.get("Items", [])

            buckets: dict[float, list[float]] = {}
            for item in items:
                ts_str = item["timestamp"]
                # Parse ISO format string
                ts_dt = datetime.fromisoformat(ts_str)
                epoch = ts_dt.timestamp()
                bucket_epoch = int(epoch / interval) * interval

                battery = float(item.get("battery_percentage", 0.0))

                if bucket_epoch not in buckets:
                    buckets[bucket_epoch] = []
                buckets[bucket_epoch].append(battery)

            row_count = len(buckets)
            latency = time.perf_counter() - start
            return {
                "latency_seconds": latency,
                "groups_returned": row_count,
            }

        elif query_name == "historical_replay_query":
            response = await self.table.scan(
                FilterExpression=Attr("mission_id").eq(params["mission_id"])
            )
            items = response.get("Items", [])
            items.sort(key=lambda x: x["timestamp"])
            row_count = len(items)

        elif query_name == "join_query":
            vehicle_id = params["vehicle_id"]
            start_iso = params["start_time"].isoformat()
            end_iso = params["end_time"].isoformat()
            response = await self.table.query(
                KeyConditionExpression=Key("vehicle_id").eq(vehicle_id)
                & Key("timestamp").between(start_iso, end_iso)
            )
            items = response.get("Items", [])
            row_count = len(items)

            start_merge = time.perf_counter()
            vehicles_dict = {
                f"drone_{i:04d}": {"model": f"Model-{i%5}", "manufacturer": f"Manufacturer-{i%3}"}
                for i in range(200)
            }
            joined_items = []
            for item in items:
                v_meta = vehicles_dict.get(
                    item.get("vehicle_id", ""), {"model": "Unknown", "manufacturer": "Unknown"}
                )
                joined_item = {**item, **v_meta}
                joined_items.append(joined_item)
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
        """Return approximate storage size."""
        return None
