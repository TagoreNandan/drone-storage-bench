from typing import Any

import structlog
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING

from benchmark.config.settings import AppSettings
from benchmark.core.database import BaseDatabaseClient
from benchmark.core.specification import TelemetryRecord

logger = structlog.get_logger()


class MongoDBClient(BaseDatabaseClient):
    """MongoDB client implementation."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)

        self.connection_config = settings.mongodb

        self.client: Any = None
        self.database: Any = None
        self.collection: Any = None

    async def connect(self) -> None:
        """Connect to MongoDB."""

        logger.info(
            "Connecting to MongoDB",
            host=self.connection_config.host,
        )

        uri = (
            f"mongodb://{self.connection_config.user}:"
            f"{self.connection_config.password}@"
            f"{self.connection_config.host}:"
            f"{self.connection_config.port}/"
        )

        self.client = AsyncIOMotorClient[Any](uri)

        self.database = self.client[self.connection_config.database]
        self.collection = self.database.telemetry

    async def disconnect(self) -> None:
        """Disconnect from MongoDB."""

        logger.info("Disconnecting from MongoDB")

        if self.client is not None:
            self.client.close()

        self.client = None
        self.database = None
        self.collection = None

    async def is_healthy(self) -> bool:
        """Health check."""

        if self.client is None:
            return False

        try:
            await self.client.admin.command("ping")
            return True
        except Exception as exc:
            logger.exception(
                "MongoDB health check failed",
                error=str(exc),
            )
            return False

    async def setup_schema(self) -> None:
        """Create indexes."""

        collection = self.collection
        if collection is None:
            raise RuntimeError("MongoDB collection not initialized.")

        logger.info("Creating MongoDB indexes")

        await collection.create_index([("timestamp", ASCENDING)])

        await self.collection.create_index(
            [
                ("vehicle_id", ASCENDING),
                ("timestamp", ASCENDING),
            ]
        )

    async def cleanup_data(self) -> None:
        """Delete telemetry collection."""

        collection = self.collection
        if collection is None:
            raise RuntimeError("MongoDB collection not initialized.")

        logger.info("Cleaning MongoDB benchmark data")

        await collection.delete_many({})

    async def write_telemetry_batch(
        self,
        batch: list[TelemetryRecord],
    ) -> dict[str, Any]:
        """Write a telemetry batch."""

        collection = self.collection
        if collection is None:
            raise RuntimeError("MongoDB collection not initialized.")

        import time

        # 1. Format/Serialize outside of the timed block
        documents = [
            {
                "timestamp": record.timestamp,
                "vehicle_id": record.vehicle_id,
                "mission_id": record.mission_id,
                "latitude": record.latitude,
                "longitude": record.longitude,
                "altitude": record.altitude,
                "roll": record.roll,
                "pitch": record.pitch,
                "yaw": record.yaw,
                "velocity": record.velocity,
                "battery_percentage": record.battery_percentage,
            }
            for record in batch
        ]

        # 2. Time only the database insert operation
        start = time.perf_counter()
        await collection.insert_many(documents, ordered=False)
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
        """Execute benchmark queries."""

        if query_name == "compress":
            return {}

        collection = self.collection
        if collection is None:
            raise RuntimeError("MongoDB collection not initialized.")

        import time

        start = time.perf_counter()

        if query_name == "total_row_count":
            row_count = await self.collection.count_documents({})

        elif query_name == "time_range_query":
            cursor = self.collection.find(
                {
                    "vehicle_id": params["vehicle_id"],
                    "timestamp": {
                        "$gte": params["start_time"],
                        "$lte": params["end_time"],
                    },
                }
            )
            rows = await cursor.to_list(length=None)
            row_count = len(rows)

        elif query_name == "aggregation_query":
            interval = params.get("aggregation_interval_seconds", 60.0)
            pipeline = [
                {
                    "$match": {
                        "vehicle_id": params["vehicle_id"],
                        "timestamp": {
                            "$gte": params["start_time"],
                            "$lte": params["end_time"],
                        },
                    }
                },
                {
                    "$project": {
                        "bucket": {
                            "$toDate": {
                                "$subtract": [
                                    {"$toLong": "$timestamp"},
                                    {"$mod": [{"$toLong": "$timestamp"}, int(interval * 1000)]},
                                ]
                            }
                        },
                        "battery_percentage": 1,
                    }
                },
                {
                    "$group": {
                        "_id": "$bucket",
                        "avg_value": {"$avg": "$battery_percentage"},
                    }
                },
            ]
            cursor = self.collection.aggregate(pipeline)
            rows = await cursor.to_list(length=None)
            row_count = len(rows)
            latency = time.perf_counter() - start
            return {
                "latency_seconds": latency,
                "groups_returned": row_count,
            }

        elif query_name == "historical_replay_query":
            cursor = self.collection.find({"mission_id": params["mission_id"]}).sort("timestamp", 1)
            rows = await cursor.to_list(length=None)
            row_count = len(rows)

        elif query_name == "join_query":
            cursor = self.collection.find(
                {
                    "vehicle_id": params["vehicle_id"],
                    "timestamp": {
                        "$gte": params["start_time"],
                        "$lte": params["end_time"],
                    },
                }
            )
            rows = await cursor.to_list(length=None)
            row_count = len(rows)

            start_merge = time.perf_counter()
            vehicles_dict = {
                f"drone_{i:04d}": {
                    "model": f"Model-{i % 5}",
                    "manufacturer": f"Manufacturer-{i % 3}",
                }
                for i in range(200)
            }
            joined_rows = []
            for r in rows:
                v_meta = vehicles_dict.get(
                    r.get("vehicle_id", ""), {"model": "Unknown", "manufacturer": "Unknown"}
                )
                joined_row = {**r, **v_meta}
                joined_rows.append(joined_row)
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
        """Return storage size."""

        if self.database is None:
            return 0

        stats = await self.database.command(
            "collStats",
            "telemetry",
        )

        return int(stats.get("storageSize", 0))
