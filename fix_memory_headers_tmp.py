"""
One-off fix: the 5 stub memory files contain a malformed docstring
delimiter (literal backslash-quote sequences instead of triple quotes)
and a stale 'Version: 0.6.0' header. Both must be fixed together;
otherwise the file is still non-Python.
"""
from pathlib import Path

TARGETS = [
    "app/memory/context.py",
    "app/memory/knowledge.py",
    "app/memory/preferences.py",
    "app/memory/projects.py",
    "app/memory/search.py",
]

# backslash = 0x5c, double-quote = 0x22, newline = 0x0a
MALFORMED_DELIM = bytes([0x5C, 0x22, 0x5C, 0x22, 0x5C, 0x22])  # \"\"\" (literal)
GOOD_DELIM = bytes([0x22, 0x22, 0x22])                          # """
OLD_HEADER = b"Version: 0.6.0" + bytes([0x0A])                  # Version: 0.6.0\n

for rel in TARGETS:
    p = Path(rel)
    raw = p.read_bytes()
    new = raw.replace(MALFORMED_DELIM, GOOD_DELIM).replace(OLD_HEADER, b"")
    if new == raw:
        print("NO CHANGE:", rel)
        continue
    p.write_bytes(new)
    print("FIXED:", rel, "->", repr(new[:80]))
