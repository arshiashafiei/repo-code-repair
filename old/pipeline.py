from __future__ import annotations
import textwrap
from pathlib import Path
from typing import Dict, List
from .config import RunnerConfig
from .repo_docs import build_repo_docs, filedoc_to_json
from .bm25 import BM25, tokenize
from .prompts import RETRIEVAL_TASK, EDITING_TASK
from .models import call_model, parse_retriever_output, parse_editor_output
from .line_numbers import add_line_numbers
from .patcher import Edit, apply_edits, syntax_check_python, PatchApplicationError
from .git_utils import ensure_git_repo_exist, git_diff, git_commit_all
from .io_utils import read_text
import subprocess


def _build_bm25_corpus(docs_json: List[Dict]) -> List[str]:
    texts = []
    for fd in docs_json:
        parts = [fd.get("file_path", ""), fd.get("module_docstring", "")]
        parts += [c.get("name", "") for c in fd.get("classes", [])]
        for f in fd.get("functions", []):
            parts.append(f.get("name", ""))
            parts.append(f.get("content", ""))
        texts.append("\n".join(parts))
    return texts


def _run_tests(test_cmd: str, cwd: Path) -> int:
    try:
        result = subprocess.run(test_cmd, cwd=str(cwd), shell=True)
        return result.returncode
    except FileNotFoundError:
        return 127


def run_pipeline(cfg: RunnerConfig) -> int:
    # 1) Build file docs
    print("[1/7] Scanning repository and building file docs…")
    docs = build_repo_docs(cfg.repo, cfg.include_patterns)
    docs_json = [filedoc_to_json(fd) for fd in docs]
    if not docs_json:
        print("[error] No file docs found (patterns:", cfg.include_patterns, ")")
        return 2

    # 2) BM25@K
    print(f"[2/7] Computing BM25@{cfg.bm25_k} over file docs…")
    doc_texts = _build_bm25_corpus(docs_json)
    bm25 = BM25([tokenize(t) for t in doc_texts])
    idxs = bm25.top_k(cfg.issue_text, cfg.bm25_k)
    top_docs_json = [docs_json[i] for i in idxs]

    # 3) Retriever call
    retr_in = {
        "issue": cfg.issue_text,
        "readme file": cfg.readme,
        "retrieved file documentations": top_docs_json,
        "task": RETRIEVAL_TASK,
    }

    if cfg.dry_run:
        preview = textwrap.shorten(str(retr_in), width=2000, placeholder="…")
        print("\n[DRY RUN] Retriever input JSON preview:\n" + preview)
        return 0

    print("[3/7] Calling retriever model…")
    if not cfg.retriever_url:
        print("[error] --retriever-url is required (or use --dry-run).")
        return 3

    temperature_seq = [0.0] + [0.7] * max(0, cfg.max_attempts - 1)
    files_for_editing: List[str] = []
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
    files_payload: List[Dict] = []
    for rel in files_for_editing:
        p = cfg.repo / rel
        if not p.exists():
            print(f"  [warn] missing file from retriever: {rel}")
            continue
        numbered = add_line_numbers(read_text(p), start=1)
        files_payload.append({"file": rel, "file content": numbered})
        print("       -", rel)
    if not files_payload:
        print("[error] No files available for editor input.")
        return 4

    edit_in = {"issue": cfg.issue_text, "files to be modified": files_payload, "task": EDITING_TASK}

    # 5) Editor call + post-processing loop
    print("[5/7] Calling editor model and validating outputs…")
    if not cfg.editor_url:
        print("[error] --editor-url is required (or use --dry-run).")
        return 3

    original_snapshots: dict[Path, str] = {}
    rc = 1
    for attempt, temp in enumerate(temperature_seq, start=1):
        try:
            resp = call_model(cfg.editor_url, edit_in, cfg.api_key, temperature=temp)
            reasoning, edit_items = parse_editor_output(resp)
            print("[editor] reasoning (truncated):\n" + textwrap.shorten(reasoning, width=500, placeholder="…"))

            edits = [Edit(file=item["file"],
                          original_numbered=item["code snippet to be modified"],
                          edited=item["edited code snippet"]) for item in edit_items]

            for e in edits:
                target = cfg.repo / e.file
                if target.exists() and target not in original_snapshots:
                    original_snapshots[target] = read_text(target)

            modified = apply_edits(cfg.repo, edits)
            if not syntax_check_python(modified):
                raise PatchApplicationError("Syntax check failed after applying edits.")

            print("[tests] Running:", cfg.test_cmd)
            exit_code = _run_tests(cfg.test_cmd, cfg.repo)
            if exit_code != 0:
                raise PatchApplicationError(f"Tests failed with exit code {exit_code}.")

            rc = 0
            break
        except Exception as ex:
            print(f"[editor] attempt {attempt} failed: {ex}")
            for path, text in original_snapshots.items():
                if path.exists():
                    path.write_text(text, encoding="utf-8")
            if attempt >= cfg.max_attempts:
                rc = 5
                break

    # 6) Emit diff and optionally commit
    print("[6/7] Git diff of working tree:")
    if ensure_git_repo_exist(cfg.repo):
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
