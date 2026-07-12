"""
JARVIS Evolution Engine - Benchmark
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Any


@dataclass
class BenchmarkResult:
    name: str
    elapsed_ms: float
    success: bool


class Benchmark:
    """Simple benchmark runner."""

    def run(self, name: str, func: Callable[..., Any], *args, **kwargs) -> BenchmarkResult:
        start = time.perf_counter()
        success = True
        try:
            func(*args, **kwargs)
        except Exception:
            success = False
        elapsed = (time.perf_counter() - start) * 1000.0
        return BenchmarkResult(name=name, elapsed_ms=elapsed, success=success)


if __name__ == "__main__":
    bench = Benchmark()

    def demo():
        sum(range(100000))

    print(bench.run("demo", demo))
