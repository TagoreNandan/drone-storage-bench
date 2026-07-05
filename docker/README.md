# Database Configuration Overrides

This directory contains database-specific configuration files, custom init scripts, or Dockerfiles used to tune each target database under identical system configurations.

## Directory Structure

- `postgres/`: Configurations and initialization scripts for the relational control plane database.
- `timescaledb/`: Optimized `postgresql.conf` parameters (e.g. timescaledb-tune) for timeseries workloads.
- `questdb/`: custom `server.conf` overrides.
- `clickhouse/`: ClickHouse XML configurations (e.g. memory settings, user permissions).
- `influxdb/`: InfluxDB 3 / v2 configuration overrides.
