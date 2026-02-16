import os
import time
import traceback

from langchain_core.messages import AIMessage
import openai
from pydantic import BaseModel

from process_layer import LLM, RETRIEVER_LLM
from process_layer import context_retriever, build_context_payload_from_docs, retriever_bm25_docs, add_line_numbers
from log import log_and_print
from io_utils import get_project_tree, get_file_content
from patch_output import PatchSuggestions, DiffViewEdits, FilesToEdit
from prompts import OUTPUT_FORMAT, OUTPUT_FORMAT_FILESTOEDIT, USER_PROMPT_FILESTOEDIT, USER_PROMPT_V7, SYSTEM_PROMPT_PYTHON_PROGRAMMER


def offline_pipeline_file(prompt: str,
                          local_project_path: str, local_issues_path: str,
                          local_file_path: str, top_k: int = 2) -> AIMessage:
    log_and_print(f"Running offline_pipeline_file method...\n \
                      Args: local_project_path={local_project_path}\n \
                      | local_issues_path={local_issues_path} | local_file_path={local_file_path}\n \
                      | top_k={top_k}\n")

    try:
        os.stat(local_file_path)
        os.stat(local_issues_path)
        os.stat(local_project_path)
    except (OSError, ValueError) as e:
        log_and_print("Error occured in args of offline_pipeline_file")
        log_and_print(e)
        log_and_print(traceback.format_exc())
        raise e
    
    log_and_print(f"Reading file {local_file_path}...")
    file_content = get_file_content(local_file_path)

    context = context_retriever(local_project_path, local_issues_path, file_content, top_k)
    log_and_print(f"Numbering file content...")
    numbered_content = add_line_numbers(file_content)

    log_and_print(f"Creating user payload (aka prompt)...")
    user_payload = (
        prompt
        + "\n\n[CODE FILE PATH]\n"
        + local_file_path
        + "\n\n[BEGIN SUBMITTED CODE CONTENT]\n"
        + numbered_content
        + "\n[END SUBMITTED CODE CONTENT]\n\n"
        + context
    )
    log_and_print(f"{user_payload}")

    structured_llm = LLM.with_structured_output(PatchSuggestions)
    
    log_and_print(f"Calling LLM for patch generation with system prompt...\n{SYSTEM_PROMPT_PYTHON_PROGRAMMER}")
    response = structured_llm.invoke(
        [
            ("system", SYSTEM_PROMPT_PYTHON_PROGRAMMER),
            ("human", user_payload),
        ]
    )

    log_and_print(f"vvvvvvvvvvvv Response recived vvvvvvvvvvvv\n\n")
    log_and_print("\n--- Generated Snippets ---")
    for suggestion in response.edits:
        log_and_print(f"vvvvvvvvvvvvvvvvvvvvvvvv\n")
        log_and_print(f"{suggestion}")
    return response


def offline_pipeline_issue(prompt: str,
                           local_project_path: str, 
                           local_issues_path: str,
                           issue_content: str,
                           top_k: int = 2,
                           output_format: BaseModel = PatchSuggestions,
                           output_prompt: str = OUTPUT_FORMAT,
                           file_selection: bool = False) -> PatchSuggestions | DiffViewEdits:
    # issue_content = io_utils.get_issue_content(issue_id, local_issues_path)
    # issue_content = f"{issue_content[0]}\n{issue_content[1]}\n{issue_content[2]}" 

    if file_selection:
        file_docs = build_context_payload_from_docs(retriever_bm25_docs(local_project_path, local_issues_path, issue_content, top_k))
        structured_llm = RETRIEVER_LLM.with_structured_output(FilesToEdit)

        retriever_payload = (
            USER_PROMPT_FILESTOEDIT
            + "\n\n[ISSUE STATEMENT]\n"
            + issue_content
            + "\n[END ISSUE STATEMENT]\n\n"
            + "Top-30 similar files:\n"
            + file_docs
            # + f"\n[PROJECT TREE]\n{get_project_tree(local_project_path)}\n[END PROJECT TREE]\n"
            + OUTPUT_FORMAT_FILESTOEDIT
        )
        log_and_print("Calling LLM for file selection...\n")    
        log_and_print(f"Prompt Sent:\n\n{retriever_payload}\n\n")
        time.sleep(2)
        try:
            retriever_response = structured_llm.invoke(
                [
                    ("system", SYSTEM_PROMPT_PYTHON_PROGRAMMER),
                    ("human", retriever_payload),
                ]
            )
            if retriever_response and retriever_response.files_for_editing:
                raise ValueError
        except openai.RateLimitError as e:
            log_and_print("Rate limit error occurred. Retrying after 60 seconds...")
            time.sleep(60)
            retriever_response = structured_llm.invoke(
                [
                    ("system", SYSTEM_PROMPT_PYTHON_PROGRAMMER),
                    ("human", retriever_payload),
                ]
            )
        except ValueError:
            RETRIEVER_LLM.temperature = 0.2
            try:
                retriever_response = structured_llm.invoke(
                    [
                        ("system", SYSTEM_PROMPT_PYTHON_PROGRAMMER),
                        ("human", retriever_payload),
                    ]
                )
                if retriever_response and retriever_response.files_for_editing:
                    raise ValueError
            except openai.RateLimitError as e:
                log_and_print("Rate limit error occurred. Retrying after 60 seconds...")
                time.sleep(60)
                retriever_response = structured_llm.invoke(
                    [
                        ("system", SYSTEM_PROMPT_PYTHON_PROGRAMMER),
                        ("human", retriever_payload),
                    ]
                )
            except ValueError:
                RETRIEVER_LLM.temperature = 0.8
                retriever_response = structured_llm.invoke(
                    [
                        ("system", SYSTEM_PROMPT_PYTHON_PROGRAMMER),
                        ("human", retriever_payload),
                    ]
                )


        files_for_editing = "Only make changes to these files to solve the stated issue.\nFiles For Editing:\n"
        log_and_print(f"vvvvvvvvvvvv Retriever Response recived vvvvvvvvvvvv\n\n")
        log_and_print("\n--- Files to Edit ---")
        if retriever_response and retriever_response.files_for_editing:
            log_and_print("No files suggested for editing by the retriever LLM. Proceeding without file context.")
            for file_path in retriever_response.files_for_editing:
                log_and_print(f">>> {file_path}")
                try:
                    _raw = get_file_content(f"{local_project_path}/{file_path}")
                    files_for_editing += f"- File Path: {file_path}\n[File Content START]\n{add_line_numbers(_raw[:12000])}\n[File Content END]\n"
                except FileNotFoundError as e:
                    log_and_print(f"!!!Error while getting content for file {file_path}. Skipping this file.\nError: {e}")
                    continue
    context = context_retriever(local_project_path, local_issues_path, issue_content, top_k, with_tree=False)

    user_payload = (
        prompt 
        + "\n\n[ISSUE STATEMENT]\n"
        + issue_content
        + "\n[END ISSUE STATEMENT]\n\n"
        + (files_for_editing if file_selection else "")
        + context
        + output_prompt
    )
    
    structured_llm = LLM.with_structured_output(output_format)

    log_and_print("Calling LLM...\n")
    time.sleep(2)
    try:
        response = structured_llm.invoke(
            [
                ("system", SYSTEM_PROMPT_PYTHON_PROGRAMMER),
                ("human", user_payload),
            ]
        )
    except openai.RateLimitError as e:
        log_and_print("Rate limit error occurred. Retrying after 60 seconds...")
        time.sleep(60)
        response = structured_llm.invoke(
            [
                ("system", SYSTEM_PROMPT_PYTHON_PROGRAMMER),
                ("human", user_payload),
            ]
        )
    log_and_print(f"Prompt Sent:\n\n{user_payload}\n\n")
    log_and_print("Recieving response...\n")
    log_and_print("\n--- Generated Snippets ---")
    # for suggestion in response.edits:
    #     log_and_print(f"{suggestion}")
    if response and response.patch:
        log_and_print(f"{response.patch}")
    # patch_output.pretty_print_response(response)
    return response


def main():
    local_file_path = "codebase/manage.py"
    local_file_response = offline_pipeline_file(OUTPUT_FORMAT + USER_PROMPT_V7, "codebase", "issues/local_issues_summaries.jsonl", local_file_path, top_k=5)
    # local_issue_response= offline_pipeline_issue(USER_PROMPT_V4, "codebase", "issues/local_issues_summaries.jsonl", 1, top_k=5)
    # file_diff_view = evaluation.patch_response_to_diff(local_file_response, local_file_path, "")

    # log_and_print(f"vvvvvvvv Git diff view vvvvvvvv\n{file_diff_view}")


if __name__ == "__main__":
    main()
