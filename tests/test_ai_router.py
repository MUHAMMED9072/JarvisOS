# tests/test_ai_router.py

import importlib
import sys
import textwrap
from pathlib import Path

import pytest

from app.ai.providers.base import AIProvider
from app.ai.router import AIRouter


# ---------------------------------------------------------------------------
# Fake providers used as lightweight, network-free stand-ins.
# ---------------------------------------------------------------------------

class _FakeProvider(AIProvider):

    def __init__(self, name: str, payload: str = "ok"):

        self.provider_name = name
        self._payload = payload
        self.instantiations = 0
        self.generate_calls: list[str] = []

    def generate(self, prompt: str) -> str:

        self.generate_calls.append(prompt)
        return f"{self._payload}::{prompt}"


class _ExplodingProvider(AIProvider):

    provider_name = "exploder"

    def generate(self, prompt: str) -> str:

        raise RuntimeError("boom")


class _NotAProvider:
    """Deliberately does not implement the AIProvider protocol."""


# ---------------------------------------------------------------------------
# Helpers: build an AIRouter around a temp package of provider modules.
# ---------------------------------------------------------------------------

def _write_module(directory: Path, name: str, source: str) -> Path:

    module_file = directory / f"{name}.py"
    module_file.write_text(textwrap.dedent(source).lstrip())
    return module_file


@pytest.fixture
def provider_package(tmp_path):
    """
    Redirect ``app.ai.providers.__path__`` to a temp directory for the
    duration of the test. ``AIRouter._discover_providers`` walks
    ``providers_package.__path__``; by replacing the attribute we make
    the router discover only the modules we drop into the temp dir.

    The modules written into the temp dir import the real
    ``app.ai.providers.base.AIProvider``. The test module imports it
    at collection time, so it is normally already cached in
    ``sys.modules`` before this fixture runs -- but that's an
    incidental ordering fact, not a guarantee. Every dynamically
    written provider module does ``from app.ai.providers.base import
    AIProvider``, and that import is resolved against whatever
    ``providers_pkg.__path__`` happens to be *at the moment it
    executes*. If ``app.ai.providers.base`` were ever missing from
    ``sys.modules`` when the swap below is in effect (e.g. because
    something upstream evicted it, or this fixture is reused in a
    context where the module-level import hasn't run), the import
    would fail with ``ModuleNotFoundError`` for every provider
    module. ``AIRouter._discover_providers`` catches and logs that
    per-module, so the visible symptom isn't a traceback -- it's a
    silently empty ``router.providers`` dict. Importing it explicitly
    here, under the *real* path, removes that hidden dependency on
    import order instead of relying on it.

    A second, unrelated hazard lives in the reload tests: they write
    a module, import it, then rewrite the same filename with new
    content and reload it. Python's default bytecode cache validates
    against the source's mtime truncated to whole seconds, so two
    writes within the same wall-clock second can hash-collide and
    ``importlib.reload`` will silently keep executing the stale
    cached bytecode. Disabling bytecode writes for the duration of
    the fixture forces every import to compile straight from the
    on-disk source, which is what these tests actually intend to
    exercise.
    """

    from app.ai import providers as providers_pkg

    # Guarantee this is resident in sys.modules under the *real*
    # package path before we repoint providers_pkg.__path__ below.
    # NOTE: this must be an assertion, not a re-import. If
    # 'app.ai.providers.base' were ever evicted from sys.modules and
    # then re-imported here, Python would execute base.py again and
    # produce a *second*, distinct AIProvider class object -- while
    # every dynamically written provider module and every isinstance/
    # issubclass check elsewhere in this file still reference the
    # *original* class object imported at the top of this module.
    # issubclass(NewClass, OriginalClass) is False even though they
    # look identical, so "fixing" a missing import this way would
    # silently break discovery in a way that's harder to notice than
    # the ModuleNotFoundError it's meant to prevent. The real
    # guarantee comes from the module-level import at the top of this
    # file, which runs once at collection time and is never evicted
    # (the teardown below explicitly special-cases it); this assert
    # just makes that guarantee explicit and fails loudly if it's
    # ever violated instead of silently producing an empty
    # router.providers.
    assert "app.ai.providers.base" in sys.modules, (
        "app.ai.providers.base must already be imported before "
        "providers_pkg.__path__ is redirected, or every dynamically "
        "written provider module's own import of it will fail"
    )

    providers_dir = tmp_path / "providers"
    providers_dir.mkdir(parents=True)

    original_path = list(providers_pkg.__path__)
    original_dont_write_bytecode = sys.dont_write_bytecode

    sys.dont_write_bytecode = True
    providers_pkg.__path__ = [str(providers_dir)]
    importlib.invalidate_caches()

    try:
        yield providers_dir
    finally:
        # Restore the package search path exactly as it was.
        providers_pkg.__path__ = original_path
        sys.dont_write_bytecode = original_dont_write_bytecode
        importlib.invalidate_caches()

        # Purge any modules that were loaded from the temp directory so
        # later tests start from a clean import state.
        providers_dir_str = str(providers_dir)
        stale: list[str] = []
        for mod_name, mod in list(sys.modules.items()):
            if not mod_name.startswith("app.ai.providers."):
                continue
            if mod_name == "app.ai.providers.base":
                continue
            mod_file = getattr(mod, "__file__", None)
            if mod_file is not None and mod_file.startswith(providers_dir_str):
                stale.append(mod_name)
        for mod_name in stale:
            del sys.modules[mod_name]
            attr = mod_name.rsplit(".", 1)[-1]
            if hasattr(providers_pkg, attr):
                try:
                    delattr(providers_pkg, attr)
                except AttributeError:
                    pass


def _build_router(providers_dir: Path) -> AIRouter:
    """
    Build a router whose discovery sees only the temp provider modules.
    The fixture has already redirected ``app.ai.providers.__path__``,
    so a plain ``AIRouter()`` instantiates against the temp tree.
    """

    return AIRouter()


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

class TestAIRouterDiscovery:

    def test_automatic_provider_discovery(self, provider_package):

        providers_dir = provider_package

        _write_module(
            providers_dir,
            "alpha",
            """
            from app.ai.providers.base import AIProvider

            class AlphaProvider(AIProvider):
                provider_name = "alpha"
                def generate(self, prompt):
                    return f"alpha:{prompt}"
            """,
        )
        _write_module(
            providers_dir,
            "beta",
            """
            from app.ai.providers.base import AIProvider

            class BetaProvider(AIProvider):
                provider_name = "beta"
                def generate(self, prompt):
                    return f"beta:{prompt}"
            """,
        )
        _write_module(
            providers_dir,
            "gamma",
            """
            VALUE = 123
            def not_a_skill():
                return 1
            """,
        )

        router = _build_router(providers_dir)

        assert set(router.providers) == {"alpha", "beta"}
        assert isinstance(router.providers["alpha"], AIProvider)
        assert isinstance(router.providers["beta"], AIProvider)

    def test_discovery_ignores_infrastructure_modules(self, provider_package):

        providers_dir = provider_package

        # ``base`` and ``__init__`` are always ignored.
        # ``base`` is already present in the real package (cached in
        # ``sys.modules``) but the router only iterates the temp ``__path__``,
        # so neither ends up in the discovered map.
        _write_module(
            providers_dir,
            "alpha",
            """
            from app.ai.providers.base import AIProvider

            class AlphaProvider(AIProvider):
                provider_name = "alpha"
                def generate(self, prompt):
                    return "x"
            """,
        )

        router = _build_router(providers_dir)

        assert "base" not in router.providers
        assert "__init__" not in router.providers
        assert "alpha" in router.providers


# ---------------------------------------------------------------------------
# register / unregister
# ---------------------------------------------------------------------------

class TestAIRouterRegister:

    def test_register_valid_provider(self):

        router = AIRouter.__new__(AIRouter)
        router.providers = {}

        provider = _FakeProvider("custom_one")

        router.register(provider)

        assert router.providers["custom_one"] is provider

    def test_register_rejects_duplicate(self):

        router = AIRouter.__new__(AIRouter)
        router.providers = {}

        first = _FakeProvider("dup")
        second = _FakeProvider("dup")

        router.register(first)
        with pytest.raises(ValueError):
            router.register(second)

        assert router.providers["dup"] is first

    def test_register_rejects_invalid_provider(self):

        router = AIRouter.__new__(AIRouter)
        router.providers = {}

        with pytest.raises(TypeError):
            router.register(_NotAProvider())

        assert router.providers == {}

    def test_register_rejects_missing_provider_name(self):

        class _NamelessProvider(AIProvider):
            provider_name = ""
            def generate(self, prompt):
                return prompt

        router = AIRouter.__new__(AIRouter)
        router.providers = {}

        with pytest.raises(ValueError):
            router.register(_NamelessProvider())

        assert router.providers == {}


class TestAIRouterUnregister:

    def test_unregister_existing_provider(self):

        router = AIRouter.__new__(AIRouter)
        provider = _FakeProvider("ephemeral")
        router.providers = {"ephemeral": provider}

        assert router.unregister("ephemeral") is True
        assert "ephemeral" not in router.providers

    def test_unregister_unknown_provider(self):

        router = AIRouter.__new__(AIRouter)
        router.providers = {"present": _FakeProvider("present")}

        assert router.unregister("missing") is False
        assert router.unregister("") is False
        # Existing provider is untouched.
        assert "present" in router.providers


# ---------------------------------------------------------------------------
# ask
# ---------------------------------------------------------------------------

class TestAIRouterAsk:

    def test_ask_dispatches_to_correct_provider(self):

        router = AIRouter.__new__(AIRouter)
        alpha = _FakeProvider("alpha", payload="A")
        beta = _FakeProvider("beta", payload="B")
        router.providers = {"alpha": alpha, "beta": beta}

        assert router.ask("alpha", "hello") == "A::hello"
        assert router.ask("beta", "world") == "B::world"
        assert alpha.generate_calls == ["hello"]
        assert beta.generate_calls == ["world"]

    def test_ask_raises_for_unknown_provider(self):

        router = AIRouter.__new__(AIRouter)
        router.providers = {}

        with pytest.raises(ValueError):
            router.ask("ghost", "hi")


# ---------------------------------------------------------------------------
# reload
# ---------------------------------------------------------------------------

class TestAIRouterReload:

    def test_reload_existing_provider(self, provider_package):

        providers_dir = provider_package

        _write_module(
            providers_dir,
            "charlie",
            """
            from app.ai.providers.base import AIProvider

            class CharlieProvider(AIProvider):
                provider_name = "charlie"
                payload = "v1"

                def generate(self, prompt):
                    return f"{self.payload}:{prompt}"
            """,
        )

        router = _build_router(providers_dir)
        first = router.providers["charlie"]
        assert first.generate("ping") == "v1:ping"

        # Mutate the module on disk to simulate a new release.
        (providers_dir / "charlie.py").write_text(textwrap.dedent("""
            from app.ai.providers.base import AIProvider

            class CharlieProvider(AIProvider):
                provider_name = "charlie"
                payload = "v2"

                def generate(self, prompt):
                    return f"{self.payload}:{prompt}"
            """).lstrip())

        assert router.reload("charlie") is True
        second = router.providers["charlie"]

        assert second is not first
        assert second.generate("ping") == "v2:ping"

    def test_reload_unknown_provider(self):

        router = AIRouter.__new__(AIRouter)
        router.providers = {}

        assert router.reload("ghost") is False
        assert router.providers == {}

    def test_reload_rolls_back_on_registration_failure(self, provider_package, monkeypatch):
        """
        The real reload pipeline must run end-to-end:

        * ``importlib.reload`` is invoked on the provider module,
        * the reloaded module is scanned for ``AIProvider`` subclasses,
        * the new instance is constructed,
        * the re-registration step is forced to fail,
        * the original provider instance is restored.

        Only ``router.register`` is patched. Everything else
        (discovery, ``importlib.reload``, instantiation, rollback) is
        the production code path.
        """

        providers_dir = provider_package

        _write_module(
            providers_dir,
            "delta",
            """
            from app.ai.providers.base import AIProvider

            class DeltaProvider(AIProvider):
                provider_name = "delta"

                def generate(self, prompt):
                    return f"delta:{prompt}"
            """,
        )

        router = _build_router(providers_dir)
        original = router.providers["delta"]
        assert isinstance(original, AIProvider)

        # Rewrite the module so reload still finds a valid provider.
        # The class name and provider_name are preserved so the reload
        # path remains a pure no-op aside from the ``register`` call
        # we are about to force-fail.
        (providers_dir / "delta.py").write_text(textwrap.dedent("""
            from app.ai.providers.base import AIProvider

            class DeltaProvider(AIProvider):
                provider_name = "delta"

                def generate(self, prompt):
                    return f"delta:v2:{prompt}"
            """).lstrip())

        def failing_register(provider):

            raise RuntimeError("forced registration failure")

        monkeypatch.setattr(router, "register", failing_register)

        # ``reload`` must surface the failure as a ``False`` return.
        assert router.reload("delta") is False

        # The original provider instance is restored verbatim.
        assert router.providers["delta"] is original

        # The router still routes through the original provider.
        assert router.ask("delta", "ping") == original.generate("ping")