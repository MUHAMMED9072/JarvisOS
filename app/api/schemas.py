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


# ==========================================================================
# Skills
# ==========================================================================


class SkillInfo(BaseModel):
    name: str = Field(..., description="Skill name")
    intent: str = Field(..., description="Skill intent identifier")
    description: str = Field("", description="Skill description")
    version: str = Field("1.0.0", description="Skill version")
    author: str = Field("JarvisOS", description="Skill author")
    enabled: bool = Field(True, description="Whether the skill is enabled")
    category: str = Field("", description="Skill category derived from module path")


class SkillListResponse(BaseModel):
    skills: list[SkillInfo]


class SkillExecuteRequest(BaseModel):
    text: str = Field(..., description="Input text for the skill")
    brain: str | None = Field(None, description="Brain type (fast/smart/deep)")
    source: str = Field("api", description="Source identifier")


class SkillExecuteResponse(BaseModel):
    success: bool = Field(..., description="Whether execution succeeded")
    message: str = Field("", description="Result message")
    data: dict[str, Any] = Field(default_factory=dict, description="Structured result data")
    execution_time: float = Field(0.0, description="Execution time in seconds")
    skill: str = Field("", description="Name of the skill that executed")


class SkillIntentInfo(BaseModel):
    name: str = Field(..., description="Skill name")
    intent: str = Field(..., description="Intent identifier")
    description: str = Field("", description="Skill description")


class SkillIntentListResponse(BaseModel):
    intents: list[SkillIntentInfo]


class SkillCategoryInfo(BaseModel):
    name: str = Field(..., description="Category name")
    count: int = Field(0, description="Number of skills in this category")


class SkillCategoryListResponse(BaseModel):
    categories: list[SkillCategoryInfo]


class SkillReloadRequest(BaseModel):
    intent: str | None = Field(None, description="Intent to reload (omit or use all for full reload)")
    all: bool = Field(False, description="Reload all skills")


class SkillReloadResponse(BaseModel):
    status: str = Field(..., description="Reload status")
    message: str = Field("", description="Status message")
    intents: list[str] = Field(default_factory=list, description="Intents reloaded")


class SkillDiscoverResponse(BaseModel):
    status: str = Field(..., description="Discovery status")
    count: int = Field(0, description="Number of skills discovered")
    skills: list[str] = Field(default_factory=list, description="Discovered skill intents")


# ==========================================================================
# Plugins (P11-04)
# ==========================================================================


class PluginInfo(BaseModel):
    name: str = Field(..., description="Plugin name")
    version: str = Field("", description="Plugin version")
    enabled: bool = Field(False, description="Whether the plugin is enabled")
    description: str = Field("", description="Plugin description")
    author: str = Field("", description="Plugin author")
    min_core_version: str = Field("", description="Minimum core version required")
    capabilities: list[str] = Field(default_factory=list, description="Plugin capabilities")
    permissions: list[str] = Field(default_factory=list, description="Plugin permissions")
    services: list[str] = Field(default_factory=list, description="Services registered by this plugin")
    errors: list[str] = Field(default_factory=list, description="Plugin errors")


class PluginListResponse(BaseModel):
    plugins: list[PluginInfo]


class PluginNameRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Plugin name")


class PluginActionResponse(BaseModel):
    status: str = Field(..., description="Action status")
    message: str = Field(..., description="Status message")
    name: str = Field(..., description="Plugin name")


class PluginDiscoverResponse(BaseModel):
    status: str = Field(..., description="Discovery status")
    count: int = Field(0, description="Number of plugins loaded")
    plugins: list[str] = Field(default_factory=list, description="Loaded plugin names")


class PluginServiceInfo(BaseModel):
    plugin: str = Field(..., description="Plugin name")
    services: list[str] = Field(..., description="Service names")


class PluginServiceListResponse(BaseModel):
    services: list[PluginServiceInfo]


class PluginPermissionInfo(BaseModel):
    name: str = Field(..., description="Permission name")
    description: str = Field("", description="Permission description")


class PluginPermissionListResponse(BaseModel):
    permissions: list[PluginPermissionInfo]


class PluginPackageInfo(BaseModel):
    name: str = Field(..., description="Package name")
    version: str = Field(..., description="Package version")
    installed_at: str = Field("", description="Installation timestamp")
    package_hash: str = Field("", description="Package SHA-256 hash")


class PluginPackageListResponse(BaseModel):
    packages: list[PluginPackageInfo]


# ==========================================================================
# Voice (P11-05)
# ==========================================================================


class VoiceTranscribeResponse(BaseModel):
    text: str = Field(..., description="Transcribed text")
    confidence: float = Field(0.0, description="Transcription confidence (0.0–1.0)")
    language: str = Field("en", description="Detected language")
    duration_ms: float = Field(0.0, description="Audio duration in milliseconds")


class VoiceProcessRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to process through the voice pipeline")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Transcription confidence")
    session_id: str = Field("", description="Session identifier for conversation reuse")
    session_metadata: dict[str, Any] | None = Field(None, description="Additional session metadata")


class VoiceProcessResponse(BaseModel):
    success: bool = Field(..., description="Whether processing succeeded")
    response: str = Field(..., description="Response text")
    provider: str = Field("", description="AI provider used")
    model: str = Field("", description="AI model used")
    conversation_id: str = Field("", description="Conversation ID for follow-up")
    routing_strategy: str = Field("", description="Routing strategy used")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Response metadata")


class VoiceListenActionResponse(BaseModel):
    status: str = Field(..., description="Action status (ok/error)")
    message: str = Field(..., description="Status message")


class VoiceStatusResponse(BaseModel):
    running: bool = Field(..., description="Whether the voice subsystem is running")
    enabled: bool = Field(..., description="Whether voice is enabled in config")
    speaker_enabled: bool = Field(False, description="Whether speaker (TTS) is enabled")
    wake_word_enabled: bool = Field(False, description="Whether wake word detection is enabled")
    vad_enabled: bool = Field(False, description="Whether VAD is enabled")
    whisper_model: str = Field("base", description="Whisper model name")
    language: str = Field("en", description="Voice language")
    sample_rate: int = Field(16000, description="Audio sample rate")
    record_seconds: int = Field(5, description="Fixed recording duration in seconds")


class VoiceProviderInfo(BaseModel):
    name: str = Field(..., description="Provider name")
    type: str = Field(..., description="Provider type (whisper/speaker/listener)")
    available: bool = Field(False, description="Whether the provider is available")
    description: str = Field("", description="Provider description")
    config: dict[str, Any] = Field(default_factory=dict, description="Provider configuration")


class VoiceProviderListResponse(BaseModel):
    providers: list[VoiceProviderInfo]
