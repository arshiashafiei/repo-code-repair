from langchain_core.vectorstores import InMemoryVectorStore
from langchain_core.vectorstores.base import VectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document
from pathlib import Path
from typing import Any, Iterable, List, Literal, Optional, Tuple

from io_utils import get_file_content, iter_issues_jsonl, iter_text_files
import log


def build_vector_store(codebase_root: str="codebase", issues_jsonl_path: str | None="issues/issues.jsonl") -> VectorStore:
    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
    docs: List[Document] = []

    # Codebase files
    for p in iter_text_files(codebase_root):
        log.log_and_print(f"Name of the file scanned: {p.name}")
        text = get_file_content(p.as_posix())
        if not text:
            continue
        docs.append(
            Document(
                page_content=text,
                metadata={
                    "doc_type": "file",
                    "path": p.as_posix(),
                },
            )
        )

    # GitHub issues / PRs from jsonl (optional)
    if issues_jsonl_path and Path(issues_jsonl_path).exists():
        for issue in iter_issues_jsonl():
            issue_text = (
                f"title={issue.get('title')}\n"
                f"labels:\n{issue.get('labels') or ''}\n"
                f"body:\n{issue.get('body') or ''}\n"
            )
            log.log_and_print(f"Processing...\n{issue_text}")
            docs.append(
                Document(
                    page_content=issue_text,
                    metadata={
                        "doc_type": "issue",
                        "repo": issue.get("repo"),
                        "number": issue.get("number"),
                        "url": issue.get("html_url"),
                    },
                )
            )
    
    vector_store = InMemoryVectorStore(embeddings)
    vector_store.add_documents(documents=docs)
    
    return vector_store
