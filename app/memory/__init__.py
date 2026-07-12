"""
JARVIS Memory Engine

Persistent memory subsystem.

Modules:
- storage
- session
- history
- projects
- preferences
- knowledge
- search
- context
"""

from .manager import MemoryManager

__all__ = ["MemoryManager"]