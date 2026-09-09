# Implementation audit and cleanup guide

Audit date: 2026-09-09. This review covers the current working tree, including untracked API/extension code and pre-existing Python edits. It is not a certification of past experiment results.

The root README was rewritten against source and targeted checks. Runtime code and existing research artifacts were not changed or deleted. References below use function names so that they remain useful as line numbers move.

## Verification

| Check | Result / scope |
| --- | --- |
| Parse Python source | 31 application, example, and entry-point files parsed successfully with the available Python interpreter. This does not prove compatibility with Python 3.9. |
| `.notebook/bin/python verify_install.py` | Passed imports, callable exports, and Pydantic model availability. This is the usable existing environment found during the audit. |
| `.venv/bin/python verify_install.py` | Failed: missing `github` module (PyGithub). |
| `.venv2/bin/python verify_install.py` | Failed: missing `langchain_deepseek`. |
| Webview extension | `code_fixer_extension/node_modules/.bin/tsc --noEmit -p code_fixer_extension` passed. |
| Alternative extension | `custom_extension/node_modules/.bin/tsc --noEmit -p custom_extension` passed. |
| Context assembly | Executed the actual `context_retriever` function with stubbed storage/file dependencies: retrieved content appears with `with_tree=True`; `with_tree=False` returns an empty string. |
| Metric helpers | Executed source-isolated actual functions: identical patches match, an empty candidate differs, and old `candidate_patch`/`reference_patch` keywords raise `TypeError`. |
| Structural validator | Source-isolated actual function accepts a simple diff and rejects non-diff text. |
| API import and schema | Actual application imports; direct health handler returns `ok`; OpenAPI construction exposes 13 paths. HTTP request handling was not verified (an initial TestClient run was interrupted). |
| Real BM25 and AST extraction | Passed on one disposable Python file using installed dependencies in `.notebook`. No LLM selection was invoked. |
| Real Git patch validation | Matching diff passed `git apply --check`, mismatched diff failed, and the fixture file remained unchanged. |
| Imported metric function | Actual installed-environment import and positional-call example passed. |

Isolated checks execute real function bodies but do not establish service integration. No paid generation, network ingestion, actual vector search, official benchmark harness, or interactive VS Code session was run. There is no dedicated `tests/` suite; `test.py` invokes the benchmark and should not be described as a unit test.

## Findings that affect documented behavior

### Offline issue repair needs fixes

In [process_layer.py](code_fixer/process_layer.py), `context_retriever` builds its return value with a trailing `if with_tree else ""`. Python applies that conditional to the entire concatenation, so turning off the tree turns off all context. This was reproduced with the actual function body.

[offline_pipeline.py](code_fixer/offline_pipeline.py), `offline_pipeline_issue`, explicitly sets `with_tree=False`. It also sets `with_summary=True, comments_path="comments"`; [summarize_discussions.py](code_fixer/summarize_discussions.py), `load_comments`, opens that path as a file. In this workspace it is a directory, so the reader raises `IsADirectoryError` if reached.

The same issue function raises `ValueError` when a nonempty file selection **exists**, leading to unnecessary retries. Its default `PatchSuggestions` output is later accessed via `.patch`, which belongs to `DiffViewEdits`. The current benchmark supplies `DiffViewEdits`, but default library calls do not.

These findings qualify the earlier RAG explanation: the repository implements RAG components and a file-context path, but the current offline issue path cannot be assumed to deliver semantic context to generation. They do not establish which revision produced historical results.

### Setup metadata is inconsistent

- [pyproject.toml](pyproject.toml) omits the actively imported `langchain-deepseek` and BM25's `rank-bm25` requirement. The latter is present in `requirements.txt`; the former is not. The README includes an explicit installation workaround.
- Python 3.9 metadata conflicts with union annotations and same-quote f-string expressions that require newer Python. Current source requires at least Python 3.12 syntax support; clean installation still needs testing.
- FastAPI and Uvicorn dependencies are each declared twice with different lower bounds.
- No active `load_dotenv` call was found. Credentials must be exported or explicitly loaded by the caller.
- Active generation/file-selection constructors use DeepSeek and separate key variables. Commented provider configurations are not a provider-selection feature.
- [docker-compose.yml](docker-compose.yml) defaults to `chromadb/chroma@latest`, an invalid image reference. Do not delete the file merely because it needs correction.
- The Chroma client ignores the API's host/port settings. Ollama's base URL lacks a scheme; client acceptance was not established.
- [LICENSE](LICENSE) contains GPL v3 text, but the package classifier says MIT. Resolve the intended license before publishing; this audit does not choose one.

### The VS Code extension is a saved-results viewer

[code_fixer_extension/src/panel.ts](code_fixer_extension/src/panel.ts), `cmdRunPipeline`, loads saved predictions. It derives selected files from the stored patch, shows the first 30 lines as a “skeleton,” and displays metrics as “context.” These are not live BM25, AST-skeleton retrieval, or LLM-generation stages.

The extension does implement Git checks/application and force checkout. Its manifest has no `apiBaseUrl` setting. The extension README's API workflow is stale; the root README now describes actual behavior.

Both extensions use force checkout. In `custom_extension`, even the diff-view flow checks out the base commit. Keep working changes out of their target clones. The webview's dry run writes and removes a fixed `.tmp_patch.diff` inside the project; it could overwrite a pre-existing file with that name.

### Benchmark support is generation and comparison, not integrated test execution

[swe_bench.py](code_fixer/swe_bench.py), `run_swebench`, loads the Lite development split, generates patches, checks applicability, and records comparison metrics. No official SWE-bench harness invocation was found in the Python runner. Recorded metrics alone do not substantiate test-based resolved rates reported in the thesis.

Additional reproducibility concerns:

- It opens the results JSONL file for reading before creating it on a first run.
- It loads `MariusHobbhahn/swe-bench-verified-mini` into an unused variable.
- Its first attempt includes `hints_text`; later attempts do not. Record that protocol when comparing results.
- Resume keys include instance and model, but not prompt/retrieval settings; different experiments can be skipped accidentally.
- A nonempty Chroma collection is reused by path, without a commit/content version. Retrieval can be stale after checkout or ingestion changes.
- Context selection finds chunks but sends the first 4,000 characters of the source file, potentially omitting the actual matched region.
- Hunk-overlap metrics compare line ranges without retaining their file identity. Treat them cautiously for multifile patches.

Patch format/applicability checks are implemented. Automatic program test execution, guaranteed syntax/semantic correctness, proactive technical-debt detection, and demonstrated RAG uplift are not established by these checks.

### API stages exist, with integration gaps

The API contains register/checkout/tree, ingestion, indexing, selection, retrieval, repair, and validation routes. Repair expects the caller to supply issue text, selected files, and retrieved context. There is no single full-pipeline route or patch-apply route.

Ingestion accepts `since_timestamp` but does not forward it to the commit-based helper; use a commit hash. Its `state` value is reduced to an `only_closed` boolean rather than a complete state filter. Fallback issue-file discovery can select the newest file from a shared directory without matching the repository. Repo IDs use only the repository name, so different owners with identical repo names can collide. Relative paths assume the repository root as the working directory.

## Cleanup candidates

“No references found” means no active references were found in the application sources/configuration inspected. It cannot account for personal scripts, external consumers, or unpublished experiments. Archive original research evidence before deleting it.

### Low-risk, optional cleanup

| Path | Evidence and removal condition |
| --- | --- |
| `vscode-extension/` (~99 MB) | Downloaded tutorials and upstream ZIP archives; no application dependency found. Remove or move to personal reference storage if no longer useful. This is different from `code_fixer_extension/`. |
| `test.py` | Thin `run_swebench()` launcher, not a test. Optional to remove if no personal task launches it; module execution already exists. |
| `__pycache__/`, `*.pyc`, `code_fixer.egg-info/` | Generated files. Regenerable by Python/editable installation. Close relevant running processes first. |
| Extension `out/` directories | Generated JavaScript; recompile before launching an extension again. |
| Extension `node_modules/` directories | Reinstallable dependencies, but removal prevents local compilation/use until restored. Keep package manifests and lockfiles. |
| `setup.py` | Only calls `setuptools.setup()`; optional compatibility shim if all packaging uses `pyproject.toml`. Retain it if an older external workflow requires it. |

### Archive or decide before removal

| Path | Why it is not automatically safe to delete |
| --- | --- |
| `custom_extension/` | Independent older-style viewer with absolute machine paths and hardcoded instances; the backend/webview do not depend on it. It also offers a tree/native-diff UI, so archive it if that capability is no longer needed. It was untracked during this audit: Git cannot recover uncommitted files. |
| `combined_pipeline.ipynb` | Contains experiment code and stored outputs. May preserve research provenance or behavior missing from modules. Archive before removing. |
| `results/bkup.jsonl` | No runtime reference found, but the filename does not prove it duplicates other results. Compare records before removal. It has uncommitted changes. |
| `results/swe_bench_lite_results.jsonl` | Read by the runner for resume and both viewers for predictions. Keep for experiments/demos. |
| `results/swe_bench_lite_metrics.jsonl` | Research output; preserve for reporting/reproducibility, even though generation can write new records. |
| `QUICKSTART.md`, `examples/`, `code_fixer_extension/README.md`, `doc.md` | Stale or overstated documentation, not unused runtime modules. Update or consolidate; if removing, repair links in README, examples documentation, and `MANIFEST.in`. |
| `requirements.txt` | Large frozen environment, possibly useful for reconstructing experiments. Do not prune GPU/ML packages solely because they have no direct import: some are transitive dependencies. Consolidate only after a clean install/build test. |

The old examples contain concrete failures: nonexistent `get_github_client`, `fetch_issue`, `fetch_issue_comments`, and `clone_repo` imports; unsupported issue-number/clone keyword arguments; `.content` access on Pydantic results; wrong metric argument names and return keys. They should not be linked as working tutorials.

### Do not remove these wholesale

- `code_fixer/bugsinpy_bugs.py`: older experimental runner, but `swe_bench.py` still imports its `apply_patch` symbol. That import appears unused; remove/refactor it and verify package imports before removing the module. Its runner also uses a stale imported `LLM = None` value.
- `bugsinpy_bugs.jsonl`: consumed by the BugsInPy runner. Remove only if retiring that workflow and preserving any needed dataset provenance.
- `code_fixer/extract_bugsinpy.py`: standalone dataset-conversion utility, not duplicate runtime code merely because it lacks a caller. Optional only if BugsInPy preparation is retired.
- `.notebook/` (~7.8 GB): a Python environment, not just notebook outputs. It was the only tested environment that passed package verification. Keep until a replacement is validated.
- `.venv/` (~7.7 GB), `.venv2/` (~6.2 GB): possible environment consolidation candidates; both currently fail import verification, but may retain dependencies or editor/kernel bindings needed elsewhere. Recreate and validate a chosen environment before removing old ones.
- `chroma-data/` (~2.1 GB): persistent retrieval data; deleting requires re-embedding/reindexing and loses the current index state.
- `projects/`, `issues/`, `comments/`, `summarized_issues/`, `logs/`: runtime/research data. Clones may contain manual or generated changes, and logs may be the only record of prompts. Back up before purging.
- `api/` and `code_fixer_extension/`: implemented components, both untracked at audit time. Preserve or commit them deliberately.

### Code-level cleanup after checking callers

- `process_layer.context_retriever_both`: no caller found. It overwrites an initial search with file-only MMR results, so its later issue branch cannot supply issues. Candidate for removal or repair.
- The demo entry point at the end of `process_layer.py` accesses `LLM.with_structured_output` while `LLM` starts as `None`. Retire or update this demo; preserve the module used by the application.
- Large commented provider/CLI alternatives in `process_layer.py`, `vector_store.py`, and `github_utils.py` can be moved to a small configuration/example document after retaining any unique information.
- The unused benchmark dataset load can be removed independently of the rest of the benchmark runner.

## Repository hygiene

`.env` is already tracked and is not covered by the current root `.gitignore`. Its contents were not inspected or printed. Check it privately before sharing the repository; if it contains real credentials, remove it from tracking and address any exposed credentials/history. Adding an ignore rule alone will not untrack an existing file.

The three results files are also already tracked despite the `results/` ignore rule. Decide explicitly whether to publish curated research results. `api/`, both extension sources, the PDF, `test.py`, and downloaded references were untracked. Cleanup cannot rely on Git recovery for those files.

Suggested order: preserve thesis/results and untracked source, repair pipeline/setup blockers, validate one reproducible environment, then remove reference downloads, redundant environments, and retired prototypes. No deletion is necessary to use the revised README.
