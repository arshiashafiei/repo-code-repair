# Code Fixer - Quick Start Guide

## Installation

The project has been converted into a Python library called `code-fixer`. To use it:

### Install in Development Mode
```bash
cd /home/arshia2562/Documents/Uni/Term-8/FP
pip install -e .
```

### Install for Development with Dev Dependencies
```bash
pip install -e ".[dev]"
```

## Package Structure

```
code_fixer/
├── __init__.py              # Main package initialization
├── apply_patch.py           # Patch application and validation
├── bugsinpy_bugs.py         # BugsInPy dataset handling
├── extract_bugsinpy.py      # Extract data from BugsInPy
├── github_utils.py          # GitHub API integration
├── io_utils.py              # File I/O utilities  
├── log.py                   # Logging utilities
├── offline_pipeline.py      # Offline processing pipeline
├── patch_output.py          # Patch output models (Pydantic)
├── process_layer.py         # LLM processing layer
├── prompts.py               # Prompt templates
├── summarize_discussions.py #Discussion summarization
├── swe_bench.py             # SWE-Bench evaluation
└── vector_store.py          # RAG vector store management
```

## Basic Usage

```python
import code_fixer

# Check version
print(code_fixer.__version__)  # 0.1.0

# Build a vector store for RAG
vector_store = code_fixer.build_vector_store(
    codebase_root="./codebase",
    issues_jsonl_path="./issues/issues.jsonl"
)

# Download a codebase from GitHub
code_fixer.download_codebase(
    repo_url="https://github.com/owner/repo",
    ref="main"  # or commit hash
)

# Compute patch quality metrics
metrics = code_fixer.compute_patch_metrics(
    candidate_patch="...",
    reference_patch="..."
)
```

## Using Specific Modules

```python
# GitHub utilities
from code_fixer.github_utils import download_codebase, get_commit_date_posix

# Vector store
from code_fixer.vector_store import build_vector_store

# SWE-Bench evaluation
from code_fixer.swe_bench import compute_patch_metrics, apply_patch_suggestions_and_diff

# Patch models
from code_fixer.patch_output import PatchSuggestions, PatchSnippet

# Process layer (LLM interface)
from code_fixer.process_layer import LLM

# Offline pipeline
from code_fixer.offline_pipeline import offline_pipeline_file, offline_pipeline_issue
```

## Examples

See the `examples/` directory for complete usage examples:

- `basic_usage.py` - Complete workflow example  
- `analyze_file.py` - Analyze a single file for issues
- `evaluate_patch.py` - Evaluate patch quality
- `github_integration.py` - GitHub repository integration

## Environment Variables

Create a `.env` file with:

```env
GITHUB_TOKEN=your_github_token
OPENAI_API_KEY=your_openai_key
GOOGLE_API_KEY=your_google_api_key 
```

## Verification

Run the verification script to ensure everything is set up correctly:

```bash
python verify_install.py
```

Expected output:
```
✓✓✓ All tests passed! Package is ready to use. ✓✓✓
```

## Distribution

To build a distributable package:

```bash
python -m build
```

This creates:
- `dist/code_fixer-0.1.0-py3-none-any.whl` (wheel)
- `dist/code_fixer-0.1.0.tar.gz` (source)

Install from the built package:
```bash
pip install dist/code_fixer-0.1.0-py3-none-any.whl
```

## Publishing to PyPI (Optional)

```bash
# Install twine
pip install twine

# Upload to Test PyPI first
twine upload --repository testpy dist/*

# Upload to PyPI
twine upload dist/*
```

## Key Features

✅ **Modular Design**: Each module can be imported independently
✅ **Type Hints**: Full type annotations for better IDE support
✅ **Pydantic Models**: Structured output with validation
✅ **RAG Support**: Built-in vector store for context retrieval
✅ **Multiple LLMs**: Support for OpenAI, Gemini, Ollama, DeepSeek
✅ **SWE-Bench**: Standard evaluation metrics included
✅ **GitHub Integration**: Easy repository cloning and issue fetching

## Next Steps

1. Check out the examples in `examples/`
2. Read the full documentation in `README.md`
3. Configure your LLM API keys in `.env`
4. Start using the library in your projects!

## Troubleshooting

If imports fail, make sure you've installed the package:
```bash
pip install -e .
```

If you see "module not found" errors, check that you're in the correct environment:
```bash
which python
python -c "import code_fixer; print(code_fixer.__version__)"
```

## Support

- GitHub Repository: https://github.com/arshiashafiei/code-fixer
- Issues: https://github.com/arshiashafiei/code-fixer/issues
