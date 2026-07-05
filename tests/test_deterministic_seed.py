from benchmark.core.seed import DeterministicSeedManager


def test_deterministic_seed_generator_equality() -> None:
    """Verifies that two seed managers with the same seed generate identical sub-seeds."""
    manager_a = DeterministicSeedManager(seed=100)
    manager_b = DeterministicSeedManager(seed=100)

    gen_a = manager_a.get_subseed_generator()
    gen_b = manager_b.get_subseed_generator()

    seeds_a = [next(gen_a) for _ in range(5)]
    seeds_b = [next(gen_b) for _ in range(5)]

    assert seeds_a == seeds_b


def test_deterministic_seed_generator_inequality() -> None:
    """Verifies that different seeds yield different sub-seed streams."""
    manager_a = DeterministicSeedManager(seed=100)
    manager_b = DeterministicSeedManager(seed=200)

    gen_a = manager_a.get_subseed_generator()
    gen_b = manager_b.get_subseed_generator()

    seeds_a = [next(gen_a) for _ in range(5)]
    seeds_b = [next(gen_b) for _ in range(5)]

    assert seeds_a != seeds_b
