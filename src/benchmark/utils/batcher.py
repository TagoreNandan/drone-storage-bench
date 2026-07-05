from collections.abc import Iterator
from typing import TypeVar

T = TypeVar("T")


def batch_generator[T](iterable: Iterator[T], batch_size: int) -> Iterator[list[T]]:
    """Yields batches of a configurable size from the given iterable.

    Accumulates elements in memory up to `batch_size`, then yields the list.
    When the source iterable is exhausted, yields any remaining elements as
    a final partial batch.

    Args:
        iterable: An iterator yielding telemetry records or other data points.
        batch_size: Configured maximum size of each batch. Must be >= 1.

    Yields:
        Lists containing up to batch_size elements.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    batch: list[T] = []
    for item in iterable:
        batch.append(item)
        if len(batch) == batch_size:
            yield batch
            batch = []

    if batch:
        yield batch
