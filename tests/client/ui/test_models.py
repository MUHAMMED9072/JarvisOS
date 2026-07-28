"""Tests for client UI view models."""

from __future__ import annotations

from app.client.ui.models import (
    ChatMessage,
    ConversationEntry,
    HealthEvent,
    MetricSample,
    PluginDescriptor,
    ServerStatus,
    SettingsGroup,
    SkillDescriptor,
)


class TestChatMessage:
    def test_default_construction(self):
        msg = ChatMessage(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"
        assert msg.timestamp == 0.0

    def test_streaming_default(self):
        msg = ChatMessage()
        assert msg.streaming is False

    def test_message_id_default(self):
        msg = ChatMessage()
        assert msg.message_id == ""


class TestMetricSample:
    def test_default_construction(self):
        sample = MetricSample(cpu_percent=42.5, memory_percent=65.0)
        assert sample.cpu_percent == 42.5
        assert sample.memory_percent == 65.0

    def test_default_values(self):
        sample = MetricSample()
        assert sample.cpu_percent == 0.0
        assert sample.memory_used_gb == 0.0


class TestServerStatus:
    def test_default_construction(self):
        status = ServerStatus(connected=True, uptime=3600, version="1.0.0")
        assert status.connected is True
        assert status.uptime == 3600
        assert status.version == "1.0.0"

    def test_optional_fields_default(self):
        status = ServerStatus()
        assert status.app_name == ""
        assert status.skills_count == 0
        assert status.plugins_count == 0


class TestSkillDescriptor:
    def test_default_construction(self):
        skill = SkillDescriptor(name="test", description="A skill", intent="test.intent")
        assert skill.name == "test"
        assert skill.description == "A skill"
        assert skill.intent == "test.intent"

    def test_optional_fields_default(self):
        skill = SkillDescriptor()
        assert skill.version == ""
        assert skill.author == ""


class TestPluginDescriptor:
    def test_default_construction(self):
        plugin = PluginDescriptor(name="test", description="A plugin", version="1.0.0")
        assert plugin.name == "test"
        assert plugin.description == "A plugin"
        assert plugin.version == "1.0.0"

    def test_enabled_default(self):
        plugin = PluginDescriptor(name="test", version="", description="")
        assert plugin.enabled is False

    def test_enabled_true(self):
        plugin = PluginDescriptor(name="test", description="", version="", enabled=True)
        assert plugin.enabled is True


class TestConversationEntry:
    def test_default_construction(self):
        entry = ConversationEntry(conversation_id="1", title="hello", message_count=5)
        assert entry.conversation_id == "1"
        assert entry.title == "hello"
        assert entry.message_count == 5

    def test_created_updated_default(self):
        entry = ConversationEntry()
        assert entry.created == 0.0
        assert entry.updated == 0.0


class TestSettingsGroup:
    def test_default_construction(self):
        group = SettingsGroup(name="General", settings={})
        assert group.name == "General"
        assert group.settings == {}

    def test_with_settings(self):
        group = SettingsGroup(name="Connection", settings={"host": "localhost", "port": 8080})
        assert group.settings["host"] == "localhost"
        assert group.settings["port"] == 8080


class TestHealthEvent:
    def test_default_construction(self):
        event = HealthEvent(status="healthy", message="All systems operational")
        assert event.status == "healthy"
        assert event.message == "All systems operational"

    def test_default_status(self):
        event = HealthEvent()
        assert event.status == "healthy"
        assert event.timestamp == 0.0
