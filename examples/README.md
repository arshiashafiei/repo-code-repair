# Code Fixer Examples

This directory contains example scripts demonstrating how to use the `code_fixer` library.

## Examples

### 1. Basic Usage (`basic_usage.py`)
Demonstrates the complete workflow:
- Fetching GitHub issues
- Building a vector store
- Generating patch suggestions

```bash
python examples/basic_usage.py
```

### 2. Analyze File (`analyze_file.py`)
Shows how to analyze a single file for code issues:
- Bug detection
- Code smell identification
- Best practice violations

```bash
python examples/analyze_file.py
```

### 3. Evaluate Patch (`evaluate_patch.py`)
Demonstrates patch quality evaluation using SWE-Bench metrics:
- Computing similarity metrics
- Comparing candidate vs reference patches
- Understanding different evaluation criteria

```bash
python examples/evaluate_patch.py
```

### 4. GitHub Integration (`github_integration.py`)
Shows repository management:
- Cloning repositories
- Fetching issues and comments
- Preparing codebases for analysis

```bash
python examples/github_integration.py
```

## Setup

Before running the examples:

1. Install the library:
```bash
pip install -e .
```

2. Set up environment variables:
```bash
export GITHUB_TOKEN=your_github_token
export OPENAI_API_KEY=your_openai_key
# or
export GOOGLE_API_KEY=your_google_key
```

3. Modify the configuration variables in each script:
   - Repository URLs
   - Issue numbers
   - File paths
   - Project directories

## Tips

- Start with `github_integration.py` to set up a test repository
- Use `analyze_file.py` for quick file-level analysis
- Use `basic_usage.py` for issue-driven patch generation
- Use `evaluate_patch.py` to measure quality of generated patches

## Customization

Each example includes configuration variables at the top of the file. Modify these to:
- Use different repositories
- Analyze different files
- Adjust retrieval parameters (`top_k`)
- Change LLM models and prompts
