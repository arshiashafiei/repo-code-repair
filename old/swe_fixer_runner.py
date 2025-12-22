#!/usr/bin/env python3
"""
SWE-Fixer style minimal runner (Python repos)

What it does
------------
- Builds compact "file documentations" (skeletons) for a repo's Python files
  (module docstring, class headers + method names, function signatures,
  and the first & last five lines of each function body).
- Runs BM25 over those docs using the GitHub issue text as the query to get top-30 candidates.
- Packs JSON for the retriever model (issue + README + BM25@30 docs + task) and
  expects JSON: {"files for editing": ["path", ...]}.
- Packs JSON for the editor model (issue + selected files with FULL contents *with line numbers* + task)
  and expects structured edits JSON with per-file {file, code snippet to be modified (WITH line numbers),
  edited code snippet (WITHOUT line numbers)}.
- Applies edits by line range (parsed from the provided numbered snippet), syntax-checks edited Python files,
  runs your test command, and supports up to N resampling attempts when invalid.
- Emits a git diff and (optionally) commits on success.

Notes
-----
- This reference runner focuses on Python repositories. To support more languages, implement
  additional skeleton builders and syntax checks.
- The runner is model-agnostic: point it at your inference endpoints via env vars or CLI flags.

Usage
-----
python swe_fixer_runner.py \
  --repo /path/to/repo \
  --issue-file /path/to/issue.md \
  --test-cmd "pytest -q" \
  --retriever-url http://localhost:8001/v1/infer \
  --editor-url http://localhost:8002/v1/infer \
  --max-attempts 5

Optional: --dry-run to only build/print JSON payloads without calling models.
"""
from __future__ import annotations

import argparse
import ast
import dataclasses
import fnmatch
import io
import itertools
import json
import math
import os
import re
import shutil
import subprocess
import sys
import textwrap
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Iterable, Optional

# --------------------------
# BM25 (lightweight, no deps)
# --------------------------

def _tokenize(text: str) -> List[str]:
    # Simple alnum tokenizer, lowercase
    return re.findall(r"[A-Za-z0-9_]+", text.lower())

class BM25:
    def __init__(self, docs: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs = docs
        self.N = len(docs)
        self.avgdl = sum(len(d) for d in docs) / self.N if self.N else 0.0
        # term -> df
        self.df: Dict[str, int] = Counter(itertools.chain.from_iterable(set(d) for d in docs))
        # precompute idf
        self.idf: Dict[str, float] = {}
        for term, df in self.df.items():
            # Classic BM25 idf with +0.5 smoothing to avoid div by zero
            self.idf[term] = math.log((self.N - df + 0.5) / (df + 0.5) + 1e-9)

    def score(self, q: List[str], doc: List[str]) -> float:
        if not doc:
            return 0.0
        freq = Counter(doc)
        score = 0.0
        dl = len(doc)
        for term in q:
            if term not in freq:
                continue
            f = freq[term]
            idf = self.idf.get(term, 0.0)
            denom = f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1.0))
            score += idf * (f * (self.k1 + 1)) / (denom or 1.0)
        return score

    def top_k(self, query_text: str, k: int) -> List[int]:
        q = _tokenize(query_text)
        scores = [self.score(q, d) for d in self.docs]
        return sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]

# --------------------------------------
# Repo scanning & Python skeleton builder
# --------------------------------------

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


def iter_files(root: Path, patterns: List[str]) -> Iterable[Path]:
    for dirpath, _, filenames in os.walk(root):
        for pat in patterns:
            for fname in fnmatch.filter(filenames, pat):
                yield Path(dirpath) / fname


def _get_source(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def extract_function_snippets(src_lines: List[str], start: int, end: int, head: int = 5, tail: int = 5) -> str:
    """
    Return the first `head` and last `tail` lines of a function body (1-based indices inclusive),
    joined with ellipsis between blocks, preserving original code.
    """
    start = max(1, start)
    end = min(len(src_lines), end)
    head_block = src_lines[start - 1: min(end, start - 1 + head)]
    tail_block = src_lines[max(start - 1, end - tail): end]
    blocks = []
    if head_block:
        blocks.append("".join(head_block))
    if tail_block and tail_block != head_block:
        blocks.append("...\n")
        blocks.append("".join(tail_block))
    return "".join(blocks)


def build_python_file_doc(py_path: Path, rel_to: Path) -> Optional[FileDoc]:
    src = _get_source(py_path)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        # Skip files that don't parse
        return None
    module_doc = ast.get_docstring(tree) or ""
    src_lines = src.splitlines(keepends=True)

    classes: List[ClassDoc] = []
    functions: List[FunctionDoc] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            # Compose a readable class header like Name(Base1, Base2)
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
                    sig = _format_func_signature(sub)
                    methods.append(sig)
            classes.append(ClassDoc(name_hdr, doc, methods))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig = _format_func_signature(node)
            # Use end_lineno when available to find tail
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


def _format_func_signature(fn: ast.AST) -> str:
    name = getattr(fn, "name", "function")
    try:
        args = ast.unparse(fn.args)  # type: ignore
    except Exception:
        # Fallback: basic arg names
        arg_names = []
        for a in getattr(fn.args, "args", []):
            arg_names.append(getattr(a, "arg", "arg"))
        args = "(" + ", ".join(arg_names) + ")"
    return f"{name}{args}"


def build_repo_docs(repo: Path, include_patterns: List[str]) -> List[FileDoc]:
    docs: List[FileDoc] = []
    for p in iter_files(repo, include_patterns):
        fd = build_python_file_doc(p, repo)
        if fd:
            docs.append(fd)
    return docs

# -----------------------------
# README, issue, and JSON pack
# -----------------------------

RETRIEVAL_TASK = (
    "You are selecting which files must be edited to resolve the issue.\n"
    "Use ONLY the provided 'retrieved file documentations' (BM25 top-30) and the README.\n"
    "Return exactly this JSON schema: {\"files for editing\": [\"<path>\", ...]}\n"
    "Rules:\n"
    "- Choose only from the candidate files provided.\n"
    "- Include only paths (strings); no duplicates.\n"
    "- Prefer the minimal set sufficient to fix the issue.\n"
    "- Output valid JSON only — no extra keys or explanations.\n"
)

EDITING_TASK = (
    "Generate a code patch that resolves the issue using the provided files (full contents with line numbers).\n"
    "Return exactly this JSON:\n"
    "{\n  \"reasoning process\": \"<markdown explanation>\",\n  \"edited code\": [\n    {\n      \"file\": \"<path>\",\n      \"code snippet to be modified\": \"<original snippet WITH line numbers>\",\n      \"edited code snippet\": \"<replacement WITHOUT line numbers>\"\n    }\n  ]\n}\n"
    "Rules:\n"
    "- Always include the file path for each change.\n"
    "- The original snippet must include line numbers so it can be precisely located.\n"
    "- Do NOT include line numbers in 'edited code snippet'.\n"
    "- Make minimal, necessary changes; keep code valid.\n"
    "- Return valid JSON only — no extra keys or commentary outside the JSON.\n"
)


def load_issue_text(path: Path) -> str:
    return _get_source(path)


def load_readme(repo: Path) -> str:
    for name in ["README.md", "README.MD", "README.rst", "README.txt", "README"]:
        p = repo / name
        if p.exists():
            return _get_source(p)
    return ""


def filedoc_to_json(fd: FileDoc) -> Dict:
    return {
        "file_path": fd.file_path,
        "module_docstring": fd.module_docstring,
        "classes": [
            {
                "name": c.name,
                "docstring": c.docstring,
                "methods": c.methods,
            }
            for c in fd.classes
        ],
        "functions": [
            {
                "name": f.name,
                "content": f.content,
            }
            for f in fd.functions
        ],
    }

# ----------------------------------
# HTTP calls (stdlib, no dependency)
# ----------------------------------

from urllib import request


def http_json_post(url: str, payload: Dict, headers: Optional[Dict[str, str]] = None, timeout: int = 300) -> Dict:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        text = body.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError(f"Model returned non-JSON response: {text[:500]}")

# ------------------------
# Line-numbering utilities
# ------------------------

LINE_NO_PATTERN = re.compile(r"^\s*(\d+)\s+")


def add_line_numbers(text: str, start: int = 1) -> str:
    lines = text.splitlines(keepends=False)
    # Format: right-align numbers to width of max line number, then a single space
    width = max(2, len(str(start + len(lines) - 1)))
    return "\n".join(f"{i:>{width}} {line}" for i, line in enumerate(lines, start=start))


def strip_line_numbers(numbered: str) -> Tuple[int, int, List[str]]:
    """Parse a numbered snippet -> (start_line, end_line, code_lines_without_numbers).
    Accepts lines that begin with optional spaces, then digits, then whitespace.
    """
    start_line = None
    end_line = None
    body: List[str] = []
    for raw in numbered.splitlines():
        m = LINE_NO_PATTERN.match(raw)
        if not m:
            # Allow blank/ellipsis lines; keep as-is
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


# ---------------------------
# Apply edits & run validators
# ---------------------------

@dataclass
class Edit:
    file: str
    original_numbered: str
    edited: str


class PatchApplicationError(Exception):
    pass


def apply_edits(repo: Path, edits: List[Edit]) -> List[Path]:
    """Apply edits in-place. Returns list of modified file paths.
    Raises PatchApplicationError if any edit cannot be applied.
    """
    modified: List[Path] = []
    for e in edits:
        target = repo / e.file
        if not target.exists():
            raise PatchApplicationError(f"Target file not found: {e.file}")
        text = _get_source(target)
        lines = text.splitlines(keepends=True)
        try:
            start, end, body = strip_line_numbers(e.original_numbered)
        except ValueError as ex:
            raise PatchApplicationError(str(ex))

        # Convert 1-based [start, end] to 0-based slices
        s_idx = max(0, start - 1)
        e_idx = min(len(lines), end)

        # Replace the selected lines with the edited snippet (no numbers)
        new_snippet = e.edited
        # Keep original newline style: use newline of the following line or default to "\n"
        newline = "\n"
        for l in lines:
            if l.endswith("\r\n"):
                newline = "\r\n"
                break
            if l.endswith("\n"):
                newline = "\n"
                break
        replacement = (new_snippet if new_snippet.endswith("\n") else new_snippet + "\n").replace("\n", newline)

        before = lines[:s_idx]
        after = lines[e_idx:]
        # If body has trailing blank line logic, ignore; we trust line range more than text match.
        new_lines = before + [replacement] + after
        new_text = "".join(new_lines)
        if new_text == text:
            # No change; warn but continue
            print(f"[warn] Edit produced no change for {e.file} lines {start}-{end}")
        target.write_text(new_text, encoding="utf-8")
        modified.append(target)
    return modified


def syntax_check_python(files: List[Path]) -> bool:
    ok = True
    for f in files:
        try:
            src = _get_source(f)
            ast.parse(src)
        except SyntaxError as ex:
            print(f"[syntax] {f}: {ex}")
            ok = False
    return ok


def run_tests(test_cmd: str, cwd: Path) -> int:
    try:
        result = subprocess.run(test_cmd, cwd=str(cwd), shell=True)
        return result.returncode
    except FileNotFoundError:
        return 127

# -----------------------
# End-to-end orchestration
# -----------------------

@dataclass
class RunnerConfig:
    repo: Path
    issue_text: str
    readme: str
    include_patterns: List[str]
    bm25_k: int
    test_cmd: str
    retriever_url: Optional[str]
    editor_url: Optional[str]
    api_key: Optional[str]
    max_attempts: int
    dry_run: bool
    commit_on_success: bool


def make_retriever_input(issue_text: str, readme: str, docs_json: List[Dict]) -> Dict:
    return {
        "issue": issue_text,
        "readme file": readme,
        "retrieved file documentations": docs_json,
        "task": RETRIEVAL_TASK,
    }


def make_editor_input(issue_text: str, files_payload: List[Dict]) -> Dict:
    return {
        "issue": issue_text,
        "files to be modified": files_payload,
        "task": EDITING_TASK,
    }


def line_numbered_content(path: Path) -> str:
    text = _get_source(path)
    return add_line_numbers(text, start=1)


def call_model(url: str, payload: Dict, api_key: Optional[str], temperature: float = 0.0) -> Dict:
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    # Allow temperature to be part of payload for generic servers
    enriched = {"temperature": temperature, **payload}
    return http_json_post(url, enriched, headers=headers)


def parse_retriever_output(resp: Dict) -> List[str]:
    if not isinstance(resp, dict) or "files for editing" not in resp:
        raise RuntimeError("Retriever output missing 'files for editing'.")
    files = resp["files for editing"]
    if not isinstance(files, list) or not all(isinstance(x, str) for x in files):
        raise RuntimeError("'files for editing' must be a list of paths (strings).")
    return files


def parse_editor_output(resp: Dict) -> Tuple[str, List[Edit]]:
    if not isinstance(resp, dict) or "edited code" not in resp:
        raise RuntimeError("Editor output missing 'edited code'.")
    reasoning = resp.get("reasoning process", "")
    edits_raw = resp["edited code"]
    edits: List[Edit] = []
    if not isinstance(edits_raw, list):
        raise RuntimeError("'edited code' must be a list.")
    for item in edits_raw:
        if not isinstance(item, dict):
            raise RuntimeError("Each edit must be an object.")
        file = item.get("file")
        orig = item.get("code snippet to be modified")
        new = item.get("edited code snippet")
        if not (isinstance(file, str) and isinstance(orig, str) and isinstance(new, str)):
            raise RuntimeError("Malformed edit item (file/original/edited).")
        edits.append(Edit(file=file, original_numbered=orig, edited=new))
    return reasoning, edits


def ensure_git_repo(repo: Path) -> bool:
    return (repo / ".git").exists()


def git_diff(repo: Path) -> str:
    try:
        out = subprocess.check_output(["git", "-C", str(repo), "diff"], text=True)
    except subprocess.CalledProcessError:
        out = ""
    return out


def git_commit_all(repo: Path, message: str) -> None:
    try:
        subprocess.check_call(["git", "-C", str(repo), "add", "."])
        subprocess.check_call(["git", "-C", str(repo), "commit", "-m", message])
    except subprocess.CalledProcessError:
        pass


def run_pipeline(cfg: RunnerConfig) -> int:
    # 1) Build file docs
    print("[1/7] Scanning repository and building file docs…")
    docs = build_repo_docs(cfg.repo, cfg.include_patterns)
    docs_json = [filedoc_to_json(fd) for fd in docs]

    if not docs_json:
        print("[error] No Python file docs found in repo.")
        return 2

    # 2) BM25@30
    print("[2/7] Computing BM25@%d over file docs…" % cfg.bm25_k)
    doc_texts = [
        fd["file_path"] + "\n" + fd.get("module_docstring", "") + "\n" +
        "\n".join(c.get("name", "") for c in fd.get("classes", [])) + "\n" +
        "\n".join(f.get("name", "") + "\n" + f.get("content", "") for f in fd.get("functions", []))
        for fd in docs_json
    ]
    bm25 = BM25([_tokenize(t) for t in doc_texts])
    idxs = bm25.top_k(cfg.issue_text, cfg.bm25_k)
    top_docs_json = [docs_json[i] for i in idxs]

    # 3) Retriever call
    retr_in = make_retriever_input(cfg.issue_text, cfg.readme, top_docs_json)
    if cfg.dry_run:
        print("\n[DRY RUN] Retriever input JSON:\n" + json.dumps(retr_in)[:2000] + ("…" if len(json.dumps(retr_in)) > 2000 else ""))
        return 0

    print("[3/7] Calling retriever model…")
    if not cfg.retriever_url:
        print("[error] --retriever-url is required (or use --dry-run).")
        return 2

    files_for_editing: List[str] = []
    temperature_seq = [0.0] + [0.7] * max(0, cfg.max_attempts - 1)
    for attempt, temp in enumerate(temperature_seq, start=1):
        try:
            resp = call_model(cfg.retriever_url, retr_in, cfg.api_key, temperature=temp)
            files_for_editing = parse_retriever_output(resp)
            if not files_for_editing:
                raise RuntimeError("Retriever returned empty file list.")
            break
        except Exception as ex:
            print(f"[retriever] attempt {attempt} failed: {ex}")
            if attempt >= cfg.max_attempts:
                return 3

    # 4) Prepare editor input (full contents with line numbers)
    print("[4/7] Preparing editor input for files:")
    for p in files_for_editing:
        print("       -", p)
    files_payload = []
    for rel in files_for_editing:
        p = cfg.repo / rel
        if not p.exists():
            print(f"[warn] missing file from retriever: {rel}")
            continue
        files_payload.append({
            "file": rel,
            "file content": line_numbered_content(p),
        })
    if not files_payload:
        print("[error] No files available for editor input.")
        return 4

    edit_in = make_editor_input(cfg.issue_text, files_payload)

    # 5) Editor call + post-processing loop
    print("[5/7] Calling editor model and validating outputs…")
    if not cfg.editor_url:
        print("[error] --editor-url is required (or use --dry-run).")
        return 2

    original_snapshots: Dict[Path, str] = {}
    rc = 1
    for attempt, temp in enumerate(temperature_seq, start=1):
        try:
            resp = call_model(cfg.editor_url, edit_in, cfg.api_key, temperature=temp)
            reasoning, edit_list = parse_editor_output(resp)
            print("[editor] reasoning (truncated):\n" + textwrap.shorten(reasoning, width=500, placeholder="…"))

            # Save originals before applying
            for e in edit_list:
                target = cfg.repo / e.file
                if target.exists() and target not in original_snapshots:
                    original_snapshots[target] = _get_source(target)

            modified = apply_edits(cfg.repo, edit_list)
            if not syntax_check_python(modified):
                raise PatchApplicationError("Syntax check failed after applying edits.")

            # Run tests
            print("[tests] Running:", cfg.test_cmd)
            exit_code = run_tests(cfg.test_cmd, cfg.repo)
            if exit_code != 0:
                raise PatchApplicationError(f"Tests failed with exit code {exit_code}.")

            rc = 0
            break
        except Exception as ex:
            print(f"[editor] attempt {attempt} failed: {ex}")
            # Restore originals
            for path, text in original_snapshots.items():
                if path.exists():
                    path.write_text(text, encoding="utf-8")
            if attempt >= cfg.max_attempts:
                rc = 5
                break

    # 6) Emit diff and optionally commit
    print("[6/7] Git diff of working tree:")
    if ensure_git_repo(cfg.repo):
        print(git_diff(cfg.repo))
        if rc == 0 and cfg.commit_on_success:
            git_commit_all(cfg.repo, "SWE-Fixer runner: apply patch for issue")
            print("[git] committed changes.")
    else:
        print("(not a git repo)")

    # 7) Done
    if rc == 0:
        print("[7/7] Success: tests pass. Patch ready.")
    else:
        print("[7/7] Failed to produce a passing patch.")
    return rc


# --------------
# CLI entrypoint
# --------------

def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Minimal SWE-Fixer-style runner (Python repos)")
    p.add_argument("--repo", required=True, help="Path to repository root")
    p.add_argument("--issue-file", required=True, help="Path to file containing issue text")
    p.add_argument("--test-cmd", default="pytest -q", help="Shell command to run tests (default: pytest -q)")
    p.add_argument("--include", nargs="*", default=["*.py"], help="Glob patterns to include (default: *.py)")
    p.add_argument("--bm25-k", type=int, default=30, help="Number of BM25 candidates (default: 30)")
    p.add_argument("--retriever-url", default=os.environ.get("RETRIEVER_URL"), help="HTTP URL for retriever model")
    p.add_argument("--editor-url", default=os.environ.get("EDITOR_URL"), help="HTTP URL for editor model")
    p.add_argument("--api-key", default=os.environ.get("MODEL_API_KEY"), help="Optional Bearer token for both calls")
    p.add_argument("--max-attempts", type=int, default=5, help="Max attempts with resampling (default: 5)")
    p.add_argument("--commit-on-success", action="store_true", help="git add/commit when tests pass")
    p.add_argument("--dry-run", action="store_true", help="Stop after printing retriever input JSON")

    args = p.parse_args(argv)

    repo = Path(args.repo).resolve()
    if not repo.exists():
        print(f"[error] repo not found: {repo}")
        return 2

    issue_text = load_issue_text(Path(args.issue_file))
    readme = load_readme(repo)

    cfg = RunnerConfig(
        repo=repo,
        issue_text=issue_text,
        readme=readme,
        include_patterns=args.include,
        bm25_k=args.bm25_k,
        test_cmd=args.test_cmd,
        retriever_url=args.retriever_url,
        editor_url=args.editor_url,
        api_key=args.api_key,
        max_attempts=args.max_attempts,
        dry_run=args.dry_run,
        commit_on_success=args.commit_on_success,
    )

    return run_pipeline(cfg)


if __name__ == "__main__":
    sys.exit(main())
