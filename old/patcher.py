from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List
from .io_utils import read_text
from .line_numbers import strip_line_numbers
import ast


@dataclass
class Edit:
    file: str
    original_numbered: str
    edited: str


class PatchApplicationError(Exception):
    pass


def apply_edits(repo: Path, edits: List[Edit]) -> List[Path]:
    modified: List[Path] = []
    for e in edits:
        target = repo / e.file
        if not target.exists():
            raise PatchApplicationError(f"Target file not found: {e.file}")
        text = read_text(target)
        lines = text.splitlines(keepends=True)
        start, end, _ = strip_line_numbers(e.original_numbered)
        s_idx = max(0, start - 1)
        e_idx = min(len(lines), end)
        # Preserve newline style
        newline = "\n"
        for l in lines:
            if l.endswith("\r\n"):
                newline = "\r\n"; break
            if l.endswith("\n"):
                newline = "\n"; break
        replacement = (e.edited if e.edited.endswith("\n") else e.edited + "\n").replace("\n", newline)
        new_lines = lines[:s_idx] + [replacement] + lines[e_idx:]
        new_text = "".join(new_lines)
        target.write_text(new_text, encoding="utf-8")
        modified.append(target)
    return modified


def syntax_check_python(files: List[Path]) -> bool:
    ok = True
    for f in files:
        try:
            src = read_text(f)
            ast.parse(src)
        except SyntaxError as ex:
            print(f"[syntax] {f}: {ex}")
            ok = False
    return ok
