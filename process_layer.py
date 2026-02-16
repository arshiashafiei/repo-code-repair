import os
import getpass
import json

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from langchain_ollama import ChatOllama
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

from log import log_and_print
from io_utils import get_project_tree, get_file_content, iter_text_files
from patch_output import PatchSuggestions
from vector_store import build_vector_store, make_id
from apply_patch import extract_file_documentation


LLM = None

# LLM = ChatDeepSeek(
#     api_key=os.environ.get("DEEPSEEK_API_KEY"),
#     api_base="https://api.deepseek.com",
#     model="deepseek-chat",
#     # disabled_params={"tool_choice": None}
#     temperature=0, top_p=0.8,
# )

# RETRIEVER_LLM = ChatDeepSeek(
#     api_key=os.environ.get("DEEPSEEK_API_KEY2"),
#     api_base="https://api.deepseek.com",
#     model="deepseek-chat",
#     # disabled_params={"tool_choice": None}
#     temperature=0, top_p=0.8,
# )

LLM = ChatOllama(model="gemma2:2b", temperature=0, top_p=0.8)
RETRIEVER_LLM = LLM
# LLM = ChatGoogleGenerativeAI(
#     model="gemini-2.5-flash",
#     temperature=0,
#     top_p=0.95,
#     max_retries=1,
#     timeout=180,
#     api_key=os.environ.get("GOOGLE_API_KEY"),
# )


# RETRIEVER_LLM = ChatGoogleGenerativeAI(
#     api_key=os.environ.get("GOOGLE_API_KEY2"),
#     model="gemini-2.5-flash",
#     temperature=0,
#     top_p=0.95,
#     max_retries=1,
#     timeout=180,
# )

# LLM = ChatOpenAI(
#     # base_url="94.184.177.134:8000/v1",
#     model="qwen/qwen3-coder:free",
#     api_key=os.environ.get("OPENROUTER_API_KEY"),
#     base_url="https://openrouter.ai/api/v1",
#     # disabled_params={"tool_choice": None},
#     # extra_body={"reasoning": {"enabled": True}},
#     temperature=0, top_p=0.8,
#     #  "max_tokens": 163840, "transforms": ["middle-out"]
# )

# RETRIEVER_LLM = ChatOpenAI(
#     # base_url="94.184.177.134:8000/v1",
#     model="qwen/qwen3-coder:free",
#     api_key=os.environ.get("OPENROUTER_API_KEY"),
#     base_url="https://openrouter.ai/api/v1",
#     # disabled_params={"tool_choice": None},
#     # extra_body={"reasoning": {"enabled": True}},
#     temperature=0, top_p=0.8,
#     #  "max_tokens": 163840, "transforms": ["middle-out"]
# )

# LLM = ChatOllama(
#     model="deepseek-r1:14b", temperature=0, top_p=0.8,
#     base_url="NGROK_URL", num_ctx=32768, num_gpu=30, validate_model_on_init=True,

#     reasoning=True,
# )

# if not LLM:
#     print("""
#           1- qwen2.5-coder:0.5b (default)
#           2- gemma2:2b
#           3- gemini-2.5-flash
#           4- qwen3:14b
#           5- deepseek-r1:14b
#           6- gemma3:12b
#           7- upstage/solar-pro-3:free
#           8- liquid/lfm-2.5-1.2b-thinking:free
#           9- tngtech/deepseek-r1t2-chimera:free
#           10- arcee-ai/trinity-large-preview:free
#           """)
#     selected = input("Select a model to continue: ")
#     # selected = "2"
#     if selected == "1":
#         log_and_print("qwen2.5-coder:0.5b selected")
#         LLM = ChatOllama(model="qwen2.5-coder:0.5b", temperature=0, top_p=0.8)
#     elif selected == "2":
#         log_and_print("gemma2:2b selected")
#         LLM = ChatOllama(model="gemma2:2b", temperature=0, top_p=0.8)
#     elif selected == "3":
#         log_and_print("gemini-2.5-flash")
#         if "GOOGLE_API_KEY" not in os.environ:
#             os.environ["GOOGLE_API_KEY"] = getpass.getpass("Enter your GOOGLE_API_KEY: ")

#         LLM = ChatGoogleGenerativeAI(
#             model="gemini-2.5-flash",
#             temperature=0,
#             top_p=0.8,
#             max_retries=1,
#             timeout=180,
#         )
#     elif selected == "4":
#         log_and_print("qwen3:14b selected")
#         LLM = ChatOllama(model="qwen3:14b", temperature=0, top_p=0.8)
#     elif selected == "5":
#         log_and_print("deepseek-r1:14b selected")
#         LLM = ChatOllama(model="deepseek-r1:14b", temperature=0, top_p=0.8)
#     elif selected == "6":
#         log_and_print("gemma3:12b selected")
#         LLM = ChatOllama(model="gemma3:12b", temperature=0, top_p=0.8)
#     elif selected == "7":
#         if not os.environ.get("OPENROUTER_API_KEY"):
#             os.environ["OPENROUTER_API_KEY"] = getpass.getpass("Enter your OPENROUTER_API_KEY: ")

#         LLM = ChatOpenAI(
#             api_key=os.environ.get("OPENROUTER_API_KEY"),
#             base_url="https://openrouter.ai/api/v1",
#             model="upstage/solar-pro-3:free",
#         )
#     elif selected == "8":
#         if not os.environ.get("OPENROUTER_API_KEY"):
#             os.environ["OPENROUTER_API_KEY"] = getpass.getpass("Enter your OPENROUTER_API_KEY: ")

#         LLM = ChatOpenAI(
#             api_key=os.environ.get("OPENROUTER_API_KEY"),
#             base_url="https://openrouter.ai/api/v1",
#             model="liquid/lfm-2.5-1.2b-thinking:free",
#         )
#     elif selected == "9":
#         if not os.environ.get("OPENROUTER_API_KEY"):
#             os.environ["OPENROUTER_API_KEY"] = getpass.getpass("Enter your OPENROUTER_API_KEY: ")

#         LLM = ChatOpenAI(
#             api_key=os.environ.get("OPENROUTER_API_KEY"),
#             base_url="https://openrouter.ai/api/v1",
#             model="tngtech/deepseek-r1t2-chimera:free",
#         )
#     elif selected == "10":
#         if not os.environ.get("OPENROUTER_API_KEY"):
#             os.environ["OPENROUTER_API_KEY"] = getpass.getpass("Enter your OPENROUTER_API_KEY: ")

#         LLM = ChatOpenAI(
#             api_key=os.environ.get("OPENROUTER_API_KEY"),
#             base_url="https://openrouter.ai/api/v1",
#             model="arcee-ai/trinity-large-preview:free",
#         )
#     else:
#         LLM = ChatOllama(model="qwen2.5-coder:0.5b", temperature=0)


def context_retriever(project_path: str, issues_path: str, query_content: str, top_k: int = 3, with_summary: bool = False, with_tree: bool = True):
    vector_store = build_vector_store(project_path, issues_path)

    log_and_print(f"Querying for similar docs...\n\nQuery Text:\n{query_content}\n")
    similar_docs = vector_store.similarity_search(
        query_content,
        k = top_k * 2 + 1,
    )
    # retriever = vector_store.as_retriever(search_type="mmr", search_kwargs={"k": 2 * (top_k + 1), "fetch_k": 40, "lambda_mult": 0.25})
    
    # similar_docs = retriever.invoke(query_content)
    log_and_print(f"#{len(similar_docs)} Similar docs found:\n\n")
    related_files_block = ""
    related_issues_block = ""
    found = set()
    counter = 0
    for d in similar_docs:
        log_and_print(f"############# Doc Path: #############")
        log_and_print(f"{d.metadata.get("path")}")
        log_and_print(f"{d.metadata.get("url")}")
        log_and_print(f"{top_k}")
        log_and_print(f"{counter}")
        if d.metadata.get("id") in found:
            log_and_print(f"!!doc already checked in {found} | skipping...")
            continue
        found.add(d.metadata.get("id"))

        if counter >= top_k + 1:
            log_and_print(f"!!!!Breaking...")
            break
        if d.metadata.get("doc_type") == "file":
            log_and_print(f"Not The same file {d.metadata.get("id") != make_id(query_content)}")
            c: str = get_file_content(f"{project_path}/{d.metadata.get("path")}")
            related_files_block += "".join(
                f"---BEGIN RELATED FILE---\n"
                f"FILEPATH: ./{d.metadata.get('path')}\n"
                f"CONTENT:\n{(c[:4000].rstrip())}\n"
                f"---END RELATED FILE---\n"
            )
            counter += 1
        elif d.metadata.get("doc_type") == "issue" and d.metadata.get("full_content") != query_content:
            c: str = d.metadata.get("full_content")
            log_and_print(f"Not The same issue {d.metadata.get("full_content") != query_content}")
            related_issues_block += "".join(
                f"---BEGIN RELATED ISSUE: {d.metadata.get('repo')}#{d.metadata.get('number')}---\n"
                f"CONTENT:\n{c[:4000].rstrip()}\n"
                f"---END RELATED ISSUE---\n"
            )
            counter += 1


    context_payload = (
        "[TOP-" + str(top_k) + " RELEVANT CONTEXT as FILES or ISSUES]\n"
        + (related_files_block)
        + (related_issues_block)
        + "\n[END RELEVANT CONTEXT]\n"
        + f"[PROJECT TREE]\n{get_project_tree(project_path)}\n[END PROJECT TREE]\n" if with_tree else ""
    )
    return context_payload


def context_retriever_both(project_path: str, issues_path: str, query_content: str, top_k: int = 3):
    vector_store = build_vector_store(project_path, issues_path)

    log_and_print(f"Querying for similar docs...\n\nQuery Text:\n{query_content}\n")
    similar_docs = vector_store.similarity_search(
        query_content,
        k = 2 * (top_k + 1),
    )
    retriever = vector_store.as_retriever(search_type="mmr", search_kwargs={"k": top_k + 1, "lambda_mult": 0.5, "filter": {"doc_type": "file"}})
    
    similar_docs = retriever.invoke(query_content)

    log_and_print(f"#{top_k} Similar docs found:\n")
    related_files_block = ""
    related_issues_block = ""
    found = set()
    file_counter = 0
    issue_counter = 0
    for d in similar_docs:
        log_and_print(f"{d.metadata}\n")
        if d.metadata.get("id") in found:
            continue
        log_and_print(f"############# Doc Path: #############")
        log_and_print(f"{d.metadata.get("path")}")

        found.add(d.metadata.get("id"))
        if d.metadata.get("doc_type") == "file" and d.page_content != query_content and file_counter < top_k:
            c: str = get_file_content(f"{project_path}/{d.metadata.get("path")}")
            related_files_block += "".join(
                f"---BEGIN RELATED FILE (Line Numbered)---\n"
                f"FILEPATH: ./{d.metadata.get('path')}\n"
                f"CONTENT:\n{add_line_numbers(c[:4000].rstrip())}\n"
                f"---END RELATED FILE---\n"
            )
            file_counter += 1

    for d in similar_docs:
        if d.metadata.get("id") in found:
            continue
        log_and_print(f"############# ISSUE URL: #############")
        log_and_print(f"{d.metadata.get("html_url")}")
        found.add(d.metadata.get("id"))
        if d.metadata.get("doc_type") == "issue" and make_id(query_content) != d.metadata.get("id") and issue_counter < top_k:
            c: str = d.metadata.get("full_content")
            related_issues_block += "".join(
                f"---BEGIN RELATED ISSUE: {d.metadata.get('repo')}#{d.metadata.get('number')}---\n"
                f"CONTENT:\n{c[:4000].rstrip()}\n"
                f"---END RELATED ISSUE---\n"
            )
            issue_counter += 1

    context_payload = (
        "[TOP-" + str(top_k) + " RELEVANT CONTEXT as FILES]\n"
        + (related_files_block)
        + "\n[END RELEVANT FILES]\n"
        + "[TOP-" + str(top_k) + " RELEVANT CONTEXT as ISSUES]\n"
        + (related_issues_block)
        + "\n[END RELEVANT ISSUES]\n"
    )
    return context_payload


def retriever_bm25_docs(project_path: str, issues_path: str, query_content: str, top_k: int = 3, with_summary: bool = False, with_tree: bool = True) -> dict:
    """
    Retrieve top-30 files using BM25 retriever and return their documentation.
    
    Args:
        project_path: Path to the project root
        issues_path: Path to issues (unused but kept for API compatibility)
        query_content: Query text to search for
        top_k: Unused but kept for API compatibility
        with_summary: Unused but kept for API compatibility
        with_tree: Unused but kept for API compatibility
        
    Returns:
        Dict with file paths as keys and file documentation dicts as values
    """
    # Build document list from Python files in the project
    file_docs = []
    for file_path in iter_text_files(project_path):
        try:
            content = file_path.read_text(encoding="utf-8")
            rel_path = file_path.relative_to(project_path).as_posix()
            file_docs.append(Document(
                page_content=content,
                metadata={"path": rel_path}
            ))
        except Exception as e:
            log_and_print(f"[{type(e).__name__}] Failed to read {file_path}: {e}")
    
    if not file_docs:
        return {}
    
    log_and_print(f"Found {len(file_docs)} Python files in {project_path}")
    
    # Create BM25 retriever from file documents
    bm25_retriever = BM25Retriever.from_documents(file_docs, k=30)
    
    log_and_print(f"BM25 retrieving top-30 files for query...\n")
    retrieved_docs = bm25_retriever.invoke(query_content)
    
    # Build result dict with file path -> file documentation
    result = {}
    for doc in retrieved_docs:
        file_path = doc.metadata.get("path")
        if file_path:
            try:
                file_doc = extract_file_documentation(doc.page_content)
                result[file_path] = file_doc
                log_and_print(f"Extracted documentation for: {file_path}")
            except Exception as e:
                log_and_print(f"[{type(e).__name__}] Failed to extract documentation for {file_path}: {e}")
    
    return result


def build_context_payload_from_docs(file_docs: dict) -> str:
    """
    Build a JSON context payload for LLM input from file documentation dict.
    
    Args:
        file_docs: Dict with file paths as keys and file documentation dicts as values
                   (output from retriever_bm25_docs)
        
    Returns:
        JSON string containing the context payload for LLM input
    """
    
    payload = {
        "retrieved_file_documentations": [
            {
                "path": file_path,
                "documentation": doc
            }
            for file_path, doc in file_docs.items()
        ]
    }

    return json.dumps(payload, indent=2, ensure_ascii=False)


def add_line_numbers(text: str) -> str:
    lines = text.splitlines()
    return "\n".join(f"{i:04d} {line}" for i, line in enumerate(lines, start=1))


def main() -> None:
    vector_store = build_vector_store()

    target_path = "manage.py"
    file_text = get_file_content(target_path)
    
    query_text = file_text[:6000]
    log_and_print(f"Querying for similar docs...\n\nQuery Text:\n{query_text}\n")
    similar_docs = vector_store.similarity_search(
        query_text,
        k=4,
    )
    
    log_and_print(f"Similar docs found:\n\n{similar_docs}")
    related_files_block = ""
    related_issues_block = ""
    for d in similar_docs:
        if d.metadata.get("doc_type") == "file" and d.metadata.get("path") != target_path:
            related_files_block = "".join(
                f"---BEGIN RELATED FILE: {d.metadata.get('path')}---\n"
                f"{d.page_content[:4000].rstrip()}\n"
                f"---END RELATED FILE---"
            )
        elif d.metadata.get("doc_type") == "issue":
            related_issues_block = "".join(
                f"---BEGIN RELATED ISSUE: {d.metadata.get('repo')}#{d.metadata.get('number')}---\n"
                f"{d.page_content[:2000].rstrip()}\n"
                f"---END RELATED ISSUE---"
            )

    numbered_target = add_line_numbers(file_text)
    
    user_payload = (
        SIMPLE_WHOLE_FILE_PATCH_PROMPT
        + "\n\n[TARGET FILE PATH]\n"
        + "./" + target_path
        + "\n\n[TARGET FILE CONTENT(LINE-NUMBERED VIEW)]\n---BEGIN NUMBERED TARGET FILE---\n"
        + numbered_target
        + "\n[END NUMBERED TARGET FILE CONTENT]\n"
        + "\n\n[TOP-3 SIMILAR FILES/ISSUES CONTEXT]\n"
        + (related_files_block or "(none)\n")
        + (related_issues_block or "(none)\n")
        + "\n\n[END RELEVANT CONTEXT]\n"
    )
    
    structured_llm = LLM.with_structured_output(PatchSuggestions)

    log_and_print("Calling LLM...\n")
    response = structured_llm.invoke(
        [
            (
                "system",
                SYSTEM_PROMPT_V1
            ),
            ("human", user_payload),
        ]
    )
    log_and_print(f"Prompt Sent:\n\n{user_payload}\n\n")
    log_and_print("Recieving response...\n")
    log_and_print(response.edits)

    if response.edits:
        for suggestion in response.edits:
            print("\n--- Generated Snippet ---")
            print(suggestion.replacement_snippet)


if __name__ == "__main__":
    main()
