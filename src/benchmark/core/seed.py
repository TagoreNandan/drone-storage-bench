import random
from collections.abc import Generator


class DeterministicSeedManager:
    """Manages deterministic pseudo-random state across benchmark workers.

    Ensures that telemetry generation, drone routes, and query patterns
    are repeatable across database comparison runs.
    """

    def __init__(self, seed: int) -> None:
        """Initialize the seed manager with a global root seed."""
        self.seed = seed

    def get_subseed_generator(self) -> Generator[int]:
        """Creates a stream of sub-seeds.

        Useful for seeding multiple parallel workloads, metrics generators,
        or telemetry streams without losing reproducibility.
        """
        rng = random.Random(self.seed)
        while True:
            yield rng.randint(0, 2**31 - 1)
