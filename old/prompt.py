# prompts.py

from __future__ import annotations
from typing import List, Dict, Any, Optional
from pathlib import Path
import json

from file_doc import build_python_skeleton


BM25_RETRIEVAL_SYS_PROMPT = None

BM25_RETRIEVAL_TASK_NO_REASONING = (
    "In this task, you will be provided with a software development issue from a real-world "
    "GitHub repository, along with the repository's README file and a set of preliminarily "
    "retrieved files (documentation). Your objective is to carefully analyze the issue in the "
    "context of the provided files and identify the most relevant files that are likely candidates "
    "for modification to resolve the issue."
)

BM25_RETRIEVAL_ORACLE_FILE_OUTPUT_CONTROL_NO_REASONING = {
    "files for editing": {"type": "array", "items": {"type": "string"}}
}


def _read_text_file(path: Optional[str | Path]) -> str:
    """Read a UTF-8 text file safely; return '' on any error or None."""
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _make_doc_for_non_python(path: str | Path) -> Dict[str, Any]:
    """Placeholder skeleton for non-Python files (swap with Tree-sitter later if desired)."""
    return {
        "file_path": str(path),
        "module_docstring": "",
        "classes": [],
        "functions": [],
    }


def generate_retrieval_prompt_from_paths(
    file_paths: List[str],
    readme_path: Optional[str],
    issue_text: str,
    *,
    top_k: Optional[int] = None,
    max_files: int = 30,
) -> Dict[str, Any]:
    """
    Build the SWE-Fixer retriever input JSON:
    {
      "issue": "...",
      "readme file": "...",
      "retrieved file documentations": [ ... up to 30 ... ],
      "task": "..."
    }

    - Uses build_python_skeleton(path) for .py files.
    - Non-Python files get an empty placeholder (you can replace with a Tree-sitter-based extractor).
    """
    docs: List[Dict[str, Any]] = []
    for p in list(file_paths)[:max_files]:
        p_str = "codebase/" + str(p)
        if p_str.endswith(".py"):
            try:
                docs.append(build_python_skeleton(p_str))
            except Exception as e:
                # Fall back to an empty doc if AST parse fails
                docs.append({
                    "file_path": p_str,
                    "module_docstring": "",
                    "classes": [],
                    "functions": [],
                    "error": f"{type(e).__name__}: {e}",
                })
        else:
            docs.append(_make_doc_for_non_python(p))

    task = BM25_RETRIEVAL_TASK_NO_REASONING
    if top_k is not None:
        task = task.rstrip() + f" Return the top-{top_k} file paths only."

    prompt_obj = {
        "issue": issue_text,
        "readme file": _read_text_file(readme_path),
        "retrieved file documentations": docs,
        "task": task,
    }
    return prompt_obj


def to_chat_messages_payload(
    prompt_obj: Dict[str, Any],
    *,
    system_prompt: Optional[str] = BM25_RETRIEVAL_SYS_PROMPT,
    output_control_schema: Dict[str, Any] = BM25_RETRIEVAL_ORACLE_FILE_OUTPUT_CONTROL_NO_REASONING,
    max_new_tokens: int = 64,
    temperature: float = 0.0,
) -> Dict[str, Any]:
    """
    Wrap the prompt + output control schema into a chat payload for a chat model.
    The user message concatenates the input JSON and the output-control JSON (as in the paper).
    """
    user_content = (
        json.dumps(prompt_obj, ensure_ascii=False, indent=2)
        + "\n\n"
        + json.dumps(output_control_schema, ensure_ascii=False, indent=2)
    )
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})
    return {
        "messages": messages,
        "max_new_tokens": max_new_tokens,
        "temperature": temperature,
    }

__all__ = [
    "BM25_RETRIEVAL_SYS_PROMPT",
    "BM25_RETRIEVAL_TASK_NO_REASONING",
    "BM25_RETRIEVAL_ORACLE_FILE_OUTPUT_CONTROL_NO_REASONING",
    "generate_retrieval_prompt_from_paths",
    "to_chat_messages_payload",
]


# RETRIEVAL_TASK = (
    # "You are selecting which files must be edited to resolve the issue.\n"
    # "Use ONLY the provided 'retrieved file documentations' (BM25 top-30) and the README.\n"
    # "Return exactly this JSON schema: {\"files for editing\": [\"<path>\", ...]}\n"
    # "Rules:\n"
    # "- Choose only from the candidate files provided.\n"
    # "- Include only paths (strings); no duplicates.\n"
    # "- Prefer the minimal set sufficient to fix the issue.\n"
    # "- Output valid JSON only — no extra keys or explanations.\n"
# )
# 
# EDITING_TASK = (
    # "Generate a code patch that resolves the issue using the provided files (full contents with line numbers).\n"
    # "Return exactly this JSON:\n"
    # "{\n  \"reasoning process\": \"<markdown explanation>\",\n  \"edited code\": [\n    {\n      \"file\": \"<path>\",\n      \"code snippet to be modified\": \"<original snippet WITH line numbers>\",\n      \"edited code snippet\": \"<replacement WITHOUT line numbers>\"\n    }\n  ]\n}\n"
    # "Rules:\n"
    # "- Always include the file path for each change.\n"
    # "- The original snippet must include line numbers so it can be precisely located.\n"
    # "- Do NOT include line numbers in 'edited code snippet'.\n"
    # "- Make minimal, necessary changes; keep code valid.\n"
    # "- Return valid JSON only — no extra keys or commentary outside the JSON.\n"
# )
# 

EDITING_SYS_PROMPT = None


EDITING_LEVEL_TASK_ONLY_FILE_CONTENT_WITH_REASONING = "In this task, you will be provided with a software development issue from a real-world GitHub repository, along with the full content of retrieved code files for modification. You will also receive narrowed code snippets that are likely candidates for modification. Your objective is to carefully analyze and understand the issue in the context of the provided files, explain your reasoning process for addressing it, and identify the exact file paths and original code snippets that require modification. Based on this analysis, you will propose new code snippets to replace the identified ones to effectively resolve the issue."

EDITING_LEVEL_OUTPUT_CONTROL_WITH_REASONING = {  # for training
    "type": "object",
    "properties": {
        "reasoning process": {
            "type": "string",
        },
        "edited code": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                    },
                    "code snippet to be modified": {
                        "type": "string",
                    },
                    "edited code snippet": {
                        "type": "string",
                    },
                },
            },
        },
    },
}
