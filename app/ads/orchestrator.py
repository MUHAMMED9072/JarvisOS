from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.ads.pipeline import Pipeline, PipelineReport, StageStatus


@dataclass
class PipelineJob:
    job_id: str = ""
    request: str = ""
    status: str = "pending"
    progress: float = 0.0
    current_stage: str = ""
    report: PipelineReport | None = None
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "request": self.request,
            "status": self.status,
            "progress": self.progress,
            "current_stage": self.current_stage,
            "report": self.report.to_dict() if self.report else None,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class Orchestrator:
    """Monitor pipeline jobs, track progress, detect stalls, and report failures."""

    STAGE_ORDER = [
        "requirements", "capability_analysis", "gap_detection", "architecture",
        "content_generation", "test_generation", "sandbox", "security_review",
        "performance_review", "benchmark", "governance", "installation",
        "registration", "versioning", "metrics",
    ]

    STALL_TIMEOUT_SECONDS: float = 300.0

    def __init__(self, pipeline: Pipeline | None = None) -> None:
        self._pipeline = pipeline or Pipeline()
        self._lock = threading.RLock()
        self._jobs: dict[str, PipelineJob] = {}
        self._counter: int = 0

    def submit(self, request: str) -> str:
        with self._lock:
            self._counter += 1
            job_id = f"job_{int(time.time())}_{self._counter}"
            job = PipelineJob(job_id=job_id, request=request)
            self._jobs[job_id] = job
        return job_id

    def run_job(self, job_id: str) -> PipelineReport | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.status = "running"
            job.started_at = time.time()

        report = self._pipeline.run(job.request)

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.report = report
            job.completed_at = time.time()

            if report.success:
                job.status = "completed"
                job.progress = 1.0
            else:
                job.status = "failed"
                job.error = report.error
                # Calculate progress based on stages
                passed = sum(1 for s in report.stages if s.status == StageStatus.PASSED)
                total = len(report.stages)
                job.progress = passed / max(total, 1)

            # Set current stage from last stage run
            if report.stages:
                last = report.stages[-1]
                job.current_stage = last.stage_name

        return report

    def get_job(self, job_id: str) -> PipelineJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(
        self, status: str | None = None, limit: int = 50,
    ) -> list[PipelineJob]:
        with self._lock:
            jobs = list(self._jobs.values())
            if status:
                jobs = [j for j in jobs if j.status == status]
            jobs.sort(key=lambda j: j.created_at, reverse=True)
            return jobs[:limit]

    def get_progress(self, job_id: str) -> float:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return 0.0
            return job.progress

    def detect_stalled(self) -> list[PipelineJob]:
        now = time.time()
        stalled: list[PipelineJob] = []
        with self._lock:
            for job in self._jobs.values():
                if job.status == "running":
                    elapsed = now - job.started_at
                    if elapsed > self.STALL_TIMEOUT_SECONDS:
                        stalled.append(job)
        return stalled

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status not in ("pending", "running"):
                return False
            job.status = "cancelled"
            job.completed_at = time.time()
            return True

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._jobs)
            completed = sum(1 for j in self._jobs.values() if j.status == "completed")
            failed = sum(1 for j in self._jobs.values() if j.status == "failed")
            running = sum(1 for j in self._jobs.values() if j.status == "running")
            pending = sum(1 for j in self._jobs.values() if j.status == "pending")
            cancelled = sum(1 for j in self._jobs.values() if j.status == "cancelled")
            return {
                "total_jobs": total,
                "completed": completed,
                "failed": failed,
                "running": running,
                "pending": pending,
                "cancelled": cancelled,
                "stalled_count": len(self.detect_stalled()),
            }

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "total_jobs": len(self._jobs),
        }
