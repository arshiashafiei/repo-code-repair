from __future__ import annotations

import os
import re
import math
import difflib
import time
import jsonlines
from collections import Counter
from datasets import load_dataset
from dataclasses import dataclass
from difflib import unified_diff
from typing import Dict, List, Optional, Set, Tuple

from .github_utils import download_codebase, get_commit_date_posix, save_issues_and_comments_before_commit
from .offline_pipeline import offline_pipeline_file, offline_pipeline_issue
from .patch_output import PatchSnippet, PatchSuggestions, DiffViewEdits, FilesToEdit
from .process_layer import LLM
from .prompts import OUTPUT_FORMAT, USER_PROMPT_COT_ISSUES, USER_PROMPT_ISSUES, USER_PROMPT_MULTIFILE_COT, USER_PROMPT_MULTIFILE_ZERO_SHOT, USER_PROMPT_V7, OUTPUT_FORMAT_Diffview
from .io_utils import get_file_content
from .log import log_and_print
from .bugsinpy_bugs import apply_patch
from .apply_patch import validate_patch, sanitize_patch

# from summarize_discussions import summarize_all_discussions 


def _normalize_patch(patch: str) -> str:
    """Normalize a unified-diff patch for fair comparison.

    Strips leading/trailing whitespace, removes 'index …' lines,
    timestamp tails from ---/+++ headers, and trailing whitespace per line.
    """
    if not patch:
        return ""
    lines: List[str] = []
    for raw_line in patch.splitlines():
        line = raw_line.rstrip()
        # drop git index lines ("index abc123..def456 100644")
        if line.startswith("index "):
            continue
        # strip timestamps from --- / +++ headers
        if line.startswith("--- ") or line.startswith("+++ "):
            parts = line.split("\t")
            line = parts[0]
        lines.append(line)
    return "\n".join(lines).strip()


# ── Patch structure parsing helpers ──────────────────────────────────────

_HUNK_RE = re.compile(r"^@@\s+-(?P<os>\d+)(?:,(?P<oc>\d+))?\s+\+(?P<ns>\d+)(?:,(?P<nc>\d+))?\s+@@")


def _extract_files_from_patch(patch: str) -> Set[str]:
    """Return the set of file paths touched by a unified diff."""
    files: Set[str] = set()
    for line in patch.splitlines():
        if line.startswith("--- a/"):
            files.add(line[6:].split("\t")[0])
        elif line.startswith("+++ b/"):
            files.add(line[6:].split("\t")[0])
    return files


def _extract_hunks(patch: str) -> List[Tuple[int, int]]:
    """Return list of (start_line, line_count) for every hunk in the *old* file."""
    hunks: List[Tuple[int, int]] = []
    for line in patch.splitlines():
        m = _HUNK_RE.match(line)
        if m:
            start = int(m.group("os"))
            count = int(m.group("oc")) if m.group("oc") is not None else 1
            hunks.append((start, count))
    return hunks


def _count_diff_lines(patch: str) -> Tuple[int, int]:
    """Return (added_lines, removed_lines) from a unified diff."""
    added = removed = 0
    in_hunk = False
    for line in patch.splitlines():
        if _HUNK_RE.match(line):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed


def _changed_lines_only(patch: str) -> List[str]:
    """Extract only the added/removed source lines (without +/- prefix)."""
    lines: List[str] = []
    in_hunk = False
    for line in patch.splitlines():
        if _HUNK_RE.match(line):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            lines.append(line[1:])
    return lines


def _hunk_overlap(hunks_a: List[Tuple[int, int]], hunks_b: List[Tuple[int, int]]) -> float:
    """Compute Jaccard-style overlap of old-file line ranges covered by hunks."""
    def _to_set(hunks: List[Tuple[int, int]]) -> Set[int]:
        s: Set[int] = set()
        for start, count in hunks:
            s.update(range(start, start + count))
        return s
    sa, sb = _to_set(hunks_a), _to_set(hunks_b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _bleu4(candidate_tokens: List[str], reference_tokens: List[str]) -> float:
    """Compute sentence-level BLEU-4 with add-1 smoothing (no external deps)."""
    if not candidate_tokens or not reference_tokens:
        return 0.0

    brevity = min(1.0, math.exp(1 - len(reference_tokens) / len(candidate_tokens))) \
        if len(candidate_tokens) > 0 else 0.0

    log_avg = 0.0
    for n in range(1, 5):
        cand_ngrams: Counter = Counter()
        ref_ngrams: Counter = Counter()
        for i in range(len(candidate_tokens) - n + 1):
            cand_ngrams[tuple(candidate_tokens[i:i + n])] += 1
        for i in range(len(reference_tokens) - n + 1):
            ref_ngrams[tuple(reference_tokens[i:i + n])] += 1
        clipped = sum(min(c, ref_ngrams[ng]) for ng, c in cand_ngrams.items())
        total = max(len(candidate_tokens) - n + 1, 1)
        # add-1 smoothing
        precision = (clipped + 1) / (total + 1)
        log_avg += math.log(precision) / 4.0

    return brevity * math.exp(log_avg)


# ── Main metrics function ───────────────────────────────────────────────

def compute_patch_metrics(
    model_patch: str,
    gold_patch: str,
    *,
    attempt_number: int = 0,
    latency_s: float = 0.0,
    patch_applicable: bool = False,
) -> dict:
    """Compute a comprehensive set of patch-generation metrics.

    Patch-comparison metrics
    ~~~~~~~~~~~~~~~~~~~~~~~~
    * **exact_match (EM)** – 1 if normalised patches are identical, else 0.
    * **edit_similarity (ES)** – ``SequenceMatcher.ratio()`` on normalised patches.
    * **bleu4** – Sentence-level BLEU-4 on the changed source lines (tokenised by whitespace).

    Localization metrics
    ~~~~~~~~~~~~~~~~~~~~
    * **file_match (FM)** – Jaccard similarity over the set of files touched.
    * **hunk_overlap** – Jaccard overlap of old-file line ranges covered by hunks.

    Diff-structural metrics
    ~~~~~~~~~~~~~~~~~~~~~~~
    * **hunk_count_delta** – ``|model_hunks - gold_hunks|``.
    * **model_added / model_removed** – Added/removed line counts in the model patch.
    * **gold_added / gold_removed** – Added/removed line counts in the gold patch.
    * **lines_changed_ratio** – ``model_total_changed / gold_total_changed`` (0 if gold has none).

    Operational metrics (pass-through)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    * **patch_applicable** – 1 if the patch passed ``git apply --check``.
    * **attempt_number** – Which retry succeeded (1/2/3, or 0 = all failed).
    * **latency_s** – Wall-clock seconds for the full attempt sequence.
    """
    norm_model = _normalize_patch(model_patch)
    norm_gold = _normalize_patch(gold_patch)

    # EM / ES
    em = int(norm_model == norm_gold)
    es = difflib.SequenceMatcher(None, norm_model, norm_gold).ratio()

    # File match (Jaccard)
    model_files = _extract_files_from_patch(model_patch)
    gold_files = _extract_files_from_patch(gold_patch)
    if model_files or gold_files:
        fm = len(model_files & gold_files) / len(model_files | gold_files)
    else:
        fm = 1.0 if (not model_files and not gold_files) else 0.0

    # Hunk overlap
    model_hunks = _extract_hunks(model_patch)
    gold_hunks = _extract_hunks(gold_patch)
    ho = _hunk_overlap(model_hunks, gold_hunks)

    # BLEU-4 on changed lines
    model_tokens = " ".join(_changed_lines_only(model_patch)).split()
    gold_tokens = " ".join(_changed_lines_only(gold_patch)).split()
    bleu = _bleu4(model_tokens, gold_tokens)

    # Line counts
    m_add, m_rem = _count_diff_lines(model_patch)
    g_add, g_rem = _count_diff_lines(gold_patch)
    gold_total = g_add + g_rem
    model_total = m_add + m_rem
    lcr = (model_total / gold_total) if gold_total > 0 else 0.0

    # Hunk count delta
    hcd = abs(len(model_hunks) - len(gold_hunks))

    return {
        # patch comparison
        "exact_match": em,
        "edit_similarity": round(es, 4),
        "bleu4": round(bleu, 4),
        # localization
        "file_match": round(fm, 4),
        "hunk_overlap": round(ho, 4),
        # diff-structural
        "hunk_count_delta": hcd,
        "model_added": m_add,
        "model_removed": m_rem,
        "gold_added": g_add,
        "gold_removed": g_rem,
        "lines_changed_ratio": round(lcr, 4),
        # operational
        "patch_applicable": int(patch_applicable),
        "attempt_number": attempt_number,
        "latency_s": round(latency_s, 2),
    }


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
    model_suggested_path = response.file_path_to_edit

    log_and_print(f">>>>>>>> Local file content:\n{local_file_content}\n<<<<<<<<<<<")
    log_and_print(f">>>>>>>> model patch content:\n{local_file_content}\n<<<<<<<<<<")
    log_and_print(f"Model suggested path: {response.file_path_to_edit}")
        

    diff = difflib.unified_diff(
        local_file_content, model_patch,
        fromfile=f"a/{model_suggested_path}",
        tofile=f"b/{model_suggested_path}"
    )
    diff = "".join(diff)
    diff = f"diff --git a/{model_suggested_path} b/{model_suggested_path}\n{diff}"

    log_and_print(f"#####@@@@@@##### DIFF VIEW #####@@@@@@#####\n{diff}")

    return diff


def run_swebench():
    local_file_path = "codebase/manage.py"
    # local_file_response = offline_pipeline_file(OUTPUT_FORMAT + USER_PROMPT_ISSUES, "codebase", "issues/local_issues_summaries.jsonl", local_file_path, top_k=5)
    # diff = apply_patch_suggestions_and_diff(local_file_response, get_file_content(local_file_path))

    swebench_lite_dev = load_dataset('princeton-nlp/SWE-bench_Lite', split='dev')
    swe_bench_verified_mini = load_dataset('MariusHobbhahn/swe-bench-verified-mini', split='test')

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
        t_start = time.time()
        attempt_number = 0
        patch_applicable = False

        resp = offline_pipeline_issue(USER_PROMPT_MULTIFILE_COT, \
                    project_path, "issues/" + issues_filename, f"{task["problem_statement"]}\nhint text from discussion: {task["hints_text"]}", top_k=3, \
                    output_format=DiffViewEdits, output_prompt=OUTPUT_FORMAT_Diffview, \
                    file_selection=True)

        # resp = offline_pipeline_issue(USER_PROMPT_MULTIFILE_ZERO_SHOT, project_path, "issues/" + issues_filename, task["problem_statement"], top_k=3, output_format=DiffViewEdits, output_prompt=OUTPUT_FORMAT_Diffview)
        
        # patch = get_patch(resp, project_path + '/' + resp.file_path_to_edit)

        try:
            assert resp.patch, "Model did not return a patch."
            sanitized_patch_1 = sanitize_patch(resp.patch, project_path)
            validate_patch(sanitized_patch_1, project_path)
            attempt_number = 1
            patch_applicable = True
            results.append({"instance_id": task["instance_id"], "model_name_or_path": model_name, "model_patch": sanitized_patch_1})
        except Exception as e:
            log_and_print(f"Initial patch failed validation for {instance_id} by {model_name} with error: {e}")
            LLM.temperature = 0.2
            LLM.top_p = 0.95
            resp2 = offline_pipeline_issue(USER_PROMPT_MULTIFILE_COT, \
                        project_path, "issues/" + issues_filename, task["problem_statement"], top_k=3, \
                        output_format=DiffViewEdits, output_prompt=OUTPUT_FORMAT_Diffview + f"\nThe previous patch failed `git apply --check` with:\n{str(e)}\nProduce a correct patch.\n", \
                        file_selection=True)
            try:
                sanitized_patch_2 = sanitize_patch(resp2.patch, project_path)
                validate_patch(sanitized_patch_2, project_path)
                attempt_number = 2
                patch_applicable = True
                results.append({"instance_id": task["instance_id"], "model_name_or_path": model_name, "model_patch": sanitized_patch_2})
            except Exception as e:
                log_and_print(f"Second patch attempt also failed validation for {instance_id} by {model_name} with error: {e}")
                LLM.temperature = 0.8
                resp3 = offline_pipeline_issue(USER_PROMPT_MULTIFILE_COT, \
                            project_path, "issues/" + issues_filename, task["problem_statement"], top_k=3, \
                            output_format=DiffViewEdits, output_prompt=OUTPUT_FORMAT_Diffview + f"\nThe previous patch failed `git apply --check` with:\n{str(e)}\nProduce a corrected patch ONLY. Do not include explanations. Do not change the intent of the edit.\n", \
                            file_selection=True)
                try:
                    sanitized_patch_3 = sanitize_patch(resp3.patch, project_path)
                    validate_patch(sanitized_patch_3, project_path)
                    attempt_number = 3
                    patch_applicable = True
                    results.append({"instance_id": task["instance_id"], "model_name_or_path": model_name, "model_patch": sanitized_patch_3})
                except Exception as e:
                    log_and_print(f"Third patch attempt also failed validation for {instance_id} by {model_name} with error: {e}")
                    results.append({"instance_id": task["instance_id"], "model_name_or_path": model_name, "model_patch": ""})

        latency_s = time.time() - t_start - 2


        # diff = apply_patch_and_get_diff(resp, project_path + '/' + resp.file_path_to_edit)
        
        # log_and_print(LLM.model_dump())
        log_and_print(LLM.get_output_jsonschema())

        # ── Compute all metrics against the gold patch ──
        gold_patch = task.get("patch", "")
        metrics = compute_patch_metrics(
            results[-1]["model_patch"],
            gold_patch,
            attempt_number=attempt_number,
            latency_s=latency_s,
            patch_applicable=patch_applicable,
        )
        results[-1].update(metrics)
        log_and_print(
            f"[METRICS] {instance_id}  "
            f"EM={metrics['exact_match']}  ES={metrics['edit_similarity']:.4f}  "
            f"BLEU4={metrics['bleu4']:.4f}  FM={metrics['file_match']:.4f}  "
            f"HO={metrics['hunk_overlap']:.4f}  HCD={metrics['hunk_count_delta']}  "
            f"LCR={metrics['lines_changed_ratio']:.4f}  "
            f"Applicable={metrics['patch_applicable']}  "
            f"Attempt={metrics['attempt_number']}  "
            f"Latency={metrics['latency_s']:.2f}s"
        )

        with jsonlines.open(results_path, mode="a") as writer:
            writer.write(results[-1])
            log_and_print(f"################ Results recorded for {project_name}-{task["instance_id"]} ################")
            # writer.write_all(results)

        # ── Persist metrics to a dedicated file ──
        metrics_path = os.path.join("results", "swe_bench_lite_metrics.jsonl")
        with jsonlines.open(metrics_path, mode="a") as mw:
            mw.write({
                "instance_id": instance_id,
                "model_name_or_path": model_name,
                **metrics,
            })


if __name__ == "__main__":
    run_swebench()
