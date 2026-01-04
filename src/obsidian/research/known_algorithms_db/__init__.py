"""
Known Algorithm Database.

Contains definitions of known algorithms for various problem domains.
"""

from obsidian.research.known_algorithms import KnownAlgorithm

# Registry of all known algorithms by name
_ALGORITHM_REGISTRY: dict[str, KnownAlgorithm] = {}


def register_algorithm(algorithm: KnownAlgorithm) -> None:
    """Register an algorithm in the global registry."""
    _ALGORITHM_REGISTRY[algorithm.name.lower()] = algorithm


def get_algorithm(name: str) -> KnownAlgorithm | None:
    """Get an algorithm by name."""
    return _ALGORITHM_REGISTRY.get(name.lower())


def get_all_algorithms() -> list[KnownAlgorithm]:
    """Get all registered algorithms."""
    return list(_ALGORITHM_REGISTRY.values())


def get_algorithms_for_domain(domain: str) -> list[KnownAlgorithm]:
    """Get all algorithms for a specific domain."""
    # Import domain modules to populate registry
    if domain == "matmul":
        from obsidian.research.known_algorithms_db import matmul
        return matmul.MATMUL_ALGORITHMS
    elif domain == "sorting":
        from obsidian.research.known_algorithms_db import sorting
        return sorting.SORTING_ALGORITHMS
    return []


# Auto-register algorithms on import
def _init_registry():
    """Initialize the algorithm registry."""
    try:
        from obsidian.research.known_algorithms_db import matmul
        for algo in matmul.MATMUL_ALGORITHMS:
            register_algorithm(algo)
    except ImportError:
        pass

    try:
        from obsidian.research.known_algorithms_db import sorting
        for algo in sorting.SORTING_ALGORITHMS:
            register_algorithm(algo)
    except ImportError:
        pass


_init_registry()
