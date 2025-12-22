from __future__ import annotations
import ast
import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass
class FunctionDoc:
    name: str
    content: str


@dataclass
class ClassDoc:
    name: str
    docstring: str
    methods: List[str]


@dataclass
class FileDoc:
    file_path: str
    module_docstring: str
    classes: List[ClassDoc]
    functions: List[FunctionDoc]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def iter_files(root: Path, patterns: List[str]) -> Iterable[Path]:
    for dirpath, _, filenames in os.walk(root):
        for pat in patterns:
            for fname in fnmatch.filter(filenames, pat):
                yield Path(dirpath) / fname


# os used by iter_files
import os  # keep import here to avoid polluting global namespace


def _format_func_signature(fn: ast.AST) -> str:
    name = getattr(fn, "name", "function")
    try:
        args = ast.unparse(fn.args)  # type: ignore[attr-defined]
    except Exception:
        arg_names = [getattr(a, "arg", "arg") for a in getattr(fn.args, "args", [])]
        args = "(" + ", ".join(arg_names) + ")"
    return f"{name}{args}"


def extract_function_snippets(src_lines: List[str], start: int, end: int, head: int = 5, tail: int = 5) -> str:
    start = max(1, start)
    end = min(len(src_lines), end)
    head_block = src_lines[start - 1: min(end, start - 1 + head)]
    tail_block = src_lines[max(start - 1, end - tail): end]
    blocks: List[str] = []
    if head_block:
        blocks.append("".join(head_block))
    if tail_block and tail_block != head_block:
        blocks.append("...\n")
        blocks.append("".join(tail_block))
    return "".join(blocks)


essential_patterns = ["*.py"]


def build_python_file_doc(py_path: Path, rel_to: Path) -> Optional[FileDoc]:
    src = _read_text(py_path)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    module_doc = ast.get_docstring(tree) or ""
    src_lines = src.splitlines(keepends=True)

    classes: List[ClassDoc] = []
    functions: List[FunctionDoc] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = []
            for b in node.bases:
                try:
                    bases.append(ast.unparse(b))
                except Exception:
                    bases.append(getattr(b, "id", ""))
            name_hdr = f"{node.name}({', '.join(bases)})" if bases else node.name
            doc = ast.get_docstring(node) or ""
            methods = []
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(_format_func_signature(sub))
            classes.append(ClassDoc(name_hdr, doc, methods))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig = _format_func_signature(node)
            start = getattr(node, "lineno", 1)
            end = getattr(node, "end_lineno", start)
            content = extract_function_snippets(src_lines, start, end)
            functions.append(FunctionDoc(sig, content))

    return FileDoc(
        file_path=str(py_path.relative_to(rel_to).as_posix()),
        module_docstring=module_doc,
        classes=classes,
        functions=functions,
    )


def build_repo_docs(repo: Path, include_patterns: List[str]) -> List[FileDoc]:
    # Currently supports Python files; patterns let you narrow scope.
    patterns = include_patterns or essential_patterns
    docs: List[FileDoc] = []
    for p in iter_files(repo, patterns):
        fd = build_python_file_doc(p, repo)
        if fd:
            docs.append(fd)
    return docs


def filedoc_to_json(fd: FileDoc) -> dict:
    return {
        "file_path": fd.file_path,
        "module_docstring": fd.module_docstring,
        "classes": [
            {"name": c.name, "docstring": c.docstring, "methods": c.methods}
            for c in fd.classes
        ],
        "functions": [
            {"name": f.name, "content": f.content}
            for f in fd.functions
        ],
    }
