from pathlib import Path

import yaml


def test_docker_compose_validity() -> None:
    """Parses and validates docker-compose.benchmark.yml against target requirements."""
    compose_path = Path(__file__).parents[1] / "docker-compose.benchmark.yml"
    assert compose_path.exists(), "docker-compose.benchmark.yml must exist"

    with compose_path.open() as f:
        config = yaml.safe_load(f)

    # 1. Check network structure
    assert "networks" in config
    assert "benchmark_net" in config["networks"]
    assert config["networks"]["benchmark_net"]["name"] == "benchmark_net"

    # 2. Check service definitions
    assert "services" in config
    services = config["services"]
    required_services = {"postgres", "timescaledb", "questdb", "clickhouse", "influxdb"}
    assert required_services.issubset(services.keys())

    for name, svc in services.items():
        # Check network membership
        assert "networks" in svc, f"{name} must define networks"
        assert "benchmark_net" in svc["networks"], f"{name} must be on benchmark_net network"

        # Check version pinning (no 'latest' tags allowed)
        assert "image" in svc, f"{name} must define an image"
        image = svc["image"]
        assert ":" in image, f"{name} image '{image}' must contain a version tag"
        tag = image.split(":")[1]
        assert tag != "latest", f"{name} image must pin an exact version (cannot be 'latest')"

        # Check resource limits (identical CPU & Memory limits)
        assert "deploy" in svc, f"{name} must have a deploy configuration"
        deploy = svc["deploy"]
        assert "resources" in deploy, f"{name} deploy must define resources"
        resources = deploy["resources"]
        assert "limits" in resources, f"{name} deploy.resources must define limits"
        limits = resources["limits"]

        assert limits["cpus"] == "2.0", f"{name} must limit CPU to exactly '2.0'"
        # Check memory limit - allow string or numeric representation of 4096M / 4GB
        memory_limit = str(limits["memory"])
        assert memory_limit in (
            "4096M",
            "4G",
            "4GB",
        ), f"{name} memory limit must be exactly 4096M/4GB"

        # Check health checks
        assert "healthcheck" in svc, f"{name} must define a healthcheck"
        health = svc["healthcheck"]
        assert "test" in health, f"{name} healthcheck must define a test command"
        assert len(health["test"]) > 0

        # Check shared results directory mount
        assert "volumes" in svc, f"{name} must define volumes"
        volumes = svc["volumes"]
        has_results_mount = any(
            v == "./results:/results" or (isinstance(v, dict) and v.get("source") == "./results")
            for v in volumes
        )
        assert has_results_mount, f"{name} must mount the shared './results' directory"
