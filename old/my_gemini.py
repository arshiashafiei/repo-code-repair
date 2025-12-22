import getpass
import os
from langchain_google_genai import ChatGoogleGenerativeAI


import datetime

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from typing_extensions import Annotated, TypedDict


from github_utils import read_issue_title_and_description
from prompt import generate_retrieval_prompt_from_paths
from retrieval_bm25 import bm25_top_k_files_for_issue


def log_and_print(msg):
    filename = f"log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, "a") as f:
        f.write(msg + "\n")
    print(msg)


if "GEMINI_API_KEY" not in os.environ:
    os.environ["GEMINI_API_KEY"] = getpass.getpass("Enter your Google AI API key: ")


llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
    # other params...
)


# prompt = ChatPromptTemplate.from_messages(
#     [
#         (
#             "system",
#             "You are a helpful assistant that translates {input_language} to {output_language}.",
#         ),
#         ("human", "{input}"),
#     ]
# )

class IssueList(TypedDict):
    files_for_editing: Annotated[list[str], [], "files for editing"]


structured_llm = llm.with_structured_output(IssueList)


if __name__ == "__main__":
    issue_text = read_issue_title_and_description(issue_number=8, log=True)
    bm25_retrieved = bm25_top_k_files_for_issue(issue_text=issue_text)
    message = generate_retrieval_prompt_from_paths(file_paths=bm25_retrieved, readme_path="README.md", issue_text=issue_text)
    result = structured_llm.invoke("Tell me a joke about cats")

    print(result)



