/**
 * Webview HTML for the Code Fixer extension.
 *
 * UI layout (matching the screenshot):
 *  ┌──────────────────────────────────────────────────────────────┐
 *  │  Run #XYZ Details                                           │
 *  ├────────────────────────┬─────────────────────────────────────┤
 *  │ 🎯 Issue Description   │ 📁 Selected Files                  │
 *  ├────────────────────────┴─────────────────────────────────────┤
 *  │ 🌳 File Skeleton / Structure View                            │
 *  ├──────────────────────────────────────────────────────────────┤
 *  │ 🔍 Retrieved Context / Logs                                  │
 *  ├──────────────────────────────────────────────────────────────┤
 *  │ 🛠 Generated Patch                                           │
 *  ├──────────────────────────────────────────────────────────────┤
 *  │ ⚠ git apply Errors        [ ✅ Apply ]  [ ❌ Reject ]        │
 *  └──────────────────────────────────────────────────────────────┘
 */

import * as vscode from "vscode";

export function getWebviewHtml(
  webview: vscode.Webview,
  extensionUri: vscode.Uri,
  instanceIds: string[]
): string {
  const nonce = getNonce();
  const optionsHtml = instanceIds
    .map((id) => `<option value="${escHtml(id)}">${escHtml(id)}</option>`)
    .join("\n");

  return /*html*/ `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta
    http-equiv="Content-Security-Policy"
    content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';"
  />
  <title>Code Fixer</title>
  <style nonce="${nonce}">
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: var(--vscode-font-family, 'Segoe UI', sans-serif);
      font-size: var(--vscode-font-size, 13px);
      color: var(--vscode-foreground, #ccc);
      background: var(--vscode-editor-background, #1e1e1e);
      padding: 16px;
      line-height: 1.5;
    }
    h1 { font-size: 1.4em; margin-bottom: 16px; border-bottom: 1px solid var(--vscode-panel-border, #444); padding-bottom: 8px; }
    h2 { font-size: 1em; margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }

    .card {
      background: var(--vscode-editorWidget-background, #252526);
      border: 1px solid var(--vscode-panel-border, #3c3c3c);
      border-radius: 6px;
      padding: 12px 14px;
      margin-bottom: 12px;
    }
    .card.error { border-color: var(--vscode-errorForeground, #f44); }

    .row { display: flex; gap: 12px; }
    .row > .card { flex: 1; min-width: 0; }

    .setup-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-bottom: 8px;
    }

    label {
      display: block; margin-bottom: 4px; font-weight: 600;
      font-size: 0.92em; color: var(--vscode-descriptionForeground, #aaa);
    }
    input[type="text"], select, textarea {
      width: 100%;
      background: var(--vscode-input-background, #3c3c3c);
      color: var(--vscode-input-foreground, #ccc);
      border: 1px solid var(--vscode-input-border, #555);
      border-radius: 4px;
      padding: 6px 8px;
      font-family: inherit; font-size: inherit;
    }
    select { cursor: pointer; }
    input:focus, select:focus, textarea:focus {
      outline: none; border-color: var(--vscode-focusBorder, #007acc);
    }
    textarea { min-height: 80px; resize: vertical; font-family: inherit; }

    button {
      padding: 6px 16px; border: none; border-radius: 4px;
      font-size: 0.9em; cursor: pointer; color: #fff;
      display: inline-flex; align-items: center; gap: 4px;
    }
    .btn-primary { background: var(--vscode-button-background, #0e639c); }
    .btn-primary:hover { background: var(--vscode-button-hoverBackground, #1177bb); }
    .btn-success { background: #2ea043; }
    .btn-success:hover { background: #3fb950; }
    .btn-danger { background: #da3633; }
    .btn-danger:hover { background: #f85149; }
    .btn-secondary { background: var(--vscode-button-secondaryBackground, #3a3d41); color: var(--vscode-button-secondaryForeground, #ccc); }
    .btn-secondary:hover { background: var(--vscode-button-secondaryHoverBackground, #45494e); }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    .btn-row { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }

    pre {
      background: var(--vscode-textCodeBlock-background, #1a1a1a);
      border: 1px solid var(--vscode-panel-border, #3c3c3c);
      border-radius: 4px;
      padding: 10px 12px; overflow-x: auto;
      font-family: var(--vscode-editor-font-family, 'Cascadia Code', monospace);
      font-size: 0.9em; white-space: pre-wrap; word-break: break-all;
      max-height: 300px; overflow-y: auto;
    }

    .diff-add    { color: #3fb950; }
    .diff-del    { color: #f85149; }
    .diff-hunk   { color: #79c0ff; }
    .diff-header { color: #d2a8ff; font-weight: bold; }

    .status-dot {
      display: inline-block; width: 8px; height: 8px;
      border-radius: 50%; margin-right: 4px;
    }
    .status-dot.idle    { background: #555; }
    .status-dot.loading { background: #e3b341; animation: pulse 1s infinite; }
    .status-dot.done    { background: #3fb950; }
    .status-dot.error   { background: #f85149; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

    #logArea {
      max-height: 200px; overflow-y: auto;
      font-family: var(--vscode-editor-font-family, monospace);
      font-size: 0.85em; line-height: 1.6; padding: 8px;
      background: var(--vscode-textCodeBlock-background, #1a1a1a);
      border-radius: 4px;
    }
    .log-line { margin: 0; }
    .log-line.error   { color: #f85149; }
    .log-line.success { color: #3fb950; }

    .warning-bar {
      background: rgba(227,179,65,0.15);
      border-left: 3px solid #e3b341;
      padding: 8px 12px; border-radius: 0 4px 4px 0;
      margin-bottom: 8px; display: flex; align-items: center; gap: 8px;
    }

    .file-tag {
      display: inline-block;
      background: var(--vscode-badge-background, #4d4d4d);
      color: var(--vscode-badge-foreground, #ccc);
      padding: 2px 8px; border-radius: 3px;
      font-family: var(--vscode-editor-font-family, monospace);
      font-size: 0.9em; margin: 2px;
    }

    .hidden { display: none !important; }

    .action-bar {
      display: flex; justify-content: space-between; align-items: center;
      margin-top: 12px; padding-top: 12px;
      border-top: 1px solid var(--vscode-panel-border, #3c3c3c);
    }
    .flex-end { display: flex; align-items: flex-end; }
    .checkout-btn-wrap { height: 32px; }
    .status-row { margin-top: 8px; display: flex; gap: 12px; flex-wrap: wrap; font-size: 0.85em; }
  </style>
</head>
<body>
  <h1 id="runTitle">Code Fixer</h1>

  <!-- ═══ Setup ═══════════════════════════════════════════════════════ -->
  <div class="card" id="setupCard">
    <h2>⚙️ Configuration</h2>
    <div class="setup-grid">
      <div>
        <label for="instanceSelect">Instance ID</label>
        <select id="instanceSelect">
          <option value="">— select —</option>
          ${optionsHtml}
        </select>
      </div>
      <div>
        <label for="modelSelect">Model</label>
        <select id="modelSelect">
          <option value="">— select instance first —</option>
        </select>
      </div>
    </div>

    <div class="setup-grid">
      <div>
        <label for="commitHashInput">Commit Hash (optional checkout)</label>
        <input id="commitHashInput" type="text" placeholder="e.g. abc123 (leave empty to skip)" />
      </div>
      <div class="flex-end">
        <button class="btn-secondary checkout-btn-wrap" id="btnCheckout">🔀 Checkout</button>
      </div>
    </div>

    <div class="btn-row">
      <button class="btn-primary" id="btnRun" disabled>▶️ Run Pipeline</button>
    </div>

    <div class="status-row">
      <span><span class="status-dot idle" id="dotCheckout"></span>Checkout</span>
      <span><span class="status-dot idle" id="dotResult"></span>Result</span>
      <span><span class="status-dot idle" id="dotIssue"></span>Issue</span>
      <span><span class="status-dot idle" id="dotSelectFiles"></span>Files</span>
      <span><span class="status-dot idle" id="dotSkeleton"></span>Skeleton</span>
      <span><span class="status-dot idle" id="dotContext"></span>Context</span>
      <span><span class="status-dot idle" id="dotRepair"></span>Patch</span>
      <span><span class="status-dot idle" id="dotApplyCheck"></span>Check</span>
    </div>
  </div>

  <!-- ═══ Run Details ════════════════════════════════════════════════ -->
  <div id="runDetails" class="hidden">

    <div class="row">
      <div class="card">
        <h2>🎯 Issue Description</h2>
        <pre id="issueContent">–</pre>
      </div>
      <div class="card">
        <h2>📁 Selected Files</h2>
        <div id="selectedFiles"><em>Waiting…</em></div>
      </div>
    </div>

    <div class="card">
      <h2>🌳 File Skeleton / Structure View</h2>
      <pre id="skeletonArea">Waiting…</pre>
    </div>

    <div class="card">
      <h2>🔍 Retrieved Context / Logs</h2>
      <pre id="contextArea">(Context strings, summaries, logs as formatted HTML)</pre>
    </div>

    <div class="card" id="patchCard">
      <h2>🛠 Generated Patch</h2>
      <pre id="patchContent">Waiting for patch…</pre>
    </div>

    <div id="applyErrorBar" class="warning-bar hidden">
      <span>⚠</span>
      <span id="applyErrorText">git apply Errors</span>
    </div>

    <div class="action-bar" id="actionBar">
      <div></div>
      <div class="btn-row">
        <button class="btn-success" id="btnApply" disabled>✅ Apply</button>
        <button class="btn-danger"  id="btnReject" disabled>❌ Reject</button>
      </div>
    </div>
  </div>

  <!-- ═══ Logs ══════════════════════════════════════════════════════ -->
  <div class="card">
    <h2>📋 Activity Log</h2>
    <div id="logArea"></div>
  </div>

  <!-- ═══ Script ════════════════════════════════════════════════════ -->
  <script nonce="${nonce}">
  (function () {
    const vscode = acquireVsCodeApi();
    const $ = (id) => document.getElementById(id);

    const instanceSelect = $("instanceSelect");
    const modelSelect    = $("modelSelect");
    const commitHash     = $("commitHashInput");
    const btnCheckout    = $("btnCheckout");
    const btnRun         = $("btnRun");
    const btnApply       = $("btnApply");
    const btnReject      = $("btnReject");
    const runTitle       = $("runTitle");
    const runDetails     = $("runDetails");
    const issueContent   = $("issueContent");
    const selectedFiles  = $("selectedFiles");
    const skeletonArea   = $("skeletonArea");
    const contextArea    = $("contextArea");
    const patchContent   = $("patchContent");
    const patchCard      = $("patchCard");
    const applyErrorBar  = $("applyErrorBar");
    const applyErrorText = $("applyErrorText");
    const logArea        = $("logArea");

    let currentPatch = "";
    let currentInstanceId = "";

    // ── Status dots ───────────────────────────────────────────
    const dotMap = {
      checkout:    $("dotCheckout"),
      result:      $("dotResult"),
      issue:       $("dotIssue"),
      selectFiles: $("dotSelectFiles"),
      skeleton:    $("dotSkeleton"),
      context:     $("dotContext"),
      repair:      $("dotRepair"),
      applyCheck:  $("dotApplyCheck"),
    };
    function setDot(stage, state) {
      const d = dotMap[stage];
      if (d) d.className = "status-dot " + state;
    }

    // ── Logging ───────────────────────────────────────────────
    function addLog(text) {
      const p = document.createElement("p");
      p.className = "log-line";
      if (text.includes("✓")) p.classList.add("success");
      if (text.includes("✗") || text.includes("failed")) p.classList.add("error");
      p.textContent = text;
      logArea.appendChild(p);
      logArea.scrollTop = logArea.scrollHeight;
    }

    // ── Diff highlighting ─────────────────────────────────────
    function highlightDiff(raw) {
      return raw.split("\\n").map(function (line) {
        if (line.startsWith("diff --git")) return '<span class="diff-header">' + esc(line) + '</span>';
        if (line.startsWith("@@"))         return '<span class="diff-hunk">'   + esc(line) + '</span>';
        if (line.startsWith("+"))          return '<span class="diff-add">'    + esc(line) + '</span>';
        if (line.startsWith("-"))          return '<span class="diff-del">'    + esc(line) + '</span>';
        return esc(line);
      }).join("\\n");
    }
    function esc(s) {
      return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    }

    // ── Instance changed → fetch models ───────────────────────
    instanceSelect.addEventListener("change", function () {
      const id = instanceSelect.value;
      currentInstanceId = id;
      if (!id) {
        modelSelect.innerHTML = '<option value="">— select instance —</option>';
        btnRun.disabled = true;
        return;
      }
      vscode.postMessage({ type: "getModels", instanceId: id });
    });

    modelSelect.addEventListener("change", function () {
      btnRun.disabled = !(instanceSelect.value && modelSelect.value);
    });

    // ── Checkout ──────────────────────────────────────────────
    btnCheckout.addEventListener("click", function () {
      const ch = commitHash.value.trim();
      const iid = instanceSelect.value;
      if (!ch) { addLog("Enter a commit hash first."); return; }
      if (!iid) { addLog("Select an instance first."); return; }
      // Derive repoName from instance_id: "owner__repo-123" → "repo"
      var parts = iid.split("__");
      var rest = parts[1];
      var segs = rest.split("-");
      segs.pop(); // remove issue number
      var repoName = segs.join("-");
      vscode.postMessage({ type: "checkout", repoName: repoName, commitHash: ch });
    });

    // ── Run pipeline ──────────────────────────────────────────
    btnRun.addEventListener("click", function () {
      var iid = instanceSelect.value;
      var model = modelSelect.value;
      if (!iid || !model) { addLog("Select instance and model."); return; }

      runDetails.classList.remove("hidden");
      btnApply.disabled = true;
      btnReject.disabled = true;
      currentPatch = "";
      applyErrorBar.classList.add("hidden");
      patchContent.textContent = "Loading…";
      selectedFiles.innerHTML = "<em>Loading…</em>";
      skeletonArea.textContent = "Loading…";
      contextArea.textContent = "Loading…";
      issueContent.textContent = "Loading…";

      Object.keys(dotMap).forEach(function (k) { setDot(k, "idle"); });

      vscode.postMessage({ type: "runPipeline", instanceId: iid, model: model });
    });

    // ── Apply / Reject ────────────────────────────────────────
    btnApply.addEventListener("click", function () {
      vscode.postMessage({ type: "applyPatch", patch: currentPatch, instanceId: currentInstanceId });
    });
    btnReject.addEventListener("click", function () {
      vscode.postMessage({ type: "rejectPatch" });
    });

    // ── Incoming messages ─────────────────────────────────────
    window.addEventListener("message", function (event) {
      var msg = event.data;
      switch (msg.type) {
        case "log":
          addLog(msg.text);
          break;

        case "status":
          setDot(msg.stage, msg.state);
          break;

        case "modelsList":
          modelSelect.innerHTML = msg.models
            .map(function (m) { return '<option value="' + esc(m) + '">' + esc(m) + '</option>'; })
            .join("");
          btnRun.disabled = !(instanceSelect.value && modelSelect.value);
          break;

        case "runStarted":
          runTitle.textContent = "Run " + msg.runId + " Details";
          currentInstanceId = instanceSelect.value;
          break;

        case "issueLoaded":
          issueContent.textContent = msg.text;
          break;

        case "filesSelected":
          selectedFiles.innerHTML = msg.files
            .map(function (f) { return '<span class="file-tag">' + esc(f) + '</span>'; })
            .join(" ");
          break;

        case "fileTree":
          // tree is shown inside skeleton area as secondary info
          break;

        case "skeletonLoaded":
          skeletonArea.textContent = msg.skeleton;
          break;

        case "contextLoaded":
          contextArea.textContent = msg.context;
          break;

        case "patchGenerated":
          currentPatch = msg.patch;
          if (msg.instanceId) currentInstanceId = msg.instanceId;
          patchContent.innerHTML = highlightDiff(msg.patch);
          btnApply.disabled = false;
          btnReject.disabled = false;
          break;

        case "applyCheckResult":
          if (!msg.appliesCleanly) {
            applyErrorBar.classList.remove("hidden");
            applyErrorText.textContent = "git apply Errors: " + msg.message;
            patchCard.classList.add("error");
          } else {
            applyErrorBar.classList.add("hidden");
            patchCard.classList.remove("error");
          }
          break;
      }
    });
  })();
  </script>
</body>
</html>`;
}

function getNonce(): string {
  let text = "";
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  for (let i = 0; i < 32; i++) {
    text += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return text;
}

function escHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
