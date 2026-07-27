"""Tests for DesktopApplication."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.client.events import EventDispatcher
from app.client.state import ClientState
from app.client.ui.app import DesktopApplication
from app.client.ui.navigation import Navigator
from app.client.ui.theme import ThemeManager
from app.core.config import Config


class TestDesktopApplicationInit:
    def test_default_construction(self):
        app = DesktopApplication()
        assert app.running is False
        assert app.window is None
        assert app.client is not None
        assert app.state is not None

    def test_custom_construction(self):
        client = MagicMock()
        events = EventDispatcher()
        state = ClientState()
        theme = ThemeManager(events)
        nav = Navigator(events)
        config = Config()

        app = DesktopApplication(
            client=client,
            events=events,
            state=state,
            theme=theme,
            navigator=nav,
            config=config,
        )
        assert app.client is client
        assert app.events is events
        assert app.state is state
        assert app.theme is theme
        assert app.navigator is nav

    def test_properties(self):
        app = DesktopApplication()
        assert hasattr(app, "running")
        assert hasattr(app, "window")
        assert hasattr(app, "client")
        assert hasattr(app, "state")
        assert hasattr(app, "theme")
        assert hasattr(app, "navigator")
        assert hasattr(app, "events")


class TestDesktopApplicationLifecycle:
    def test_run_creates_window(self):
        with patch("app.client.ui.app.ctk.set_appearance_mode"):
            with patch("app.client.ui.app.MainWindow") as MockWindow:
                mock_window = MagicMock()
                MockWindow.return_value = mock_window
                # Make mainloop raise KeyboardInterrupt to exit cleanly
                mock_window.mainloop.side_effect = KeyboardInterrupt()

                config = Config()
                config.CLIENT_ANIMATIONS = True
                app = DesktopApplication(config=config)
                app.run()

                MockWindow.assert_called_once()
                assert app.window is not None

    def test_shutdown_quits(self):
        with patch("app.client.ui.app.ctk.set_appearance_mode"):
            with patch("app.client.ui.app.MainWindow") as MockWindow:
                mock_window = MagicMock()
                MockWindow.return_value = mock_window
                mock_window.mainloop.side_effect = KeyboardInterrupt()

                app = DesktopApplication()
                app.run()
                app.shutdown()
                assert app._shutdown_requested is True

    def test_double_shutdown_safe(self):
        app = DesktopApplication()
        app.shutdown()
        app.shutdown()


class TestDesktopApplicationEvents:
    def test_run_publishes_started_event(self):
        with patch("app.client.ui.app.ctk.set_appearance_mode"):
            with patch("app.client.ui.app.MainWindow") as MockWindow:
                mock_window = MagicMock()
                MockWindow.return_value = mock_window
                mock_window.mainloop.side_effect = KeyboardInterrupt()

                received = []

                def handler(event, **data):
                    received.append({"event": event, **data})

                app = DesktopApplication()
                app.events.subscribe("application.started", handler)
                app.run()
                assert len(received) >= 1

    def test_shutdown_publishes_stopped_event(self):
        app = DesktopApplication()
        app._running = True
        received = []

        def handler(event, **data):
            received.append({"event": event, **data})

        app.events.subscribe("application.stopped", handler)
        app.shutdown()
        assert len(received) >= 1


class TestDesktopApplicationViewManagement:
    def test_register_view(self):
        with patch("app.client.ui.app.ctk.set_appearance_mode"):
            with patch("app.client.ui.app.MainWindow") as MockWindow:
                mock_window = MagicMock()
                MockWindow.return_value = mock_window
                mock_window.mainloop.side_effect = KeyboardInterrupt()

                from app.client.ui.views import PlaceholderView

                app = DesktopApplication()
                app.register_view("test", PlaceholderView, title="Test View", icon="🔬")
                assert app.navigator.get_title("test") == "Test View"

    def test_navigate(self):
        with patch("app.client.ui.app.ctk.set_appearance_mode"):
            with patch("app.client.ui.app.MainWindow") as MockWindow:
                mock_window = MagicMock()
                MockWindow.return_value = mock_window

                from app.client.ui.views import PlaceholderView

                app = DesktopApplication()
                app.register_view("test", PlaceholderView, title="Test")
                result = app.navigate("test")
                # Navigate works even without container for lazy loading
                assert app.navigator.active_view == "test"

    def test_register_view_before_run(self):
        app = DesktopApplication()
        from app.client.ui.views import PlaceholderView

        app.register_view("test", PlaceholderView, title="Pre-registered")
        assert app.navigator.get_title("test") == "Pre-registered"


class TestDesktopApplicationConfigUsage:
    def test_uses_config_values(self):
        config = Config()
        config.CLIENT_API_URL = "http://custom:8000"
        config.CLIENT_WS_URL = "ws://custom:8000/ws"

        app = DesktopApplication(config=config)
        assert app.client._api_url == "http://custom:8000"
        assert app.client._ws_url == "ws://custom:8000/ws"

    def test_default_config_used(self):
        app = DesktopApplication()
        assert app.client._api_url == Config.CLIENT_API_URL


class TestDesktopApplicationBackwardCompatibility:
    def test_no_direct_server_access(self):
        import inspect
        source = inspect.getsource(DesktopApplication)
        forbidden = ["Kernel", "ServiceRegistry", "EventBus", "AIManager", "PluginManager"]
        for name in forbidden:
            assert name not in source, f"DesktopApplication references {name}"

    def test_only_uses_client_layer(self):
        app = DesktopApplication()
        assert hasattr(app, "client")
        assert not hasattr(app, "kernel")
        assert not hasattr(app, "service_registry")
        assert not hasattr(app, "event_bus")
