# Repository-Level Code Repair

A research implementation of automated program repair using LLMs, repository retrieval, structured patch generation, and patch applicability checks. Developed as part of a bachelor's thesis.

The Python package is named `code_fixer`. The repository also includes a FastAPI backend and two VS Code extensions for inspecting saved repair results.

**Status: research prototype.** Core components are implemented, but the offline issue workflow has known blockers. The current VS Code UI displays existing results, it does not invoke the backend or generate new patches. See [Implementation audit and cleanup guide](PROJECT_AUDIT.md) for verified behavior, defects, and cleanup candidates.

## TL;DR — what it does and how to start

This project explores fixing Python code with an LLM: find relevant repository files and issue discussions, include that context in the model's prompt, generate a patch, and check whether Git can apply it. That retrieved context is the RAG part. A patch that applies still needs tests and human review.

**Backend setup:** install Python 3.12+, Git, and `tree`, then run these commands from the repository root in a fresh checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e . langchain-deepseek rank-bm25
python verify_install.py

export DEEPSEEK_API_KEY='your-key'
export DEEPSEEK_API_KEY2="$DEEPSEEK_API_KEY"
export GITHUB_TOKEN='your-github-token'

python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` to explore the API. For retrieval and repair, also run Ollama on port 11434, download `granite-embedding:latest` with `ollama pull granite-embedding:latest`, and provision Chroma on port 8088. See [retrieval-service setup](#retrieval-services) for the current Compose and client-URL caveats. Starting the API alone does not make those services ready.

**Just browse saved results in VS Code?** Install Node.js/npm and run:

```bash
npm --prefix code_fixer_extension install
npm --prefix code_fixer_extension run compile
```

Launch the extension in an Extension Development Host with this repository as the workspace, then open **Code Fixer: Show Panel**. It needs saved data in `results/`, `issues/`, and `projects/`; no backend or LLM is needed. See [viewer instructions](#vs-code-result-viewer). Its checkout action can discard local changes, so use disposable clones.

**Before running experiments:** this is a prototype, not a verified one-command repair setup. Fresh dependency installation and live services remain unverified; the offline issue workflow has known blockers. Read [the audit](PROJECT_AUDIT.md) first. The benchmark runner produces patches and comparison metrics, but does not run the official SWE-bench test harness.

## What is implemented?

| Capability | Current implementation |
| --- | --- |
| Repository preparation | GitHub metadata access, local Git initialization/fetch, and checkout under `projects/`. |
| Issue context | Download issues/PRs and comments using commit-based time cutoffs; optional LLM discussion summaries. |
| File localization | BM25 retrieves 30 candidate files; AST-derived file descriptions are passed to an LLM for file selection. |
| Semantic retrieval | Granite embeddings through Ollama, overlapping character chunks, and a persistent Chroma collection containing files and optional issues. |
| Patch generation | Separate file and issue functions; Pydantic models represent snippet edits or unified diffs. |
| Validation | Diff-format heuristics, patch sanitization, and optional `git apply --check`. These do not establish behavioral correctness. |
| Benchmark tooling | SWE-bench Lite development-split patch generation, JSONL results, and reference-patch comparison metrics. Official test-harness execution is not integrated. |
| HTTP API | Repository, ingestion, indexing, file-selection, retrieval, repair, and patch-check routes. |
| VS Code UI | Local result/issue browsing, patch display, Git applicability checks, checkout, and patch application. No live LLM/API calls. |

The scanner currently includes Python files and Dockerfiles. This is primarily a Python repair prototype, not a validated general-purpose repair tool for every language.

## Retrieval and generation

The intended issue workflow is:

1. Prepare a repository at a selected commit and collect historical issue data.
2. Retrieve candidate files with BM25 and select target files using an LLM.
3. Retrieve additional code/issue context from Chroma.
4. Combine the issue, target-file contents, retrieved context, and output instructions.
5. Generate a patch, sanitize it, and check whether it applies; retry on failures.

Retrieving repository artifacts and including them in generation prompts is the RAG component. BM25 localization and vector context retrieval are separate stages; the code does not implement a fused sparse/dense ranking algorithm. Patch validation is a separate post-generation step.

**Current exception:** `context_retriever(..., with_tree=False)` returns an empty string because of conditional-expression precedence. The offline issue workflow uses this setting. It also passes the directory `comments` to a reader that expects a JSONL file, which can stop execution earlier. The file workflow and API retrieval route use the default `with_tree=True`. Do not assume historical benchmark runs exercised the intended semantic-context stage without checking their code revision and prompt logs.

## Setup

Run Python commands from the repository root: several helpers use relative data paths.

### Python environment

Use Python 3.12 or newer for the current source syntax; `.python-version` records 3.13.5. The `>=3.9` declaration in `pyproject.toml` is outdated. Dependency resolution on a fresh environment has not been verified.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m pip install langchain-deepseek rank-bm25
python verify_install.py
```

The second install command supplies packages used by the current code but missing from `pyproject.toml`. The verification script checks imports, callable exports, and model availability; it does not test external services or end-to-end repair.

`requirements.txt` is a large environment snapshot with GPU/ML dependencies and is not a minimal installation guide.

### Model credentials

The active constructors in `code_fixer/process_layer.py` use DeepSeek `deepseek-chat`:

```bash
export DEEPSEEK_API_KEY='your-generation-key'
export DEEPSEEK_API_KEY2='your-file-selection-key'
export GITHUB_TOKEN='your-github-token'
```

You can set both DeepSeek variables to the same key. The file-selection constructor reads `DEEPSEEK_API_KEY2` directly; it does not fall back to the first key.

Environment variables must be present in the process. The application does not automatically load `.env`. Other provider configurations appear as imports or commented examples; there is no user-facing provider selector.

Retrieved source code and issue text are sent to the configured generation provider. Embedding runs use the local Ollama service.

### Retrieval services

The current vector-store code uses:

| Service | Address / model |
| --- | --- |
| Ollama | Local port 11434; `granite-embedding:latest` |
| Chroma | `127.0.0.1:8088` |
| File-tree utility | The `tree` executable, invoked by context/tree helpers |

With Ollama running, download its embedding model:

```bash
ollama pull granite-embedding:latest
```

Provision a compatible Chroma server on port 8088 before using vector retrieval. The checked-in Compose file needs correction: its default image reference expands to `chromadb/chroma@latest`, which is not a valid tag reference. Review the image reference and persistence settings before starting it.

The embedding client currently uses `base_url="127.0.0.1:11434"`; an explicit `http://` URL may be needed by the installed client. These live-service connections were not verified in the documentation audit. `CHROMA_HOST` and `CHROMA_PORT` in API configuration do not override the hardcoded vector-store client.

## FastAPI backend

After installing dependencies and exporting credentials:

```bash
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

- Health endpoint: `http://127.0.0.1:8000/`
- Interactive API schema: `http://127.0.0.1:8000/docs`

The health endpoint reports that the application is responding, not that GitHub, Chroma, Ollama, or the LLM provider are ready.

Use the schema to follow this sequence:

1. Register a repository and select a commit.
2. Ingest issues with a commit hash.
3. Build the vector index. The BM25 “build” endpoint only checks eligible files; BM25 is built during retrieval.
4. Call file selection and context retrieval.
5. Supply the selected files, issue text, and returned context to the repair endpoint.
6. Review the resulting patch and use the patch-check endpoints.

The API exposes separate stages, not a single automatic end-to-end route. It has no patch-application endpoint. Use disposable repository clones: the API performs filesystem and Git operations and is intended for local development, without application-level authentication.

## Python usage

### Compare candidate and reference patches

This example uses the implemented metric signature and return keys:

```python
from code_fixer.swe_bench import compute_patch_metrics

candidate = """diff --git a/example.py b/example.py
--- a/example.py
+++ b/example.py
@@ -1 +1 @@
-x = 1
+x = 2
"""
reference = candidate

metrics = compute_patch_metrics(candidate, reference)
print(metrics["exact_match"])  # 1
print(metrics["file_match"])   # 1.0
```

`patch_applicable`, `attempt_number`, and `latency_s` are supplied by the caller; this metric function does not apply patches or run tests.

### Review a local file

After configuring the retrieval services and provider, adapt these paths:

```python
from code_fixer.offline_pipeline import offline_pipeline_file

result = offline_pipeline_file(
    prompt="Review this file and suggest focused bug fixes.",
    local_project_path="projects/example",
    local_issues_path="issues/example/issues.jsonl",
    local_file_path="projects/example/example.py",
    top_k=3,
)
print(result.model_dump_json(indent=2))
```

The issues argument must point to an existing JSONL file, which may be empty. The return value is a `PatchSuggestions` model with `file_path_to_edit` and `edits`, not an object with `.content`. This example is source-checked; live inference has not been verified.

For issue generation, `offline_pipeline_issue` accepts issue **text** via `issue_content`, not an issue number. Its current default output schema conflicts with a later `.patch` access. Use `DiffViewEdits` for unified-diff output after resolving the offline workflow blockers listed in the audit.

## VS Code result viewer

`code_fixer_extension/` is the workspace-relative webview extension. It reads:

- `results/swe_bench_lite_results.jsonl`: saved predictions and metrics.
- `issues/`: local issue records.
- `projects/<repo-name>/`: source files and Git working trees.

It needs Node.js/npm, VS Code, Git, and saved local data. It does not need the API, Ollama, or a running LLM to browse results.

```bash
cd code_fixer_extension
npm install
npm run compile
```

Launch an Extension Development Host with this directory as the extension development path, and open the repository root as its workspace. Then use **Code Fixer: New Repair Run** or **Code Fixer: Show Panel**. These commands load an existing result; they do not start inference. Root-level F5 launch settings may exist locally but are ignored by Git.

**Checkout uses `git checkout -f` and can discard local changes.** Apply writes the displayed patch to the selected clone. Use disposable clones and review patches before applying them.

`custom_extension/` is an alternative tree/diff viewer with hardcoded local paths and benchmark instances. It is not required by the webview extension or Python API.

## Benchmark scope

`code_fixer/swe_bench.py:run_swebench` loads the SWE-bench Lite `dev` split, prepares repositories, generates patches, and writes:

- `results/swe_bench_lite_results.jsonl`
- `results/swe_bench_lite_metrics.jsonl`

Metrics include normalized exact match, edit similarity, BLEU-4 over changed lines, file-set overlap, hunk overlap, line counts, applicability, attempts, and latency.

This runner does **not** execute the official SWE-bench test harness. Patch applicability and textual similarity must not be presented as a test-based resolved rate. A reproducible resolved-rate claim needs separate harness reports and the exact evaluation configuration.

Before running experiments, resolve the offline pipeline bugs and initialize the results JSONL file: the runner opens it for reading before its first append. It also loads an unused second dataset, includes `hints_text` on the first attempt, and skips existing records using only instance ID and model name. Those details affect reproducibility and comparisons across prompts.

## Repository layout

| Path | Purpose |
| --- | --- |
| `code_fixer/` | Retrieval, prompting, patch handling, GitHub ingestion, and benchmark helpers |
| `api/` | FastAPI application and stage-specific routes |
| `code_fixer_extension/` | Local webview result viewer |
| `custom_extension/` | Alternative tree/diff viewer prototype |
| `examples/` | Older examples with known API mismatches; not verified quick starts |
| `combined_pipeline.ipynb` | Experimental notebook |
| `doc.md` | Architecture report; some descriptions exceed current implementation |
| `QUICKSTART.md` | Older setup guide; use this README for current caveats |
| `PROJECT_AUDIT.md` | Verification findings and cleanup recommendations |

## Verification and limitations

The documentation audit checked Python parsing, package imports in an existing environment, the direct API health handler and OpenAPI schema construction, BM25 on a small fixture, metric calculation, real Git dry-run patch checking, and TypeScript compilation. HTTP request handling was not verified. See [the audit](PROJECT_AUDIT.md) for exact results and boundaries.

No dedicated `tests/` suite is present. `test.py` launches a benchmark; it is not a unit test. Cloud generation, GitHub ingestion, live vector retrieval, benchmark resolution, and interactive VS Code behavior were not exercised.

Further limitations include path-based index reuse across commits, truncated retrieved-file context, experimental retry logic, and inconsistent issue-file discovery. The project does not establish automatic technical-debt detection, guaranteed correct repairs, or measured RAG improvement over a no-retrieval baseline.

## License

See [LICENSE](LICENSE), which contains the GNU GPL version 3 text. Package metadata currently advertises MIT and must be reconciled with the intended license before distribution.
