# GUI Guidelines

> Part of the JARVIS OS Architecture Bible. See `JARVIS_ARCHITECT.md` for the
> system-wide index. Related: `MODULE_GUIDE.md` §app.gui,
> `JARVIS_ARCHITECT.md` §4 item 2 (GUI is disconnected from the kernel).

## Stack

`customtkinter` (per `requirements.txt`; `ttkbootstrap` is also listed but no
usage was found in the files read during this analysis — verify before
assuming it's active).

## Design Tokens (`app/gui/theme.py`)

```python
APP_TITLE = "JARVIS OS"
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 850
SIDEBAR_WIDTH = 240

COLORS = {
    "background": "#0F172A",
    "sidebar":    "#111827",
    "card":       "#1E293B",
    "accent":     "#00D4FF",
    "text":       "#F8FAFC",
    "success":    "#22C55E",
    "warning":    "#FACC15",
    "danger":     "#EF4444",
}
```

Dark, slate/cyan themed. **All new GUI code must reference `COLORS` and the
size constants from `theme.py`** — never hardcode a hex color or pixel
dimension inline in a component or page file. This is already followed by
`window.py` and `sidebar.py`; keep following it.

## Component Inventory

| File | Status |
|---|---|
| `window.py` | Implemented (224 lines) — main application window. |
| `theme.py` | Implemented — design tokens above. |
| `components/sidebar.py` | Implemented — renders nav buttons for Dashboard, AI Chat, Voice, Memory, Automation, Plugins, Settings. **Buttons have no click handlers wired** — `ctk.CTkButton(self, text=item, ...)` does not set a `command=`. |
| `components/status_card.py` | Empty. |
| `components/statusbar.py` | Empty. |
| `components/topbar.py` | Empty. |
| `pages/dashboard.py` | Empty. |
| `pages/ai_chat.py` | Empty. |
| `pages/settings.py` | Empty. |

Note the mismatch: `Sidebar`'s menu items (`Dashboard, AI Chat, Voice,
Memory, Automation, Plugins, Settings`) imply seven pages, but only three
page files exist (`dashboard.py`, `ai_chat.py`, `settings.py`), and even
those are empty — `Voice`, `Memory`, `Automation`, `Plugins` have no
corresponding page file at all yet.

## Integration Gap (see `JARVIS_ARCHITECT.md` §4)

`JarvisApp.run()` (`app/core/app.py`) constructs `JarvisWindow()` directly:

```python
class JarvisApp:
    def run(self):
        window = JarvisWindow()
        window.mainloop()
```

It receives no `ServiceRegistry`, so nothing inside `JarvisWindow` (or its
child components, once implemented) has a sanctioned way to reach
`skill_manager`, `memory`, or `event_bus`. Before implementing any page that
needs live data (dashboard status, AI chat history, memory browser), the GUI
needs a construction path that receives the registry — e.g.
`JarvisApp(registry: ServiceRegistry).run()`, with `main.py` passing
`kernel.registry` through after `kernel.boot()`.

## Rules for New GUI Work

1. Every page/component takes its dependencies (registry, or the specific
   services it needs) as constructor arguments — never imports and
   instantiates `MemoryManager()`/`SkillManager()` directly, which would
   create a second, disconnected instance from the one the kernel manages.
2. Wire `Sidebar` button `command=` callbacks to an actual navigation
   mechanism (e.g. a `NavigationController` using `app/models/navigation.py`,
   which already exists as a home for this) before adding more pages, rather
   than letting each new page invent its own navigation approach.
3. Keep business logic out of GUI classes — a page should call into a
   skill/service and render the `SkillResult`/data it gets back, not
   reimplement logic that belongs in `app/skills` or `app/memory`.
4. Follow `CODING_STANDARDS.md` typing rules even in GUI code — customtkinter
   widget attributes should still be type-hinted where practical.
