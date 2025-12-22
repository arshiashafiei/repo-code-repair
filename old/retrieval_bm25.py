from __future__ import annotations
import os
import pathlib
from typing import Iterable, List, Tuple

from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever
# from langchain_chroma import Chroma
# from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings

DEFAULT_EMBED_MODEL = "nvidia/llama-3.2-nv-embedqa-1b-v2"
ALLOWED_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".go", ".rb", ".rs", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".php", ".swift", ".m", ".mm", ".scala", ".sql", ".sh", ".bash", ".ps1",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".json", ".md", ".txt", ".rst",
    ".css", ".scss", ".html", ".htm", ".xml", ".gradle", ".properties", ".dockerfile", ".env", ".makefile",
}


def _iter_code_files(root: str | os.PathLike) -> Iterable[pathlib.Path]:
    root_path = pathlib.Path(root)
    for p in root_path.rglob("*"):
        if p.is_file():
            ext = p.suffix.lower()
            name_lower = p.name.lower()

            if ext in ALLOWED_EXTS or name_lower in {"makefile", "dockerfile"}:
                yield p


def _read_text(p: pathlib.Path, max_bytes: int = 2_000_000) -> str:
    try:
        if p.stat().st_size > max_bytes:
            return ""  # skip very large files
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _build_docs(codebase_dir: str) -> List[Document]:
    base = pathlib.Path(codebase_dir).resolve()
    docs: List[Document] = []
    for fp in _iter_code_files(base):
        txt = _read_text(fp)
        if not txt.strip():
            continue
        # repo-root-relative path (required format)
        rel = fp.relative_to(base).as_posix()
        docs.append(Document(page_content=txt, metadata={"path": rel}))
    return docs


# def vectorize_codebase_to_chroma(
#     codebase_dir: str = "codebase",
#     collection_name: str = "codebase",
#     embedding_model: str = DEFAULT_EMBED_MODEL,
# ):
#     """
#     Load files from `codebase_dir`, embed with Llama-3.2 embedding, and store in an in-memory Chroma collection.
#     Returns (vectorstore, documents).
#     """
#     # NVIDIA Llama 3.2 embedding via NIM
#     embeddings = NVIDIAEmbeddings(model=embedding_model)  # uses NVIDIA_API_KEY env var

#     docs = _build_docs(codebase_dir)
#     # In-memory Chroma if no persist_directory is given
#     vs = Chroma(collection_name=collection_name, embedding_function=embeddings)
#     if docs:
#         vs.add_documents(docs, ids=[d.metadata["path"] for d in docs])
#     print(f"[vectorize_codebase_to_chroma] Indexed {len(docs)} files into Chroma collection '{collection_name}'.")
#     return vs, docs


def bm25_top_k_files_for_issue(
    issue_text: str,
    codebase_dir: str = "codebase",
    k: int = 30,
    # embedding_model: str = DEFAULT_EMBED_MODEL,
) -> List[str]:
    """
    Uses BM25 lexical retrieval to rank files by similarity.
    Returns the top-k repo-root-relative paths as an ordered list, and logs them.
    """
    # _ = NVIDIAEmbeddings(model=embedding_model).embed_query(issue_text)

    docs = _build_docs(codebase_dir)

    retriever = BM25Retriever.from_documents(docs, k=k)
    results = retriever.invoke(issue_text)
    print(results)

    ordered_paths = [d.metadata.get("path", "") for d in results if d.metadata.get("path")]
    print("[bm25_top_k_files_for_issue] Top files:")
    for i, p in enumerate(ordered_paths, 1):
        print(f"{i:>2}. {p}")
    return ordered_paths


if __name__ == "__main__":
    bm25_top_k_files_for_issue("""Add Docker healthcheck and named volume to docker-compose.yml 
                               A healthcheck helps devs see when the app is truly ready; a named volume preserves the dev DB between restarts.

**Proposal:**

- Add a healthcheck to the web service (e.g., curl http://localhost:8000/ until 200).
- Add a named volume for the SQLite/Postgres data.
This is a small improvement aligned with the existing Dockerfile and docker-compose.yml in the repo.""")

#     bm25_top_k_files_for_issue("""Add pagination to the blog list view
# On pages that list posts, all results appear on a single page. This can get slow and unwieldy as content grows.
# you can use Django’s Paginator to show ~5–10 posts per page and render page_obj controls in the template. This is a contained change that improves UX and performance.
# The project already has a dedicated blog/ app, so the change is nicely scoped to that app.""")

#     bm25_top_k_files_for_issue("""Add pagination to the blog list view
# On pages that list posts, all results appear on a single page. This can get slow and unwieldy as content grows.
# you can use Django’s Paginator to show ~5–10 posts per page and render page_obj controls in the template. This is a contained change that improves UX and performance.
# The project already has a dedicated blog/ app, so the change is nicely scoped to that app.""")

#     bm25_top_k_files_for_issue("""Add pagination to the blog list view
# On pages that list posts, all results appear on a single page. This can get slow and unwieldy as content grows.
# you can use Django’s Paginator to show ~5–10 posts per page and render page_obj controls in the template. This is a contained change that improves UX and performance.
# The project already has a dedicated blog/ app, so the change is nicely scoped to that app.""")
