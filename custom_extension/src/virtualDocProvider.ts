import * as vscode from "vscode";

/**
 * A virtual-document content provider that serves in-memory text content.
 * Used to feed the "original" and "modified" sides of the diff viewer
 * without needing actual files on disk.
 */
export class VirtualDocumentProvider implements vscode.TextDocumentContentProvider {
  private _content = new Map<string, string>();
  private _onDidChange = new vscode.EventEmitter<vscode.Uri>();

  readonly onDidChange = this._onDidChange.event;

  /**
   * Store content that can later be resolved by URI.
   * @param uri  must use the scheme registered for this provider
   * @param content  the text to return when VS Code opens this URI
   */
  setContent(uri: vscode.Uri, content: string): void {
    this._content.set(uri.toString(), content);
    this._onDidChange.fire(uri);
  }

  provideTextDocumentContent(uri: vscode.Uri): string {
    return this._content.get(uri.toString()) ?? "";
  }

  dispose(): void {
    this._onDidChange.dispose();
  }
}
