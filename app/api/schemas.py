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


# ==========================================================================
# AI
# ==========================================================================


class ChatRequest(BaseModel):
    provider: str | None = Field(None, description="AI provider name")
    prompt: str = Field(..., description="User prompt")
    conversation_id: str | None = Field(None, description="Existing conversation ID")
    prompt_template: str | None = Field(None, description="Prompt template name")
    template_variables: dict[str, str] | None = Field(None, description="Template variables")


class ChatResponse(BaseModel):
    response: str = Field(..., description="AI response text")
    provider: str = Field(..., description="Provider used")
    model: str = Field(..., description="Model used")
    latency_ms: float = Field(0.0, description="Latency in milliseconds")
    conversation_id: str | None = Field(None, description="Conversation ID")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Response metadata")


class StreamChunk(BaseModel):
    content: str = Field("", description="Chunk content")
    finish_reason: str | None = Field(None, description="Stream finish reason")


class PlanRequest(BaseModel):
    objective: str = Field(..., description="Planning objective")
    provider: str | None = Field(None, description="AI provider name")
    conversation_id: str | None = Field(None, description="Existing conversation ID")
    prompt_template: str | None = Field(None, description="Prompt template name")
    template_variables: dict[str, str] | None = Field(None, description="Template variables")
    planning_prompt: str | None = Field(None, description="Custom planning prompt")


class PlanStep(BaseModel):
    step: int = Field(..., description="Step number")
    action: str = Field(..., description="Action description")
    reasoning: str = Field(..., description="Step reasoning")
    expected_outcome: str = Field("", description="Expected outcome")


class PlanResponse(BaseModel):
    steps: list[PlanStep] = Field(..., description="Plan steps")
    provider: str = Field(..., description="Provider used")
    model: str = Field(..., description="Model used")
    duration_ms: float = Field(0.0, description="Duration in milliseconds")
    valid: bool = Field(True, description="Whether the plan is valid")
    validation_errors: list[str] = Field(default_factory=list, description="Validation errors")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Response metadata")


class ReasonRequest(BaseModel):
    objective: str = Field(..., description="Reasoning objective")
    provider: str | None = Field(None, description="AI provider name")
    conversation_id: str | None = Field(None, description="Existing conversation ID")
    prompt_template: str | None = Field(None, description="Prompt template name")
    template_variables: dict[str, str] | None = Field(None, description="Template variables")
    reasoning_prompt: str | None = Field(None, description="Custom reasoning prompt")


class ReasonStep(BaseModel):
    step: int = Field(..., description="Step number")
    statement: str = Field(..., description="Reasoning statement")
    evidence: str = Field("", description="Supporting evidence")
    conclusion: str = Field("", description="Step conclusion")


class ReasonResponse(BaseModel):
    steps: list[ReasonStep] = Field(..., description="Reasoning steps")
    provider: str = Field(..., description="Provider used")
    model: str = Field(..., description="Model used")
    duration_ms: float = Field(0.0, description="Duration in milliseconds")
    valid: bool = Field(True, description="Whether the reasoning is valid")
    validation_errors: list[str] = Field(default_factory=list, description="Validation errors")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Response metadata")


class ConversationSummary(BaseModel):
    id: str = Field(..., description="Conversation ID")
    provider: str = Field("", description="Provider")
    model: str = Field("", description="Model")
    message_count: int = Field(0, description="Number of messages")
    created_at: float = Field(0.0, description="Creation timestamp")
    updated_at: float = Field(0.0, description="Last update timestamp")
    system_prompt: str = Field("", description="System prompt")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Conversation metadata")


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]


class ConversationCreateRequest(BaseModel):
    provider: str = Field("", description="AI provider name")
    model: str = Field("", description="Model name")
    system_prompt: str = Field("", description="System prompt")
    max_messages: int | None = Field(None, description="Maximum messages to retain")
    metadata: dict[str, Any] | None = Field(None, description="Conversation metadata")


class ConversationCreateResponse(BaseModel):
    id: str = Field(..., description="Created conversation ID")
    provider: str = Field("", description="Provider")
    model: str = Field("", description="Model")
    created_at: float = Field(0.0, description="Creation timestamp")


class MessageResponse(BaseModel):
    role: str = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    timestamp: float = Field(0.0, description="Message timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Message metadata")


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]


class ProviderInfo(BaseModel):
    name: str = Field(..., description="Provider name")
    model: str = Field(..., description="Default model")
    capabilities: list[str] = Field(default_factory=list, description="Provider capabilities")
    available: bool = Field(False, description="Whether the provider is available")


class ProviderListResponse(BaseModel):
    providers: list[ProviderInfo]


class ModelInfo(BaseModel):
    provider: str = Field(..., description="Provider name")
    model: str = Field(..., description="Model name")


class ModelListResponse(BaseModel):
    models: list[ModelInfo]
