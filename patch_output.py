from pydantic import BaseModel, Field
from typing import Any, Iterable, List, Literal, Optional, Tuple

import log


Category = Literal[
    "SYNTAX_ERROR",
    "LINTING",
    "OTHER"
]


class PatchSnippet(BaseModel):
    category: Category
    confidence: float = Field(ge=-0.1, le=1.1)
    evidence: str 

    line_start_for_editing: int
    line_end_for_editing: int

    exact_existing_buggy_snippet: str
    correct_replacement_snippet: str


class PatchSuggestions(BaseModel):
    file_path_to_edit: str
    edits: List[PatchSnippet] = Field(default_factory=list)


class MultiFileSnippet(BaseModel):
    file_path_to_edit: str
    file_edits: List[PatchSnippet] = Field(default_factory=list)


class MultiFileSuggestions(BaseModel):
    edits: List[MultiFileSnippet] = Field(default_factory=list)


class DiffviewEdits(BaseModel):
    edits: str


def pretty_print_response(resp: PatchSuggestions) -> None:
    for s in resp.edits:
        log.log_and_print(f"[{s.category}] [confidence: {s.confidence:.2f}]")
        log.log_and_print(f"[evidence]\n{s.evidence}")
        log.log_and_print(f"[path + file name]\n{resp.file_path_to_edit}")
        log.log_and_print(f"[Line numbers]\n{(s.line_start_for_editing, s.line_end_for_editing)}")
        log.log_and_print("[exact existing snippet]\n" + s.exact_existing_buggy_snippet)
        log.log_and_print("[replacement snippet]\n" + s.correct_replacement_snippet)
        log.log_and_print("#" * 160)
