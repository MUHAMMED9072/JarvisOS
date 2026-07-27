from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.dependencies import get_registry
from app.api.errors import BadRequestError, ServiceUnavailableError
from app.api.schemas import (
    EvolutionAutofixRequest,
    EvolutionAutofixResponse,
    EvolutionGenerateRequest,
    EvolutionGenerateResponse,
    EvolutionHistoryResponse,
    EvolutionPlanRequest,
    EvolutionPlanResponse,
    EvolutionSandboxRequest,
    EvolutionSandboxResponse,
    EvolutionScanRequest,
    EvolutionScanResponse,
    EvolutionStatusResponse,
    EvolutionUpgradeResponse,
    EvolutionValidateRequest,
    EvolutionValidateResponse,
)
from app.evolution.analyzer import Analyzer
from app.evolution.autofix import AutoFixer
from app.evolution.generator import CodeGenerator
from app.evolution.planner import EvolutionPlanner
from app.evolution.sandbox import Sandbox
from app.evolution.scanner import ProjectScanner
from app.evolution.updater import Updater
from app.evolution.validator import PatchValidator
from app.evolution.version import VersionManager

router = APIRouter(prefix="/api/v1/evolution", tags=["Evolution"])


# ------------------------------------------------------------------
# Project status
# ------------------------------------------------------------------


@router.get("/status", response_model=EvolutionStatusResponse)
async def evolution_status() -> EvolutionStatusResponse:
    analysis = Analyzer().analyze()
    version_info = VersionManager().info()
    return EvolutionStatusResponse(
        version=version_info.get("version", "0.0.0"),
        files=analysis.files,
        lines=analysis.lines,
        hash=analysis.sha256,
    )


# ------------------------------------------------------------------
# Scan the project
# ------------------------------------------------------------------


@router.post("/scan", response_model=EvolutionScanResponse)
async def evolution_scan(body: EvolutionScanRequest) -> EvolutionScanResponse:
    report = ProjectScanner().scan(root=body.root)
    summary = report.get("summary", {})
    return EvolutionScanResponse(
        status="ok",
        python_files=summary.get("files", 0),
        classes=summary.get("classes", 0),
        functions=summary.get("functions", 0),
        imports=summary.get("imports", 0),
        summary=summary,
    )


# ------------------------------------------------------------------
# Create an evolution plan
# ------------------------------------------------------------------


@router.post("/plan", response_model=EvolutionPlanResponse)
async def evolution_plan(
    body: EvolutionPlanRequest,
    request: Request,
) -> EvolutionPlanResponse:
    registry = get_registry(request)
    if registry is None:
        raise ServiceUnavailableError("Service registry not available")
    planner = EvolutionPlanner(registry)
    plan_text = planner.create_plan()
    return EvolutionPlanResponse(
        status="ok",
        plan=plan_text,
        plan_path="data/improvement_plan.md",
    )


# ------------------------------------------------------------------
# Generate code for a task
# ------------------------------------------------------------------


@router.post("/generate", response_model=EvolutionGenerateResponse)
async def evolution_generate(
    body: EvolutionGenerateRequest,
    request: Request,
) -> EvolutionGenerateResponse:
    registry = get_registry(request)
    if registry is None:
        raise ServiceUnavailableError("Service registry not available")
    generator = CodeGenerator(registry)
    output = generator.generate_task(task=body.task, target_file=body.target_file)
    return EvolutionGenerateResponse(status="ok", output_path=output)


# ------------------------------------------------------------------
# Auto-fix a patch
# ------------------------------------------------------------------


@router.post("/autofix", response_model=EvolutionAutofixResponse)
async def evolution_autofix(
    body: EvolutionAutofixRequest,
    request: Request,
) -> EvolutionAutofixResponse:
    registry = get_registry(request)
    if registry is None:
        raise ServiceUnavailableError("Service registry not available")
    fixer = AutoFixer(registry)
    result = fixer.fix(review_file=body.review_file, patch_file=body.patch_file)
    return EvolutionAutofixResponse(status="ok", patch_file=result)


# ------------------------------------------------------------------
# Validate a patch
# ------------------------------------------------------------------


@router.post("/validate", response_model=EvolutionValidateResponse)
async def evolution_validate(
    body: EvolutionValidateRequest,
) -> EvolutionValidateResponse:
    validator = PatchValidator()
    ok, report = validator.validate(patch_path=body.patch_path)
    return EvolutionValidateResponse(valid=ok, report=report)


# ------------------------------------------------------------------
# Execute code in the sandbox
# ------------------------------------------------------------------


@router.post("/sandbox", response_model=EvolutionSandboxResponse)
async def evolution_sandbox(
    body: EvolutionSandboxRequest,
) -> EvolutionSandboxResponse:
    sandbox = Sandbox()
    result = sandbox.run(source=body.source)
    return EvolutionSandboxResponse(
        success=result.success,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        execution_time=result.execution_time,
        timed_out=result.timed_out,
        security_violations=result.security_violations,
    )


# ------------------------------------------------------------------
# Trigger upgrade pipeline
# ------------------------------------------------------------------


@router.post("/upgrade", response_model=EvolutionUpgradeResponse)
async def evolution_upgrade() -> EvolutionUpgradeResponse:
    updater = Updater()
    report = updater.upgrade_requested()
    return EvolutionUpgradeResponse(success=report.success, message=report.message)


# ------------------------------------------------------------------
# Evolution history
# ------------------------------------------------------------------


@router.get("/history", response_model=EvolutionHistoryResponse)
async def evolution_history() -> EvolutionHistoryResponse:
    version_info = VersionManager().info()
    return EvolutionHistoryResponse(
        history=[
            {
                "timestamp": version_info.get("updated", ""),
                "action": "version_info",
                "details": version_info,
            },
        ],
    )
