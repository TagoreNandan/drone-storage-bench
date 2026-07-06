from __future__ import annotations

import threading
import time

import psutil


class ResourceMonitor:
    """Continuously monitors CPU and memory usage during benchmark execution."""

    def __init__(self, interval: float = 0.5) -> None:
        self.interval = interval
        self._cpu_samples: list[float] = []
        self._memory_samples: list[float] = []
        self._running = False
        self._thread: threading.Thread | None = None

    def _monitor(self) -> None:
        """Background sampling loop."""
        process = psutil.Process()

        while self._running:
            self._cpu_samples.append(process.cpu_percent())
            self._memory_samples.append(process.memory_info().rss / (1024 * 1024))
            time.sleep(self.interval)

    def start(self) -> None:
        """Start resource monitoring."""
        self._running = True
        self._thread = threading.Thread(
            target=self._monitor,
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop resource monitoring."""
        self._running = False

        if self._thread is not None:
            self._thread.join()

    def summary(self) -> dict[str, float]:
        """Return aggregated resource statistics."""

        return {
            "avg_cpu_percent": (
                sum(self._cpu_samples) / len(self._cpu_samples) if self._cpu_samples else 0.0
            ),
            "peak_cpu_percent": (max(self._cpu_samples) if self._cpu_samples else 0.0),
            "avg_memory_mb": (
                sum(self._memory_samples) / len(self._memory_samples)
                if self._memory_samples
                else 0.0
            ),
            "peak_memory_mb": (max(self._memory_samples) if self._memory_samples else 0.0),
        }
