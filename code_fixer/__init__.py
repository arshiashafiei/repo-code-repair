"""
Code Fixer: Automated Program Repair with LLMs

A library for automated code review and patch generation using Large Language Models (LLMs) 
and Retrieval-Augmented Generation (RAG).
"""

__version__ = "0.1.0"

# Import main modules
from . import github_utils
from . import vector_store
from . import prompts
from . import patch_output
from . import swe_bench
from . import io_utils
from . import log
from . import process_layer

# Import key functions for convenience
from .vector_store import build_vector_store
from .github_utils import (
    download_codebase,
    get_commit_date_posix,
    save_issues_and_comments_before_commit,
)
from .swe_bench import (
    compute_patch_metrics,
    apply_patch_suggestions_and_diff,
    get_patch,
)

__all__ = [
    "__version__",
    # Modules
    "github_utils",
    "vector_store", 
    "prompts",
    "patch_output",
    "swe_bench",
    "io_utils",
    "log",
    "process_layer",
    # Functions
    "build_vector_store",
    "download_codebase",
    "get_commit_date_posix",
    "save_issues_and_comments_before_commit",
    "compute_patch_metrics",
    "apply_patch_suggestions_and_diff",
    "get_patch",
]
