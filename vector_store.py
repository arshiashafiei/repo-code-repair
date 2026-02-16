from hashlib import sha256
from langchain_chroma import Chroma
from langchain_core.vectorstores.base import VectorStore
from langchain_ollama import OllamaEmbeddings
from langchain_core.documents import Document
from pathlib import Path
from typing import List, Optional
import json

from langchain_text_splitters import RecursiveCharacterTextSplitter
from io_utils import get_file_content, iter_text_files
import log

import chromadb


def make_id(text):
    return sha256(text.encode("utf-8")).hexdigest()


def build_vector_store(codebase_root: str = "codebase", issues_jsonl_path: str | None = "issues/issues.jsonl", batch_size: int = 500, splitter_chunk_size: int = 400) -> VectorStore:
    # embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
    # embeddings = FakeEmbeddings(size=1352)
    # embeddings = HuggingFaceEmbeddings(model_name="nomic-ai/nomic-embed-text-v1.5")
    # embeddings = OllamaEmbeddings(model="qwen3-embedding:0.6b", num_thread=4, num_ctx=32768, num_gpu=-1, validate_model_on_init=True)
    embeddings = OllamaEmbeddings(
        model="granite-embedding:latest", num_thread=3, num_ctx=512, base_url="127.0.0.1:11434")
    # embeddings = OllamaEmbeddings(model="vuongnguyen2212/CodeRankEmbed", num_thread=3, num_ctx=2048, base_url="127.0.0.1:11434")
    # embeddings = JinaEmbeddings(session=requests.Session(), model_name="jina-embeddings-v2-base-code", jina_api_key=os.environ["JINA_API_KEY"])
    collection_id = f"{codebase_root}|{issues_jsonl_path}"
    collection_name = f"collection_{make_id(collection_id)[:16]}"
    log.log_and_print(
        f"Using collection: {collection_name} (for {codebase_root}, {issues_jsonl_path})")

    client = chromadb.HttpClient(host="127.0.0.1", port=8088, ssl=False)
    vector_store_from_client = Chroma(
        client=client,
        collection_name=collection_name,
        embedding_function=embeddings,
    )
    # vector_store_from_client.reset_collection()
    existing_count = vector_store_from_client._collection.count()
    if existing_count > 0:
        log.log_and_print(
            f"Collection '{collection_name}' already has {existing_count} documents. Skipping reprocessing.")
        return vector_store_from_client

    log.log_and_print(
        f"Collection '{collection_name}' is empty. Processing documents...")

    docs: List[Document] = []
    for p in iter_text_files(codebase_root):
        log.log_and_print(f"Name of the file scanned: {p.name}")
        text = get_file_content(p.as_posix())
        if not text:
            continue
        rel_path = p.relative_to(Path(codebase_root)).as_posix()
        docs.append(
            Document(
                page_content=rel_path + text,
                metadata={
                    "doc_type": "file",
                    "path": rel_path,
                    "id": make_id(text),
                },
            )
        )

    # GitHub issues / PRs from jsonl (optional)
    if issues_jsonl_path and Path(issues_jsonl_path).exists():
        with open(issues_jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    issue = json.loads(line)
                except json.JSONDecodeError as e:
                    raise e

                issue_text_parts = [
                    f"{issue.get('title')}\n",
                    f"{issue.get('body') or ''}\n"
                ]

                discussion_summary = issue.get('discussion_summary')
                if discussion_summary:
                    issue_text_parts.append(f"\n{discussion_summary}\n")

                issue_text = "".join(issue_text_parts)

                log.log_and_print(
                    f"Processing issue #{issue.get('number')}: {issue.get('title', '')[:50]}...")
                docs.append(
                    Document(
                        page_content=issue_text,
                        metadata={
                            "full_content": issue_text,
                            "doc_type": "issue",
                            "repo": issue.get("repo"),
                            "number": issue.get("number"),
                            "url": issue.get("html_url"),
                            "has_summary": bool(discussion_summary),
                            "id": make_id(issue_text),
                        },
                    )
                )

    log.log_and_print(f"Total documents BEFORE splitting: {len(docs)}")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=splitter_chunk_size, chunk_overlap=50)
    chunked_docs = text_splitter.split_documents(docs)
    log.log_and_print(f"Total documents AFTER splitting: {len(chunked_docs)}")

    log.log_and_print(f"######### Calculating Hashes....")
    ids = [f"{make_id(chunk.page_content)}_{i}" for i,
           chunk in enumerate(chunked_docs)]
    # for chunk in chunked_docs:
    #     log.log_and_print(f"Chunk ID: {make_id(chunk.page_content)} | \nContent Preview: {chunk.page_content[:100]}---")

    log.log_and_print(f"######### Adding documents to vector store....")
    for i in range(0, len(chunked_docs), batch_size):
        batch_docs = chunked_docs[i:i + batch_size]
        batch_ids = ids[i:i + batch_size]
        log.log_and_print(
            f"Adding batch {i // batch_size + 1}/{(len(chunked_docs) + batch_size - 1) // batch_size}: documents {i} to {i + len(batch_docs)}")
        vector_store_from_client.add_documents(
            documents=batch_docs, ids=batch_ids)

    return vector_store_from_client
