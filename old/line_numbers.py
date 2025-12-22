from __future__ import annotations
import re
from typing import List, Tuple

LINE_NO_PATTERN = re.compile(r"^\s*(\d+)\s+")


def add_line_numbers(text: str, start: int = 1) -> str:
    lines = text.splitlines(keepends=False)
    width = max(2, len(str(start + len(lines) - 1)))
    return "\n".join(f"{i:>{width}} {line}" for i, line in enumerate(lines, start=start))


def strip_line_numbers(numbered: str) -> Tuple[int, int, List[str]]:
    start_line = None
    end_line = None
    body: List[str] = []
    for raw in numbered.splitlines():
        m = LINE_NO_PATTERN.match(raw)
        if not m:
            body.append(raw)
            continue
        n = int(m.group(1))
        code = raw[m.end():]
        if start_line is None:
            start_line = n
        end_line = n
        body.append(code)
    if start_line is None or end_line is None:
        raise ValueError("Could not detect line numbers in the original snippet.")
    return start_line, end_line, body
