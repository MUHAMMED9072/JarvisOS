from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., description="Overall health status")
    version: str = Field(..., description="JARVIS OS version")
    uptime: str = Field("", description="Uptime string")
    services_healthy: int = Field(0, description="Number of healthy services")


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = Field(None, description="Additional error context")


class ErrorResponse(BaseModel):
    error: ErrorDetail


class StatusResponse(BaseModel):
    status: str = Field(..., description="Running or stopped")
    version: str = Field(..., description="JARVIS OS version")
    plugins: int = Field(0, description="Number of loaded plugins")
    skills: int = Field(0, description="Number of loaded skills")
    services: int = Field(0, description="Number of registered services")
    memory: str = Field("", description="Memory status")
    voice: str = Field("", description="Voice subsystem status")


class ConfigResponse(BaseModel):
    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    data_dir: str = Field("", description="Data directory path")
    plugin_dir: str = Field("", description="Plugin directory path")
    log_level: str = Field("", description="Logging level")
    default_brain: str = Field("", description="Default brain type")
    voice_enabled: bool = Field(False, description="Whether voice is enabled")
    wake_word: str = Field("", description="Wake word")


class ServiceInfo(BaseModel):
    name: str = Field(..., description="Registered service name")
    available: bool = Field(..., description="Whether the service is available")


class ServiceListResponse(BaseModel):
    services: list[ServiceInfo]


class ValidationErrorItem(BaseModel):
    field: str = Field(..., description="Field name")
    message: str = Field(..., description="Validation error message")


class ValidationErrorResponse(BaseModel):
    error: ErrorDetail
    details: list[ValidationErrorItem] = Field(
        default_factory=list, description="Per-field validation errors",
    )
