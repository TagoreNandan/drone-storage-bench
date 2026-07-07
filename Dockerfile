# Use python 3.13-slim as base
FROM python:3.13-slim

# Copy uv binary from astral-sh image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency and metadata files
COPY pyproject.toml uv.lock README.md ./

# Install dependencies (without dev group) using system Python environment
RUN uv sync --frozen --no-dev

# Copy source files and configuration
COPY src/ ./src/
COPY benchmark.yaml ./

# Ensure results folder exists
RUN mkdir -p results

# Run the benchmark CLI
ENTRYPOINT ["uv", "run", "python", "-m", "benchmark.runners.cli", "run", "--config", "benchmark.yaml"]
