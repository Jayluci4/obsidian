"""
Sorting Algorithm Solution - Quicksort variant.

A divide-and-conquer approach using pivot partitioning.
"""


def sort(arr: list[int]) -> list[int]:
    """
    Sort a list of integers in ascending order using quicksort.

    Args:
        arr: List of integers to sort

    Returns:
        New sorted list (do not modify input)
    """
    if len(arr) <= 1:
        return arr.copy()

    result = arr.copy()
    _quicksort(result, 0, len(result) - 1)
    return result


def _quicksort(arr: list[int], low: int, high: int) -> None:
    """In-place quicksort helper."""
    if low < high:
        pivot_idx = _partition(arr, low, high)
        _quicksort(arr, low, pivot_idx - 1)
        _quicksort(arr, pivot_idx + 1, high)


def _partition(arr: list[int], low: int, high: int) -> int:
    """Partition array around pivot (last element)."""
    pivot = arr[high]
    i = low - 1

    for j in range(low, high):
        if arr[j] <= pivot:
            i += 1
            arr[i], arr[j] = arr[j], arr[i]

    arr[i + 1], arr[high] = arr[high], arr[i + 1]
    return i + 1
