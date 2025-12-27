from pydantic import BaseModel, Field
from typing import Any, Iterable, List, Literal, Optional, Tuple

import log

Category = Literal[
    "CORRECTNESS",
    "ROBUSTNESS_ERROR_HANDLING",
    "ARCHITECTURE_DESIGN",
    "READABILITY_NAMING",
    "PERFORMANCE",
    "MAINTAINABILITY_TECH_DEBT",
]
Severity = Literal["low", "med", "high"]


class PatchSuggestion(BaseModel):
    category: Category
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)

    evidence: str 
    file_path: str

    line_start: Optional[int] = None
    line_end: Optional[int] = None

    exact_existing_snippet: str
    replacement_snippet: str
    
    summary: str


class PatchResponse(BaseModel):
    suggestions: List[PatchSuggestion] = Field(default_factory=list)


def pretty_print_response(resp: PatchResponse) -> None:
    for s in resp.suggestions:
        log.log_and_print(f"[{s.category}] [severity: {s.severity}] [confidence: {s.confidence:.2f}]")
        log.log_and_print(f"[evidence]\n{s.evidence}")
        log.log_and_print(f"[path + file name]\n{s.file_path}")
        log.log_and_print(f"[Line numbers]\n{(s.line_start, s.line_end)}")
        log.log_and_print("[exact existing snippet]\n" + s.exact_existing_snippet)
        log.log_and_print("[replacement snippet]\n" + s.replacement_snippet)
        log.log_and_print("[Summary]\n" + s.summary)
        log.log_and_print("-" * 80)
