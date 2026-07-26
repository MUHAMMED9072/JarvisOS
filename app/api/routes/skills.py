from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import require_service
from app.api.errors import BadRequestError, NotFoundError
from app.api.schemas import (
    SkillCategoryInfo,
    SkillCategoryListResponse,
    SkillDiscoverResponse,
    SkillExecuteRequest,
    SkillExecuteResponse,
    SkillInfo,
    SkillIntentInfo,
    SkillIntentListResponse,
    SkillListResponse,
    SkillReloadRequest,
    SkillReloadResponse,
)
from app.cortex.models import CortexRequest
from app.core.registry import ServiceRegistry
from app.skills.base import Skill
from app.skills.manager import SkillManager

router = APIRouter(prefix="/api/v1/skills", tags=["Skills"])

SKILL_MGR = Depends(require_service("skill_manager"))


def _derive_category(skill: Skill) -> str:
    parts = skill.__module__.split(".")
    if len(parts) >= 3 and parts[:2] == ["app", "skills"]:
        return parts[2]
    return ""


def _skill_to_info(skill: Skill) -> SkillInfo:
    return SkillInfo(
        name=skill.name,
        intent=skill.intent,
        description=skill.description or "",
        version=skill.version or "1.0.0",
        author=skill.author or "JarvisOS",
        enabled=True,
        category=_derive_category(skill),
    )


def _find_skill(mgr: SkillManager, name: str) -> Skill | None:
    name_lower = name.lower()
    for s in mgr.all_skills():
        if s.intent.lower() == name_lower or s.name.lower() == name_lower:
            return s
    return None


# ------------------------------------------------------------------
# List all skills
# ------------------------------------------------------------------


@router.get("", response_model=SkillListResponse)
async def list_skills(
    mgr: SkillManager = SKILL_MGR,
) -> SkillListResponse:
    skills = sorted(
        (_skill_to_info(s) for s in mgr.all_skills()),
        key=lambda s: s.name.lower(),
    )
    return SkillListResponse(skills=skills)


# ------------------------------------------------------------------
# Reload skills
# ------------------------------------------------------------------


@router.post("/reload", response_model=SkillReloadResponse)
async def reload_skills(
    body: SkillReloadRequest,
    request: Request,
    mgr: SkillManager = SKILL_MGR,
) -> SkillReloadResponse:
    from app.skills.loader import SkillLoader

    registry: ServiceRegistry | None = getattr(request.app.state, "registry", None)
    loader = SkillLoader()

    if body.all:
        old_intents = list(mgr.skills.keys())
        for intent in old_intents:
            mgr.unregister(intent)
        loader.load(mgr, registry)
        new_intents = list(mgr.skills.keys())
        return SkillReloadResponse(
            status="ok",
            message=f"Reloaded {len(new_intents)} skills",
            intents=new_intents,
        )

    if not body.intent:
        raise BadRequestError("Provide 'intent' or set 'all' to true")

    reloaded = loader.reload(body.intent, mgr, registry)
    if not reloaded:
        raise NotFoundError(f"No skill found for intent {body.intent!r}")

    return SkillReloadResponse(
        status="ok",
        message=f"Reloaded skill with intent {body.intent!r}",
        intents=reloaded,
    )


# ------------------------------------------------------------------
# Discover skills from filesystem
# ------------------------------------------------------------------


@router.post("/discover", response_model=SkillDiscoverResponse)
async def discover_skills(
    request: Request,
    mgr: SkillManager = SKILL_MGR,
) -> SkillDiscoverResponse:
    from app.skills.loader import SkillLoader

    registry: ServiceRegistry | None = getattr(request.app.state, "registry", None)
    loader = SkillLoader()
    before = set(mgr.skills.keys())
    loader.load(mgr, registry)
    after = set(mgr.skills.keys())
    new_intents = sorted(after - before)
    return SkillDiscoverResponse(
        status="ok",
        count=len(new_intents),
        skills=sorted(after),
    )


# ------------------------------------------------------------------
# List categories
# ------------------------------------------------------------------


@router.get("/categories", response_model=SkillCategoryListResponse)
async def list_categories(
    mgr: SkillManager = SKILL_MGR,
) -> SkillCategoryListResponse:
    category_counts: dict[str, int] = {}
    for s in mgr.all_skills():
        cat = _derive_category(s)
        if cat:
            category_counts[cat] = category_counts.get(cat, 0) + 1
    categories = sorted(
        (SkillCategoryInfo(name=cat, count=count) for cat, count in category_counts.items()),
        key=lambda c: c.name,
    )
    return SkillCategoryListResponse(categories=categories)


# ------------------------------------------------------------------
# List intents
# ------------------------------------------------------------------


@router.get("/intents", response_model=SkillIntentListResponse)
async def list_intents(
    mgr: SkillManager = SKILL_MGR,
) -> SkillIntentListResponse:
    intents = sorted(
        (
            SkillIntentInfo(
                name=s.name,
                intent=s.intent,
                description=s.description or "",
            )
            for s in mgr.all_skills()
        ),
        key=lambda i: i.intent,
    )
    return SkillIntentListResponse(intents=intents)


# ------------------------------------------------------------------
# Get a single skill (must be last to avoid path conflicts)
# ------------------------------------------------------------------


@router.get("/{name}", response_model=SkillInfo)
async def get_skill(
    name: str,
    mgr: SkillManager = SKILL_MGR,
) -> SkillInfo:
    skill = _find_skill(mgr, name)
    if skill is None:
        raise NotFoundError(f"Skill {name!r} not found")
    return _skill_to_info(skill)


# ------------------------------------------------------------------
# Execute a skill by name (must be last to avoid path conflicts)
# ------------------------------------------------------------------


@router.post("/{name}/execute", response_model=SkillExecuteResponse)
async def execute_skill(
    name: str,
    body: SkillExecuteRequest,
    mgr: SkillManager = SKILL_MGR,
) -> SkillExecuteResponse:
    skill = _find_skill(mgr, name)
    if skill is None:
        raise NotFoundError(f"Skill {name!r} not found")

    request = CortexRequest(
        text=body.text,
        intent=skill.intent,
        source=body.source,
        brain=body.brain or "",
    )
    result = skill.execute(request)
    return SkillExecuteResponse(
        success=result.success,
        message=result.message,
        data=dict(result.data),
        execution_time=result.execution_time,
        skill=result.skill,
    )
