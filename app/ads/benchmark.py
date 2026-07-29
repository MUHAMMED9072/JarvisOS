from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.ads.sandbox import AdsSandbox, ExecutionResult


@dataclass
class BenchmarkReport:
    """Benchmark results comparing artifact performance against baseline."""

    artifact_name: str = ""
    baseline_latency_ms: float = 0.0
    measured_latency_ms: float = 0.0
    latency_change_pct: float = 0.0
    baseline_throughput: float = 0.0
    measured_throughput: float = 0.0
    throughput_change_pct: float = 0.0
    baseline_ram_mb: float = 0.0
    measured_ram_mb: float = 0.0
    ram_change_pct: float = 0.0
    passed: bool = True
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "baseline_latency_ms": self.baseline_latency_ms,
            "measured_latency_ms": self.measured_latency_ms,
            "latency_change_pct": self.latency_change_pct,
            "baseline_throughput": self.baseline_throughput,
            "measured_throughput": self.measured_throughput,
            "throughput_change_pct": self.throughput_change_pct,
            "baseline_ram_mb": self.baseline_ram_mb,
            "measured_ram_mb": self.measured_ram_mb,
            "ram_change_pct": self.ram_change_pct,
            "passed": self.passed,
            "details": self.details,
        }


class BenchmarkRunner:
    """Measure artifact performance against baseline."""

    def __init__(self, sandbox: AdsSandbox | None = None) -> None:
        self._sandbox = sandbox or AdsSandbox(timeout=60.0)

    def benchmark(
        self,
        source: str,
        artifact_name: str = "artifact",
        iterations: int = 5,
    ) -> BenchmarkReport:
        latencies: list[float] = []
        for _ in range(iterations):
            start = time.time()
            result = self._sandbox.run_code(source)
            elapsed = (time.time() - start) * 1000  # ms
            latencies.append(elapsed)

        avg_latency_ms = sum(latencies) / len(latencies)
        throughput = 1000.0 / avg_latency_ms if avg_latency_ms > 0 else 0.0
        ram_mb = result.peak_ram_bytes / (1024 * 1024) if result else 0.0

        # Compare against a nominal baseline (simple print is ~1ms)
        baseline_latency = 1.0
        baseline_throughput = 1000.0
        baseline_ram = 1.0

        return BenchmarkReport(
            artifact_name=artifact_name,
            baseline_latency_ms=baseline_latency,
            measured_latency_ms=round(avg_latency_ms, 2),
            latency_change_pct=round(
                ((avg_latency_ms - baseline_latency) / baseline_latency) * 100, 1
            ),
            baseline_throughput=baseline_throughput,
            measured_throughput=round(throughput, 2),
            throughput_change_pct=round(
                ((throughput - baseline_throughput) / baseline_throughput) * 100, 1
            ),
            baseline_ram_mb=baseline_ram,
            measured_ram_mb=round(ram_mb, 2),
            ram_change_pct=round(((ram_mb - baseline_ram) / baseline_ram) * 100, 1) if baseline_ram > 0 else 0.0,
            passed=True,
            details=f"Benchmark completed: {iterations} iterations",
        )

    def health(self) -> dict[str, Any]:
        return {"alive": True}
