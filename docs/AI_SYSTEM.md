# AI System

> Part of the JARVIS OS Architecture Bible. See `JARVIS_ARCHITECT.md` for the
> system-wide index. Related: `EVOLUTION_ENGINE.md` (the largest actual
> consumer of `OllamaProvider`, currently outside this system's router),
> `MODULE_GUIDE.md` (per-file maturity for each provider).

## Architecture

```
AIManager.ask(provider, prompt)
      │
      ▼
AIRouter.ask(provider, prompt)
      │  looks up self.providers[provider]
      ▼
<Provider>.generate(prompt: str) -> str
```

`AIRouter` eagerly constructs all five providers in `__init__`, so every
provider's `__init__` runs (and every `.env` lookup happens) as soon as an
`AIRouter` is created, regardless of which provider is actually used.

## Providers

| Provider | Backing | Status |
|---|---|---|
| `OllamaProvider` | Local Ollama daemon via the `ollama` Python package, default model `qwen2.5-coder` | **Implemented.** No API key required (local). This is the only provider currently exercised, and only by `app/evolution/generator.py`, `autofix.py`, and `planner.py`, all of which call it directly rather than through `AIRouter`/`AIManager` — see item 2 below. |
| `OpenAIProvider` | `OPENAI_API_KEY` from `.env` | Key-check only; `generate()` raises `NotImplementedError`. |
| `ClaudeProvider` | `ANTHROPIC_API_KEY` from `.env` | Key-check only; `generate()` raises `NotImplementedError`. |
| `GeminiProvider` | `GEMINI_API_KEY` from `.env` | Key-check only; `generate()` raises `NotImplementedError`. |
| `DeepSeekProvider` | `DEEPSEEK_API_KEY` from `.env` | Key-check only; `generate()` raises `NotImplementedError`. |

## Known Gaps

1. **No shared contract.** Nothing declares that a provider must implement
   `generate(prompt: str) -> str`. It's true by convention only. Add:

   ```python
   from typing import Protocol

   class AIProvider(Protocol):
       def generate(self, prompt: str) -> str: ...
   ```

   and type `AIRouter.providers` as `dict[str, AIProvider]`.

2. **Evolution Engine bypasses the router in three places, not two.**
   `CodeGenerator.generate_task` (`generator.py`), `AutoFixer.fix`
   (`autofix.py`), and `EvolutionPlanner.create_plan` (`planner.py`) each do
   `OllamaProvider().generate(prompt)` directly (`grep -n OllamaProvider
   app/evolution/*.py` confirms exactly these three call sites). This means
   the entire Evolution Engine — planning, generation, and repair alike —
   cannot be redirected to a different model/provider without editing all
   three files, and it triplicates provider-construction logic outside
   `AIRouter`. Future work should have the Evolution Engine take an
   `AIProvider` (or `AIManager`) as a constructor dependency instead — see
   `EVOLUTION_ENGINE.md` §Orchestration for how `planner.py`, `generator.py`,
   and `autofix.py` are actually wired together today (only `planner.py` and
   `generator.py` are reachable from the one real entry point,
   `EvolutionManager.run()`; `autofix.py` is currently unreachable from any
   caller in the package).

3. **No streaming, no token/cost accounting, no retry/backoff, no timeout.**
   `OllamaProvider.generate` is a single blocking call with no error handling
   — a dead Ollama daemon will raise an unhandled connection error all the
   way up through `CodeGenerator.generate_task`.

4. **No provider selection policy.** `Config.DEFAULT_BRAIN` /
   `REASONING_BRAIN` / `CODING_BRAIN` exist in `Config` but nothing maps
   those brain names to an AI provider or model — `app/cortex/brains/*.py`
   are all empty files, so `BrainSelector`'s output currently has nowhere to
   go.

## Rules for Implementing a Real Provider

When implementing `OpenAIProvider`, `ClaudeProvider`, `GeminiProvider`, or
`DeepSeekProvider` (Phase 5 work), each must:

- Implement the `AIProvider` protocol above exactly — no signature drift.
- Raise a specific, caught exception type (not let SDK exceptions propagate
  unannotated) so callers like `CodeGenerator` can distinguish "no API key"
  from "network error" from "rate limited."
- Read configuration only from `.env` via `python-dotenv`, consistent with
  the existing key-check pattern — never hardcode a key or accept one as a
  plain function argument that could end up logged.
- Include a timeout on every network call.
- Not print to stdout for status messages (`generator.py`/`autofix.py`
  currently do `print("[AI] Building project-aware patch...")` — acceptable
  today as a CLI tool, but a real provider implementation should log via
  `JarvisLogger` instead so behavior is consistent whether invoked from the
  Evolution Engine, a skill, or the GUI).
