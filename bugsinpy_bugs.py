import os
import jsonlines
import difflib
import hashlib
from typing import Any

from io_utils import get_file_content
from github_utils import download_codebase, save_issues_and_comments_before_commit, get_commit_date_posix
from patch_output import PatchSuggestions
from offline_pipeline import offline_pipeline_file, OUTPUT_FORMAT, USER_PROMPT_V7
from process_layer import LLM
from log import log_and_print 


def _apply_patch_with_stats(patch: PatchSuggestions, buggy_file_content: str) -> tuple[str, dict[str, Any]]:
    """
    Internal helper that applies a PatchSuggestions object and also returns per-edit application stats.
    """
    newline = "\r\n" if "\r\n" in buggy_file_content else "\n"
    original_had_trailing_newline = buggy_file_content.endswith(("\n", "\r\n"))

    lines = buggy_file_content.splitlines(keepends=True)

    edits_sorted = sorted(
        patch.edits,
        key=lambda e: (max(1, int(getattr(e, "line_start_for_editing", 1))), max(1, int(getattr(e, "line_end_for_editing", 1)))),
        reverse=True,
    )

    stats: dict[str, Any] = {
        "num_edits_suggested": len(patch.edits),
        "num_edits_applied": 0,
        "num_edits_skipped": 0,
        "num_edits_failed": 0,
        "edit_results": [],
    }

    def _coerce_newlines(text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if newline != "\n":
            text = text.replace("\n", newline)
        return text

    for edit in edits_sorted:
        try:
            start = int(getattr(edit, "line_start_for_editing", 1) or 1)
            end = int(getattr(edit, "line_end_for_editing", start) or start)
            if start < 1:
                start = 1
            if end < 1:
                end = 1
            if end < start:
                start, end = end, start

            # Convert to 0-based indices; end is inclusive in the edit model.
            start_idx = start - 1
            end_idx = min(len(lines), end)

            region_text = "".join(lines[start_idx:end_idx])
            expected = _coerce_newlines(getattr(edit, "exact_existing_buggy_snippet", "") or "")
            replacement = _coerce_newlines(getattr(edit, "correct_replacement_snippet", "") or "")

            applied = False
            method = None

            # Preferred: replace expected snippet within the specified region.
            if expected and expected in region_text:
                new_region = region_text.replace(expected, replacement, 1)
                applied = True
                method = "region_snippet_replace"
            # Next: if the entire region matches expected (after trimming only trailing newlines), replace region.
            elif expected and region_text.rstrip("\r\n") == expected.rstrip("\r\n"):
                new_region = replacement
                applied = True
                method = "region_whole_replace"
            # Fallback: replace the entire region by coordinates.
            else:
                new_region = replacement
                applied = True
                method = "region_coordinate_replace"

            # Preserve region's trailing newline presence to avoid accidental concatenation
            if region_text.endswith(newline) and new_region and not new_region.endswith(newline):
                new_region = new_region + newline
            if not region_text.endswith(newline) and new_region.endswith(newline) and end_idx == len(lines) and not original_had_trailing_newline:
                # If original file had no trailing newline, avoid adding one via last-region replacement.
                new_region = new_region[: -len(newline)]

            new_region_lines = new_region.splitlines(keepends=True)

            lines[start_idx:end_idx] = new_region_lines

            stats["num_edits_applied"] += 1
            stats["edit_results"].append(
                {
                    "category": getattr(edit, "category", None),
                    "confidence": getattr(edit, "confidence", None),
                    "line_start_for_editing": start,
                    "line_end_for_editing": end,
                    "applied": True,
                    "method": method,
                }
            )
        except Exception as ex:
            stats["num_edits_failed"] += 1
            stats["edit_results"].append(
                {
                    "category": getattr(edit, "category", None),
                    "confidence": getattr(edit, "confidence", None),
                    "line_start_for_editing": getattr(edit, "line_start_for_editing", None),
                    "line_end_for_editing": getattr(edit, "line_end_for_editing", None),
                    "applied": False,
                    "error": str(ex),
                }
            )

    out = "".join(lines)
    # Preserve original trailing newline if present
    if original_had_trailing_newline and not out.endswith(("\n", "\r\n")):
        out += newline

    return out, stats


def extract_bugsinpy():
    projects = {}
    with jsonlines.open("bugsinpy_bugs.jsonl") as reader:
        for bug in reader:
            # log_and_print(f"----------> {bug}")
            if bug["project"] not in projects.keys():
                projects[bug["project"]] = []
            projects[bug["project"]].append({"url": bug["url"], "id": bug["id"], "bug_commit": bug["bug_commit"], "fix_commit": bug["fix_commit"], "file_path": bug["file_path"]})
    return projects


def apply_patch(patch: PatchSuggestions, buggy_file_content: str) -> str:
    """
    Apply the generated edits to the file content to get the full generated file
    
    :param patch: LLM response object of the edits to be made
    :type patch: PatchSuggestions
    :param buggy_file_content: full file content before repair
    :type buggy_file_content: str
    :return: generated fixed file
    :rtype: str
    """
    generated, _ = _apply_patch_with_stats(patch, buggy_file_content)
    return generated


def compare(fixed_file_content: str, patch: PatchSuggestions, buggy_file_content: str, project_name: str, bug_id: int) -> dict[str, Any]:
    """
    Compare the actual real world fix with generated fix and recording their results
    
    :param fixed_file_content: real world file content after fix
    :type fixed_file_content: str
    :param patch: LLM response object of the edits to be made to the buggy file
    :type patch: PatchSuggestions
    :param buggy_file_content: full file content before repair
    :type buggy_file_content: str
    :return: key value pairs of metrics collected for this specific bug
    :rtype: dict[str, Any]
    """

    def _sha256(s: str) -> str:
        return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()

    def _line_diff_stats(a: str, b: str) -> dict[str, int]:
        a_lines = a.splitlines()
        b_lines = b.splitlines()
        sm = difflib.SequenceMatcher(a=a_lines, b=b_lines)
        additions = deletions = replaces = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "insert":
                additions += (j2 - j1)
            elif tag == "delete":
                deletions += (i2 - i1)
            elif tag == "replace":
                replaces += max(i2 - i1, j2 - j1)
        return {"additions": additions, "deletions": deletions, "replacements": replaces}

    def _unified_diff(a: str, b: str, fromfile: str, tofile: str, max_chars: int = 8000) -> str:
        diff = "\n".join(
            difflib.unified_diff(
                a.splitlines(),
                b.splitlines(),
                fromfile=fromfile,
                tofile=tofile,
                lineterm="",
            )
        )
        if len(diff) > max_chars:
            return diff[:max_chars] + "\n... (diff truncated)"
        return diff

    generated_fix, apply_stats = _apply_patch_with_stats(patch, buggy_file_content)

    similarity = difflib.SequenceMatcher(a=fixed_file_content, b=generated_fix).ratio()

    result: dict[str, Any] = {
        "project": project_name,
        "bug_id": bug_id,
        "file_path_to_edit": getattr(patch, "file_path_to_edit", None),
        "llm": LLM.get_config_jsonschema(),
        "num_edits_suggested": apply_stats.get("num_edits_suggested", len(getattr(patch, "edits", []) or [])),
        "num_edits_applied": apply_stats.get("num_edits_applied", 0),
        "num_edits_failed": apply_stats.get("num_edits_failed", 0),
        "generated_equals_actual": generated_fix == fixed_file_content,
        "buggy_equals_actual": buggy_file_content == fixed_file_content,
        "buggy_equals_generated": buggy_file_content == generated_fix,
        "similarity_generated_vs_actual": similarity,
        "sha256_buggy": _sha256(buggy_file_content),
        "sha256_generated": _sha256(generated_fix),
        "sha256_actual": _sha256(fixed_file_content),
        "diff_buggy_to_actual_stats": _line_diff_stats(buggy_file_content, fixed_file_content),
        "diff_buggy_to_generated_stats": _line_diff_stats(buggy_file_content, generated_fix),
        "diff_generated_to_actual_stats": _line_diff_stats(generated_fix, fixed_file_content),
        "diff_generated_to_actual": _unified_diff(
            generated_fix,
            fixed_file_content,
            fromfile=f"{project_name}-{bug_id}:generated",
            tofile=f"{project_name}-{bug_id}:actual",
        ),
        "edit_results": apply_stats.get("edit_results", []),
        "edits_summary": [
            {
                "category": getattr(e, "category", None),
                "confidence": getattr(e, "confidence", None),
                "line_start_for_editing": getattr(e, "line_start_for_editing", None),
                "line_end_for_editing": getattr(e, "line_end_for_editing", None),
            }
            for e in (getattr(patch, "edits", []) or [])
        ],
    }

    return result


def process_bugsinpy():
    projects_info = extract_bugsinpy()
    for project_name, bugs_list in projects_info.items():
        project_name = project_name.lower()
        
        project_path = "projects/" + project_name
        
        git_url = bugs_list[0].get("url")
        download_codebase(git_url)
        
        for bug in bugs_list:
            bug_commit = bug["bug_commit"]
            file_path = f"{project_path}/{bug["file_path"]}"
            download_codebase(git_url, bug_commit)
            results_path = os.path.join("results", f"{project_name}_results_{get_commit_date_posix(git_url, bug_commit)}_{LLM.get_name()}.jsonl")
            buggy_file_content = get_file_content(file_path)
            issues_filename, comments_filename = save_issues_and_comments_before_commit(git_url, bug_commit, issues_filename=project_name, comments_filename=project_name, include_prs=True)
            resp = offline_pipeline_file(OUTPUT_FORMAT + USER_PROMPT_V7, project_path, "issues/" + issues_filename, file_path, top_k=3)
            
            download_codebase(git_url, bug["fix_commit"])
            fixed_file = get_file_content(file_path)
            result = compare(fixed_file, resp, buggy_file_content, project_name, bug["id"])
            log_and_print(f"################ Results recorded for {project_name}-{bug["id"]} ################")
            log_and_print(result)
            with jsonlines.open(results_path, mode="w") as writer:
                writer.write(result)


if __name__ == "__main__":
    process_bugsinpy()
