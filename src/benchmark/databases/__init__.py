"""Database client drivers implementation for drone-storage-bench.

This package houses the individual client implementations for the four evaluated databases
(ClickHouse, TimescaleDB, QuestDB, InfluxDB 3) and the PostgreSQL control plane.
"""

from collections.abc import Callable

from benchmark.config.settings import AppSettings
from benchmark.core.database import BaseDatabaseClient
from benchmark.databases.clickhouse import ClickHouseClient
from benchmark.databases.dynamodb import DynamoDBClient
from benchmark.databases.influxdb import InfluxDBClient
from benchmark.databases.mongodb import MongoDBClient
from benchmark.databases.mysql import MySQLClient
from benchmark.databases.postgresql import PostgreSQLClient
from benchmark.databases.questdb import QuestDBClient
from benchmark.databases.timescaledb import TimescaleDBClient

# Registry mapping configuration keys to database client constructor callables.
# Using Callable prevents mypy abstract class instantiation warnings.
DB_CLIENT_REGISTRY: dict[str, Callable[[AppSettings], BaseDatabaseClient]] = {
    "postgres": PostgreSQLClient,
    "mysql": MySQLClient,
    "timescaledb": TimescaleDBClient,
    "questdb": QuestDBClient,
    "clickhouse": ClickHouseClient,
    "influxdb": InfluxDBClient,
    "mongodb": MongoDBClient,
    "dynamodb": DynamoDBClient,
}

__all__ = [
    "DB_CLIENT_REGISTRY",
    "ClickHouseClient",
    "DynamoDBClient",
    "InfluxDBClient",
    "MongoDBClient",
    "MySQLClient",
    "PostgreSQLClient",
    "QuestDBClient",
    "TimescaleDBClient",
]
