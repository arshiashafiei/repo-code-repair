# Code Fixer – VS Code Extension

A VS Code extension for automated program repair powered by LLMs and RAG. Provides a webview-based UI to interact with the Code Fixer FastAPI backend.

## Features

- **Register & clone** GitHub repositories via the API
- **Checkout** specific commits for historical analysis
- **Ingest** GitHub issues and comments with optional summarization
- **Build** vector (ChromaDB) and BM25 search indexes
- **Run the full repair pipeline**: file selection → context retrieval → LLM patch generation → validation
- **View generated patches** with diff syntax highlighting
- **Apply / Reject** patches with `git apply` dry-run verification
- **Activity log** for real-time pipeline progress

## Prerequisites

- The **Code Fixer FastAPI backend** must be running (default: `http://localhost:8000`)
  ```bash
  cd /path/to/code-fixer
  uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
  ```
- **ChromaDB** server running on port 8088 (for vector index operations)
- **Ollama** with the `granite-embedding:latest` model (for embeddings)

## Getting Started

1. **Install dependencies & compile**
   ```bash
   cd code_fixer_extension
   npm install
   npm run compile
   ```

2. **Launch the extension** in VS Code
   - Press `F5` to open a new Extension Development Host window
   - Or package with `npx @vscode/vsce package`

3. **Open the panel**
   - Command Palette → `Code Fixer: New Repair Run`

4. **Workflow**
   1. Enter the GitHub repo URL and click **Register Repo**
   2. Enter the Repo ID and Commit Hash, click **Checkout**
   3. Click **Ingest Issues** to fetch issues from GitHub
   4. Click **Build Indexes** to create vector + BM25 indexes
   5. Enter an Issue Number and click **Run Pipeline**
   6. Review the generated patch and click **Apply** or **Reject**

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `codeFixer.apiBaseUrl` | `http://localhost:8000` | Base URL of the FastAPI backend |

## Development

```bash
npm run watch   # Compile TypeScript in watch mode
```

Press `F5` in VS Code to launch the Extension Development Host.
