"""
Sorting Algorithm Solution - Merge Sort.

A stable divide-and-conquer approach using merging.
"""


def sort(arr: list[int]) -> list[int]:
    """
    Sort a list of integers in ascending order using merge sort.

    Args:
        arr: List of integers to sort

    Returns:
        New sorted list (do not modify input)
    """
    if len(arr) <= 1:
        return arr.copy()

    return _merge_sort(arr.copy())


def _merge_sort(arr: list[int]) -> list[int]:
    """Recursive merge sort."""
    if len(arr) <= 1:
        return arr

    mid = len(arr) // 2
    left = _merge_sort(arr[:mid])
    right = _merge_sort(arr[mid:])

    return _merge(left, right)


def _merge(left: list[int], right: list[int]) -> list[int]:
    """Merge two sorted lists."""
    result = []
    i = j = 0

    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1

    result.extend(left[i:])
    result.extend(right[j:])
    return result
