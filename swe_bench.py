from __future__ import annotations

import os
import difflib
import jsonlines
from datasets import load_dataset
from dataclasses import dataclass
from difflib import unified_diff
from typing import List, Optional, Tuple

from github_utils import download_codebase, get_commit_date_posix, save_issues_and_comments_before_commit
from offline_pipeline import offline_pipeline_file, offline_pipeline_issue
from patch_output import PatchSnippet, PatchSuggestions
from process_layer import LLM
from prompts import OUTPUT_FORMAT, USER_PROMPT_ISSUES, USER_PROMPT_V7
from io_utils import get_file_content
from log import log_and_print
from bugsinpy_bugs import apply_patch
# from summarize_discussions import summarize_all_discussions 


@dataclass(frozen=True)
class _ResolvedEdit:
    """Internal: edit with resolved 0-based [start, end) line slice."""
    start: int
    end: int
    snippet: "PatchSnippet"


def _split_lines_keepends(s: str) -> List[str]:
    return s.splitlines(keepends=True)


def _ensure_trailing_newline_like(original: str, replacement: str) -> str:
    if original.endswith("\n") and not replacement.endswith("\n"):
        return replacement + "\n"
    return replacement


def _find_unique_substring(haystack: str, needle: str) -> Tuple[int, int]:
    """Return (start_idx, end_idx) of a unique occurrence of needle in haystack."""
    if not needle:
        raise ValueError("exact_existing_buggy_snippet is empty; cannot locate edit.")
    
    first = haystack.find(needle)
    if first != -1:
        second = haystack.find(needle, first + 1)
        if second != -1:
            raise ValueError("exact_existing_buggy_snippet occurs multiple times; ambiguous.")
        return first, first + len(needle)
    
    def normalize(s: str) -> str:
        lines = s.splitlines(keepends=True)
        return "".join(line.lstrip() for line in lines)
    
    normalized_haystack = normalize(haystack)
    normalized_needle = normalize(needle)
    
    first = normalized_haystack.find(normalized_needle)
    if first != -1:
        hay_lines = haystack.splitlines(keepends=True)
        norm_hay_lines = [line.lstrip() for line in hay_lines]
        
        char_count = 0
        start_line = 0
        for i, line in enumerate(norm_hay_lines):
            if char_count + len(line) > first:
                start_line = i
                break
            char_count += len(line)
        
        needle_lines = needle.strip().splitlines()
        for i in range(len(hay_lines)):
            match = True
            for j, needle_line in enumerate(needle_lines):
                if i + j >= len(hay_lines):
                    match = False
                    break
                if hay_lines[i + j].strip() != needle_line.strip():
                    match = False
                    break
            if match:
                start_pos = sum(len(hay_lines[k]) for k in range(i))
                end_pos = sum(len(hay_lines[k]) for k in range(i + len(needle_lines)))
                return start_pos, end_pos
    
    from difflib import SequenceMatcher
    hay_lines = haystack.splitlines(keepends=True)
    needle_lines = needle.strip().splitlines()
    
    best_ratio = 0.0
    best_start = -1
    best_end = -1
    
    for i in range(len(hay_lines) - len(needle_lines) + 1):
        window = "".join(hay_lines[i:i + len(needle_lines)])
        ratio = SequenceMatcher(None, window.strip(), needle.strip()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_start = i
            best_end = i + len(needle_lines)
    
    if best_ratio >= 0.7 and best_start >= 0:
        log_and_print(f"[FUZZY MATCH] Found snippet with {best_ratio:.1%} similarity at lines {best_start+1}-{best_end}")
        start_pos = sum(len(hay_lines[k]) for k in range(best_start))
        end_pos = sum(len(hay_lines[k]) for k in range(best_end))
        return start_pos, end_pos
    
    log_and_print(f"[DEBUG] Could not find snippet in file. Best match ratio: {best_ratio:.1%}")
    log_and_print(f"[DEBUG] Looking for:\n{needle[:200]}...")
    log_and_print(f"[DEBUG] File has {len(hay_lines)} lines. First 500 chars:\n{haystack[:500]}...")
    
    raise ValueError("exact_existing_buggy_snippet not found in file content.")


def _char_span_to_line_slice(text: str, start: int, end: int) -> Tuple[int, int]:
    """
    Convert a character span to a (start_line, end_line_exclusive) 0-based slice.
    Line boundaries are computed on '\n'.
    """
    start_line = text.count("\n", 0, start)
    end_line = text.count("\n", 0, end)
    
    if end > 0 and end <= len(text) and (end == len(text) or text[end - 1] != "\n"):
        end_line += 1
    return start_line, max(end_line, start_line)


def _resolve_edits(
    patch: "PatchSuggestions",
    original_content: str,
    *,
    min_confidence: float = -0.1,
    strict_line_range_match: bool = False,
) -> List[_ResolvedEdit]:
    """
    Resolve each PatchSnippet to a concrete 0-based line slice [start, end).
    If the provided line slice doesn't match, fall back to locating the snippet
    uniquely in the file (unless strict_line_range_match=True).
    """
    lines = _split_lines_keepends(original_content)
    resolved: List[_ResolvedEdit] = []

    for e in patch.edits:
        if e.confidence < min_confidence:
            continue

        start = max(0, e.line_start_for_editing - 1)
        end_excl = max(start, e.line_end_for_editing)

        in_bounds = start <= len(lines) and end_excl <= len(lines)
        slice_text = "".join(lines[start:end_excl]) if in_bounds else ""

        
        range_matches = (slice_text == e.exact_existing_buggy_snippet)
        if not range_matches and slice_text.strip() == e.exact_existing_buggy_snippet.strip():
            range_matches = not strict_line_range_match

        if range_matches and in_bounds:
            resolved.append(_ResolvedEdit(start=start, end=end_excl, snippet=e))
            continue

        if strict_line_range_match:
            raise ValueError(
                f"Line range {e.line_start_for_editing}-{e.line_end_for_editing} does not "
                f"match exact_existing_buggy_snippet for {patch.file_path_to_edit}."
            )

        c0, c1 = _find_unique_substring(original_content, e.exact_existing_buggy_snippet)
        s_line, e_line_excl = _char_span_to_line_slice(original_content, c0, c1)
        resolved.append(_ResolvedEdit(start=s_line, end=e_line_excl, snippet=e))

    resolved.sort(key=lambda r: (r.start, r.end), reverse=True)

    for i in range(len(resolved) - 1):
        a = resolved[i]
        b = resolved[i + 1]
        if b.end > a.start:
            raise ValueError(
                f"Overlapping edits detected: [{b.start},{b.end}) overlaps [{a.start},{a.end})."
            )

    return resolved


def apply_patch_suggestions_and_diff(
    patch: "PatchSuggestions",
    original_file_content: str,
    *,
    context_lines: int = 3,
    min_confidence: float = -0.1,
    strict_line_range_match: bool = False,
    fromfile: Optional[str] = None,
    tofile: Optional[str] = None,
) -> str:
    """
    Inputs:
      1) patch: PatchSuggestions (for a single file)
      2) original_file_content: content from the repo at the SWE-bench(-Lite) base commit

    Output:
      git-style unified diff between original and patched content.
    """
    path = patch.file_path_to_edit
    a_name = fromfile or f"a/{path}"
    b_name = tofile or f"b/{path}"

    resolved = _resolve_edits(
        patch,
        original_file_content,
        min_confidence=min_confidence,
        strict_line_range_match=strict_line_range_match,
    )

    lines = _split_lines_keepends(original_file_content)

    for r in resolved:
        old_block = "".join(lines[r.start:r.end])
        expected = r.snippet.exact_existing_buggy_snippet

        if expected and (old_block != expected):
            if expected in old_block:
                new_block = old_block.replace(
                    expected,
                    _ensure_trailing_newline_like(expected, r.snippet.correct_replacement_snippet),
                    1,
                )
                lines[r.start:r.end] = _split_lines_keepends(new_block)
                continue
            raise ValueError(
                f"Resolved edit block does not match exact_existing_buggy_snippet for {path}.\n"
                f"Edit category={r.snippet.category}, confidence={r.snippet.confidence}"
            )

        replacement = _ensure_trailing_newline_like(old_block, r.snippet.correct_replacement_snippet)
        lines[r.start:r.end] = _split_lines_keepends(replacement)

    patched_content = "".join(lines)

    diff_lines = list(
        unified_diff(
            _split_lines_keepends(original_file_content),
            _split_lines_keepends(patched_content),
            fromfile=a_name,
            tofile=b_name,
            n=context_lines,
            lineterm="",
            )
    )

    if not diff_lines:
        return f"diff --git {a_name} {b_name}\n"

    return "diff --git {a} {b}\n{rest}\n".format(
        a=a_name, b=b_name, rest="\n".join(diff_lines).rstrip("\n")
    )


def get_patch(response: PatchSuggestions, local_file_path: str):
    
    if not os.path.exists(local_file_path):
        log_and_print(f"[ERROR] File not found: {local_file_path}")
        log_and_print(f"[DEBUG] Model suggested path: {response.file_path_to_edit}")
        
        project_dir = os.path.dirname(local_file_path) or "."
        if os.path.exists(project_dir):
            similar_files = [f for f in os.listdir(project_dir) if f.endswith('.py')]
            log_and_print(f"[DEBUG] Python files in {project_dir}: {similar_files[:10]}")
        raise FileNotFoundError(f"Model suggested file path does not exist: {local_file_path}")

    local_file_content = get_file_content(local_file_path)
    if not local_file_content:
        raise ValueError(f"File is empty or could not be read: {local_file_path}")
    
    log_and_print(f"[DEBUG] Attempting to patch file: {local_file_path} ({len(local_file_content)} chars, {len(local_file_content.splitlines())} lines)")
    
    model_patch = apply_patch_suggestions_and_diff(response, local_file_content)

    local_file_content = local_file_content.splitlines(keepends=True)
    model_patch = model_patch.splitlines(keepends=True)
    

    diff = difflib.unified_diff(
        local_file_content, model_patch,
        fromfile=f"a/{local_file_path}",
        tofile=f"b/{local_file_path}"
    )
    diff = "".join(diff)
    diff = f"diff --git a/{local_file_path} b/{local_file_path}\n{diff}"
    log_and_print(diff)

    return diff


def run_swebench():
    local_file_path = "codebase/manage.py"
    # local_file_response = offline_pipeline_file(OUTPUT_FORMAT + USER_PROMPT_ISSUES, "codebase", "issues/local_issues_summaries.jsonl", local_file_path, top_k=5)
    # diff = apply_patch_suggestions_and_diff(local_file_response, get_file_content(local_file_path))

    swebench_lite_dev = load_dataset('princeton-nlp/SWE-bench_Lite', split='dev')


    results = []
    for task in swebench_lite_dev:
        # clone fresh repo at base_commit
        # repo = task["repo"]
        # commit = task["base_commit"]
        instance_id = task["instance_id"]
        model_name = LLM.model_name if hasattr(LLM, "model_name") else getattr(LLM, "model", None)

        f = False
        results_path = os.path.join("results", f"swe_bench_lite_results.jsonl")
        with jsonlines.open(results_path, mode="r") as reader:
            for bench in reader:
                if bench["instance_id"] == instance_id and bench["model_name_or_path"] == model_name:
                    f = True

        if f:
            log_and_print(f"XXXXXXXXXXXXXXXXXXXXX Skipping {instance_id} By {model_name} XXXXXXXXXXXXXXXXXXXXX")
            continue

        project_name = task["repo"]
        
        project_path = "projects/" + project_name.split("/")[1]
        
        git_url = f"https://github.com/{task["repo"]}"
        download_codebase(git_url)
        
      
        bug_commit = task["base_commit"]
        download_codebase(git_url, bug_commit)
        issues_filename, comments_filename = save_issues_and_comments_before_commit(git_url, bug_commit, issues_filename=project_name, comments_filename=project_name, include_prs=True, max_workers=4)
        
        # file_path = f"{project_path}/{task["file_path"]}"
        # resp = offline_pipeline_file(OUTPUT_FORMAT + USER_PROMPT_V7, project_path, "issues/" + issues_filename, file_path, top_k=3)
        # summarize_all_discussions(
        #     issues_path="issues/" + issues_filename,
        #     comments_path="comments/" + comments_filename,
        #     output_path="summarized_issues/" + issues_filename,
        #     max_workers=2
        # )
        
        resp = offline_pipeline_issue(OUTPUT_FORMAT + USER_PROMPT_ISSUES, project_path, "issues/" + issues_filename, task["problem_statement"], top_k=3)
        
        patch = get_patch(resp, resp.file_path_to_edit)
        results.append({"instance_id": task["instance_id"], "model_name_or_path": model_name, "model_patch": patch})
        
        log_and_print(f"################ Results recorded for {project_name}-{task["instance_id"]} ################")
        # log_and_print(LLM.model_dump())
        # log_and_print(LLM.get_output_jsonschema())
        log_and_print(f"################ GIT DIFF VIEW ################")
        log_and_print(patch)

        with jsonlines.open(results_path, mode="a") as writer:
            writer.write(results[-1])
            # writer.write_all(results)


if __name__ == "__main__":
    run_swebench()
