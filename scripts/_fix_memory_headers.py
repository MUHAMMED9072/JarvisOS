"""
One-off fix script: the 5 stub memory files were written with literal
backslash-quote sequences ('\\"\\"\\"') as their docstring delimiter
instead of actual triple quotes ('"""'). That makes the file
non-Python and trips Pylint/IDE inspections. Replace the malformed
delimiters with real triple quotes and drop the per-file
"Version: 0.6.0" header line — the canonical version lives in
Config.VERSION, per CODING_STANDARDS.md.
"""
from pathlib import Path

TARGETS = [
    "app/memory/context.py",
    "app/memory/knowledge.py",
    "app/memory/preferences.py",
    "app/memory/projects.py",
    "app/memory/search.py",
]

# Build the search/replace bytes without leaning on Python string
# escapes that collide with the malformed content.
BACKSLASH = b"\\"          # one backslash
QUOTE = b'"'               # one double-quote
MALFORMED_DELIM = BACKSLASH + QUOTE + BACKSLASH + QUOTE + BACKSLASH + QUOTE  # 6 bytes
GOOD_DELIM = QUOTE + QUOTE + QUOTE                                              # 3 bytes

OLD_HEADER = b"Version: 0.6.0\n"

for rel in TARGETS:
    p = Path(rel)
    raw = p.read_bytes()
    new = raw.replace(MALFORMED_DELIM, GOOD_DELIM).replace(OLD_HEADER, b"")
    if new == raw:
        print("NO CHANGE:", rel)
        continue
    p.write_bytes(new)
    print("FIXED:", rel, "->", repr(new[:80]))
