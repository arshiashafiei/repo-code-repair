import os
import getpass

from typing import Any, Iterable, List, Literal, Optional, Tuple
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama

import log
import io_utils
from patch_output import PatchSuggestions
from vector_store import build_vector_store
from prompts import SIMPLE_REVIEW_PROMPT, SIMPLE_WHOLE_FILE_PATCH_PROMPT, \
    SYSTEM_PROMPT_V1, SYSTEM_PROMPT_PYTHON_PROGRAMMER, \
    USER_PROMPT_V1, USER_PROMPT_V2, USER_PROMPT_V3, \
    USER_PROMPT_V4, USER_PROMPT_V5


LLM = None

if not LLM:
    print("""
          1- qwen2.5-coder:0.5b (default)
          2- gemma2:2b
          3- gemini-2.5-flash
          4- qwen3:14b
          5- deepseek-r1:14b
          6- gemma3:12b
          7- upstage/solar-pro-3:free
          8- liquid/lfm-2.5-1.2b-thinking:free
          9- tngtech/deepseek-r1t2-chimera:free
          10- openrouter/auto
          """)
    selected = input("Select a model to continue: ")
    # selected = "2"
    if selected == "1":
        log.log_and_print("qwen2.5-coder:0.5b selected")
        LLM = ChatOllama(model="qwen2.5-coder:0.5b", temperature=0, top_p=0.8)
    elif selected == "2":
        log.log_and_print("gemma2:2b selected")
        LLM = ChatOllama(model="gemma2:2b", temperature=0, top_p=0.8)
    elif selected == "3":
        log.log_and_print("gemini-2.5-flash")
        if "GOOGLE_API_KEY" not in os.environ:
            os.environ["GOOGLE_API_KEY"] = getpass.getpass("Enter your GOOGLE_API_KEY: ")

        LLM = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.1,
            top_p=0.8,
            max_retries=1,
            timeout=60,
        )
    elif selected == "4":
        log.log_and_print("qwen3:14b selected")
        LLM = ChatOllama(model="qwen3:14b", temperature=0, top_p=0.8)
    elif selected == "5":
        log.log_and_print("deepseek-r1:14b selected")
        LLM = ChatOllama(model="deepseek-r1:14b", temperature=0, top_p=0.8)
    elif selected == "6":
        log.log_and_print("gemma3:12b selected")
        LLM = ChatOllama(model="gemma3:12b", temperature=0, top_p=0.8)
    elif selected == "7":
        if not os.environ.get("OPENROUTER_API_KEY"):
            os.environ["OPENROUTER_API_KEY"] = getpass.getpass("Enter your OPENROUTER_API_KEY: ")

        LLM = ChatOpenAI(
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            model="upstage/solar-pro-3:free",
        )
    elif selected == "8":
        if not os.environ.get("OPENROUTER_API_KEY"):
            os.environ["OPENROUTER_API_KEY"] = getpass.getpass("Enter your OPENROUTER_API_KEY: ")

        LLM = ChatOpenAI(
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            model="liquid/lfm-2.5-1.2b-thinking:free",
        )
    elif selected == "9":
        if not os.environ.get("OPENROUTER_API_KEY"):
            os.environ["OPENROUTER_API_KEY"] = getpass.getpass("Enter your OPENROUTER_API_KEY: ")

        LLM = ChatOpenAI(
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            model="tngtech/deepseek-r1t2-chimera:free",
        )
    elif selected == "10":
        if not os.environ.get("OPENROUTER_API_KEY"):
            os.environ["OPENROUTER_API_KEY"] = getpass.getpass("Enter your OPENROUTER_API_KEY: ")

        LLM = ChatOpenAI(
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            model="openrouter/auto",
        )
    else:
        LLM = ChatOllama(model="qwen2.5-coder:0.5b", temperature=0)


def context_retriever(project_path: str, issues_path: str, query_content: str, top_k: int = 3):
    vector_store = build_vector_store(project_path, issues_path)

    log.log_and_print(f"Querying for similar docs...\n\nQuery Text:\n{query_content}\n")
    similar_docs = vector_store.similarity_search(
        query_content,
        k = top_k + 1,
    )

    log.log_and_print(f"#{top_k} Similar docs found:\n\n{similar_docs}")
    related_files_block = ""
    related_issues_block = ""
    found = set()
    for d in similar_docs[1:]:
        if d.metadata.get("id") in found:
            continue
        log.log_and_print(f"############# Doc Content: #############")
        log.log_and_print(f"{d.page_content}")
        found.add(d.metadata.get("id"))

        if d.metadata.get("doc_type") == "file" and d.page_content != query_content:
            c: str = io_utils.get_file_content(d.metadata.get("path"))
            related_files_block += "".join(
                f"---BEGIN RELATED FILE---\n"
                f"FILEPATH: {d.metadata.get('path')}\n"
                f"CONTENT:\n{c[:4000].rstrip()}\n"
                f"---END RELATED FILE---\n"
            )
        elif d.metadata.get("doc_type") == "issue":
            c: str = d.metadata.get("full_content")
            related_issues_block += "".join(
                f"---BEGIN RELATED ISSUE: {d.metadata.get('repo')}#{d.metadata.get('number')}---\n"
                f"CONTENT:\n{c[:4000].rstrip()}\n"
                f"---END RELATED ISSUE---\n"
            )


    context_payload = (
        "[TOP-" + str(top_k) + " RELEVANT CONTEXT as FILES or ISSUES]\n"
        + (related_files_block)
        + (related_issues_block)
        + "\n[END RELEVANT CONTEXT]\n"
    )
    return context_payload


def add_line_numbers(text: str) -> str:
    lines = text.splitlines()
    return "\n".join(f"{i:04d}: {line}" for i, line in enumerate(lines, start=1))


def main() -> None:
    vector_store = build_vector_store()

    target_path = "manage.py"
    file_text = io_utils.get_file_content(target_path)
    
    query_text = file_text[:6000]
    log.log_and_print(f"Querying for similar docs...\n\nQuery Text:\n{query_text}\n")
    similar_docs = vector_store.similarity_search(
        query_text,
        k=4,
    )
    
    log.log_and_print(f"Similar docs found:\n\n{similar_docs}")
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
        + target_path
        + "\n\n[TARGET FILE CONTENT(LINE-NUMBERED VIEW)]\n---BEGIN NUMBERED TARGET FILE---\n"
        + numbered_target
        + "\n[END NUMBERED TARGET FILE CONTENT]\n"
        + "\n\n[TOP-3 SIMILAR FILES/ISSUES CONTEXT]\n"
        + (related_files_block or "(none)\n")
        + (related_issues_block or "(none)\n")
        + "\n\n[END RELEVANT CONTEXT]\n"
    )
    
    structured_llm = LLM.with_structured_output(PatchSuggestions)

    log.log_and_print("Calling LLM...\n")
    response = structured_llm.invoke(
        [
            (
                "system",
                SYSTEM_PROMPT_V1
            ),
            ("human", user_payload),
        ]
    )
    log.log_and_print(f"Prompt Sent:\n\n{user_payload}\n\n")
    log.log_and_print("Recieving response...\n")
    log.log_and_print(response.edits)

    if response.edits:
        for suggestion in response.edits:
            print("\n--- Generated Snippet ---")
            print(suggestion.replacement_snippet)


if __name__ == "__main__":
    main()
