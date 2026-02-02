import os
import traceback
import patch_output
from process_layer import LLM, SIMPLE_WHOLE_FILE_PATCH_PROMPT, SYSTEM_PROMPT_V1, SYSTEM_PROMPT_PYTHON_PROGRAMMER, USER_PROMPT_V2, USER_PROMPT_V3, USER_PROMPT_V4, USER_PROMPT_V5, add_line_numbers
import log
import io_utils
from patch_output import PatchSuggestions
from prompts import OUTPUT_FORMAT, USER_PROMPT_V7
from vector_store import build_vector_store
from langchain_core.messages import AIMessage
from process_layer import context_retriever


def offline_pipeline_file(prompt: str,
                          local_project_path: str, local_issues_path: str,
                          local_file_path: str, top_k: int = 2) -> AIMessage:
    log.log_and_print(f"Running offline_pipeline_file method...\n \
                      Args: local_project_path={local_project_path}\n \
                      | local_issues_path={local_issues_path} | local_file_path={local_file_path}\n \
                      | top_k={top_k}\n")

    try:
        os.stat(local_file_path)
        os.stat(local_issues_path)
        os.stat(local_project_path)
    except (OSError, ValueError) as e:
        log.log_and_print("Error occured in args of offline_pipeline_file")
        log.log_and_print(e)
        log.log_and_print(traceback.format_exc())
        raise e
    
    log.log_and_print(f"Reading file {local_file_path}...")
    file_content = io_utils.get_file_content(local_file_path)

    context = context_retriever(local_project_path, local_issues_path, file_content, top_k)
    log.log_and_print(f"Numbering file content...")
    numbered_content = add_line_numbers(file_content)

    log.log_and_print(f"Creating user payload (aka prompt)...")
    user_payload = (
        prompt
        + "\n\n[CODE FILE PATH]\n"
        + local_file_path
        + "\n\n[BEGIN SUBMITTED CODE CONTENT]\n"
        + numbered_content
        + "\n[END SUBMITTED CODE CONTENT]\n\n"
        + context
    )
    log.log_and_print(f"{user_payload}")

    structured_llm = LLM.with_structured_output(PatchSuggestions)
    
    log.log_and_print(f"Calling LLM for patch generation with system prompt...\n{SYSTEM_PROMPT_PYTHON_PROGRAMMER}")
    response = structured_llm.invoke(
        [
            ("system", SYSTEM_PROMPT_PYTHON_PROGRAMMER),
            ("human", user_payload),
        ]
    )

    log.log_and_print(f"vvvvvvvvvvvv Response recived vvvvvvvvvvvv\n\n")
    log.log_and_print("\n--- Generated Snippets ---")
    for suggestion in response.edits:
        log.log_and_print(f"vvvvvvvvvvvvvvvvvvvvvvvv\n")
        log.log_and_print(f"{suggestion}")
    return response


def offline_pipeline_issue(prompt: str,
                           local_project_path: str, 
                           local_issues_path: str,
                           issue_content: str,
                           top_k: int = 2):
    # issue_content = io_utils.get_issue_content(issue_id, local_issues_path)
    # issue_content = f"{issue_content[0]}\n{issue_content[1]}\n{issue_content[2]}" 
    
    context = context_retriever(local_project_path, local_issues_path, issue_content, top_k)

    user_payload = (
        prompt 
        + "\n\n[ISSUE CONTENT]\n"
        + issue_content
        + "\n[END ISSUE CONTENT]\n\n"
        + context
    )
    
    structured_llm = LLM.with_structured_output(PatchSuggestions)

    log.log_and_print("Calling LLM...\n")
    response = structured_llm.invoke(
        [
            ("system", SYSTEM_PROMPT_PYTHON_PROGRAMMER),
            ("human", user_payload),
        ]
    )
    log.log_and_print(f"Prompt Sent:\n\n{user_payload}\n\n")
    log.log_and_print("Recieving response...\n")
    log.log_and_print("\n--- Generated Snippets ---")
    for suggestion in response.edits:
        log.log_and_print(f"{suggestion}")

    patch_output.pretty_print_response(response)
    return response


def main():
    local_file_path = "codebase/manage.py"
    local_file_response = offline_pipeline_file(OUTPUT_FORMAT + USER_PROMPT_V7, "codebase", "issues/local_issues_summaries.jsonl", local_file_path, top_k=5)
    # local_issue_response= offline_pipeline_issue(USER_PROMPT_V4, "codebase", "issues/local_issues_summaries.jsonl", 1, top_k=5)
    # file_diff_view = evaluation.patch_response_to_diff(local_file_response, local_file_path, "")

    # log.log_and_print(f"vvvvvvvv Git diff view vvvvvvvv\n{file_diff_view}")


if __name__ == "__main__":
    main()
