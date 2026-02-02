# Automated Program Repair with LLMs

A tool for automated code review and patch generation using Large Language Models (LLMs) and Retrieval-Augmented Generation (RAG).

## TODO:

- [x] Git commit naming conventions and best practices
- [ ] How to validate and check my answers?
  - [ ] Ask chatgpt and Gemini about how to measure my program success rate (number 3)
  - [ ] Find things similar to SWE-BENCH
- [ ] Take a look at SWE-Bench to understand how to incorporate it with my program
- [ ] Record and Store statistics about my answers to understand the effectiveness of my work (e.g. different models, prompts, techniques, and so on)
  - [ ] What stats should be stored? → **SWE-bench provides standard metrics!**
  
**Ideas:**

- [ ] Knowledge pssobility (it is simillar to a RAG system)
- [ ] Graph based search - What are the nodes?
- [ ] Relevant files and issues (What best works for each?)
- [ ] RAG: retrieving from {a previously solved issues and problematic files} or {}
- [ ] Prompting techniques: one-shot, few-shot, zero-shot, persona, chain-of-thoughts, and so on.
- [ ] Write tests for the project using something else (LLMs, tools, or programmers...) then fix those parts or functions that are wrong according to these tests.
- [ ] Acting like a human, talking with the model until satisfied. Maybe two models talking with each other, one act as a developer and the other as the tool.

**Providing context:**

- [x] read an issue
- [x] read an issue disscussion
- [x] creating input
  - [x] Look at papers for prompt samples (SWE_FIXER)
  - [x] ask gpt for prompt samples:
    - [x] What prompt can I give to an llm to create a patch code snippet that focuses on different aspects regarding issue resolving, technical debts, code issues, bugs and so on?
    - [x] Take a look at papers focusing on APR and this problem regardless of said aspects
    - [x] I want some prompt that are used for automated program repair in academic contexts
    can you help me find papers and their respective prompts
    - [x] What papers focus on program repair using a github issue
    - [x] In these papers, how they find the buggy or problematic line, function, or hunk of code?
    - [x] yes I meant code review / refactoring / smell detection. but tell me if there are any that suggest fixes in structured output that can be applied to the code in question. In another aspect, tell me if there are any of these code review or APR papers that try to solve a github issue
  - [x] Creating system prompt
  - [x] Creating human prompt
    - [x] A simple similarity search providing most similar files and/or issues to the query(file/issue)
      - [x] Add all files and issues to a vector store using an embedding
      - [x] Search top-k (top-3) issues/files to the query and add to the context
      - [x] What data should be given about the files/issues?
        - [ ] path + file name
        - [ ] Line numbers
        - [ ] Commit message
        - [ ] and so on?(priority/severity?, confidence)

I need a prompt that handles file review and/or issue resolving, either one prompt for both, or two different ones for each of them. Also, the focus of the prompts should be on specific aspects.

I need something to use that prompt
- [ ] cli for creating input (selecting file or issue)

**Output:**

- [x] structured output in json

**Checking answers:**

- [ ] Find a dataset of issues or files with known problems and fixes, either one would suffice for now...
- [ ] Create a simple framework that tests your code using this dataset and record relevant output
- [ ] Log the number of correct answers, token used and recieved, how many times should it be run so it would be valid?(is there any standard?), and compare with other tools and ways

Create API endpoints for:

- [ ] Getting a file in POST and sending back response(not sure in another enpoint or not)
- [ ] Getting an issue and ...

export HTTPS_PROXY='http://username:password@proxy_uri:port'

```python
from langchain_google_genai import ChatGoogleGenerativeAI

model = ChatGoogleGenerativeAI(
    model="gemini-3-pro-preview",
    client_args={"proxy": "socks5://user:pass@host:port"},
)
```

Below snippet gave me an idea on how to select different options for the user for patching e.g. code smells or bugs. Anything that user choose can be put into the curly braces {}, so python adds that option to the system prompt.

```python
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
 
# Initialize model
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0,
)
 
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant that translates {input_language} to {output_language}."),
    ("human", "{input}"),
])
 
chain = prompt | llm
result = chain.invoke({
    "input_language": "English",
    "output_language": "German",
    "input": "I love programming.",
})
print(result.content)  # Output: Ich liebe Programmieren.
```

```
  Simple Code Review Prompt: Provide a succinct analysis of the code snippet below. Only offer comments
if significant concerns are identified, ensuring brevity
without vagueness. Do not describe the functionality
of the code. Avoid generating new code. Focus solely
on critical evaluation. If the code is satisfactory, refrain
from commenting.

  Detailed Code Review Prompt: As a code reviewer, con-
duct a thorough analysis of the provided code snippet to
identify any significant issues, including but not limited
to: runtime errors and edge cases, logic flaws and poten-
tial bugs, algorithm correctness, gaps in error handling,
architecture and design patterns, naming conventions
and readability, performance concerns, maintainability
issues. If any critical issues are discovered, regardless of
category, provide a concise review in approximately 200
words. If no issues are found, please state this explicitly.
```

Pricing of gemini models:
<https://ai.google.dev/gemini-api/docs/pricing>

models/gemini-2.5-flash
models/gemini-2.5-pro
models/gemini-2.0-flash
models/gemini-2.0-flash-001
models/gemini-2.0-flash-lite-001
models/gemini-2.0-flash-lite
models/gemini-exp-1206
models/gemini-2.5-flash-preview-tts
models/gemini-2.5-pro-preview-tts
models/gemma-3-1b-it
models/gemma-3-4b-it
models/gemma-3-12b-it
models/gemma-3-27b-it
models/gemma-3n-e4b-it
models/gemma-3n-e2b-it
models/gemini-flash-latest
models/gemini-flash-lite-latest
models/gemini-pro-latest
models/gemini-2.5-flash-lite
models/gemini-2.5-flash-image
models/gemini-2.5-flash-preview-09-2025
models/gemini-2.5-flash-lite-preview-09-2025
models/gemini-3-pro-preview
models/gemini-3-flash-preview
models/gemini-3-pro-image-preview
models/nano-banana-pro-preview
models/gemini-robotics-er-1.5-preview
models/gemini-2.5-computer-use-preview-10-2025
models/deep-research-pro-preview-12-2025

## Git Commit Naming Conventions

This project follows **Conventional Commits** format for clear, semantic commit history:

```
<type>(<scope>): <subject>
```

**Types:**

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `refactor`: Code refactoring (no feature/fix)
- `test`: Adding/updating tests
- `chore`: Dependencies, build, tooling
- `ci`: CI/CD configuration
- `perf`: Performance improvements
- `style`: Code formatting (no logic change)

**Scopes** (module names):

- `github-utils`, `io-utils`, `vector-store`, `process-layer`, `patch-output`, `logging`

**Examples:**

```
feat(vector-store): add embeddings caching
fix(io-utils): handle unicode decode errors
refactor(process-layer): extract prompt templates
docs: add architecture diagram
test(patch-output): validate line numbers
```

**Rules:**

- Max 50 characters in subject line
- Use imperative mood ("add" not "adds")
- No period at end of subject
- Reference issues in body: `Fixes: #123`
