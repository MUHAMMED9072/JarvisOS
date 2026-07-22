from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.registry import ServiceRegistry
from app.cortex.handlers import BaseHandler
from app.cortex.handlers.ai_handler import AIHandler
from app.cortex.handlers.automation_handler import AutomationHandler
from app.cortex.handlers.developer_handler import DeveloperHandler
from app.cortex.handlers.memory_handler import MemoryHandler


class TestBaseHandler:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseHandler()

    def test_concrete_handlers_are_subclasses(self):
        registry = MagicMock()
        assert isinstance(AIHandler(registry), BaseHandler)
        assert isinstance(MemoryHandler(registry), BaseHandler)
        assert isinstance(AutomationHandler(registry), BaseHandler)
        assert isinstance(DeveloperHandler(registry), BaseHandler)


class TestAIHandler:
    @pytest.fixture
    def handler(self):
        registry = MagicMock()
        ai_router = MagicMock()
        ai_router.ask.return_value = "AI response"
        registry.get.return_value = ai_router
        return AIHandler(registry)

    def test_chat_returns_response(self, handler):
        response = handler.chat("hello")
        assert response == "AI response"
        handler.registry.get.assert_called_with("ai_router")

    def test_chat_passes_provider(self, handler):
        response = handler.chat("hello", provider="ollama")
        assert response == "AI response"

    def test_plan_returns_plan(self, handler):
        response = handler.plan("build a calculator")
        assert response == "AI response"

    def test_summarize_returns_summary(self, handler):
        response = handler.summarize("long text here")
        assert response == "AI response"


class TestMemoryHandler:
    @pytest.fixture
    def handler(self):
        registry = MagicMock()
        memory = MagicMock()
        memory.search.return_value = ["result1", "result2"]
        memory.get_recent.return_value = [{"role": "user", "content": "hello"}]
        memory.get_session_messages.return_value = [{"role": "user", "content": "hello"}]
        registry.get.return_value = memory
        return MemoryHandler(registry)

    def test_recall_returns_results(self, handler):
        response = handler.recall("what did I do")
        assert "result" in response

    def test_recall_no_results(self, handler):
        handler.registry.get.return_value.search.return_value = []
        response = handler.recall("unknown")
        assert "No relevant memories found" in response

    def test_get_recent_returns_list(self, handler):
        recent = handler.get_recent(5)
        assert isinstance(recent, list)
        assert recent[0]["role"] == "user"

    def test_get_session_context_returns_dict(self, handler):
        context = handler.get_session_context()
        assert "messages" in context


class TestAutomationHandler:
    @pytest.fixture
    def handler(self):
        registry = MagicMock()
        return AutomationHandler(registry)

    @patch("app.cortex.handlers.automation_handler.Config")
    def test_open_known_application(self, mock_config, handler):
        mock_config.APPLICATIONS = {"notepad": "notepad.exe"}
        result = handler.open_application("notepad")
        assert "Opening" in result
        assert "notepad" in result

    @patch("app.cortex.handlers.automation_handler.Config")
    def test_open_unknown_application(self, mock_config, handler):
        mock_config.APPLICATIONS = {}
        result = handler.open_application("unknown_app")
        assert "not a supported application" in result

    @patch("subprocess.run")
    def test_close_application(self, mock_run, handler):
        mock_run.return_value = MagicMock()
        result = handler.close_application("notepad")
        assert "Closing" in result

    def test_search_web(self, handler):
        result = handler.search_web("python tutorial")
        assert "Searching for" in result
        assert "python tutorial" in result


class TestDeveloperHandler:
    @pytest.fixture
    def handler(self):
        registry = MagicMock()
        return DeveloperHandler(registry)

    def test_generate_code_uses_generator(self, handler):
        generator = MagicMock()
        generator.generate_task.return_value = "data/generated_patch.py"
        handler.registry.get.return_value = generator
        result = handler.generate_code("create a calculator")
        assert result is not None

    def test_generate_code_fallback(self, handler):
        handler.registry.get.side_effect = KeyError("generator")
        result = handler.generate_code("create a calculator")
        assert result.success is False

    def test_analyze_code(self, handler):
        analyzer = MagicMock()
        analyzer.analyze.return_value = MagicMock(success=True, message="analysis done")
        handler.registry.get.return_value = analyzer
        result = handler.analyze_code("/path/to/file.py")
        assert result.success is True

    def test_run_tests(self, handler):
        tester = MagicMock()
        tester.run.return_value = MagicMock(success=True, message="tests passed")
        handler.registry.get.return_value = tester
        result = handler.run_tests("/path/to/tests")
        assert result.success is True

    def test_analyze_code_fallback(self, handler):
        handler.registry.get.side_effect = KeyError("analyzer")
        result = handler.analyze_code("/path/to/file.py")
        assert result.success is False

    def test_run_tests_fallback(self, handler):
        handler.registry.get.side_effect = KeyError("tester")
        result = handler.run_tests("/path/to/tests")
        assert result.success is False
