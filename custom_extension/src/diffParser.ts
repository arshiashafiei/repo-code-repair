/**
 * Parses a unified diff string into structured file-level patches,
 * and provides utilities to apply patches to original file content.
 */

export interface FilePatch {
  oldPath: string;
  newPath: string;
  hunks: Hunk[];
}

export interface Hunk {
  oldStart: number;
  oldCount: number;
  newStart: number;
  newCount: number;
  lines: HunkLine[];
}

export interface HunkLine {
  type: "context" | "add" | "remove";
  content: string;
}

/**
 * Parse a unified diff (possibly multi-file) into an array of FilePatch objects.
 */
export function parseUnifiedDiff(diff: string): FilePatch[] {
  const patches: FilePatch[] = [];
  const lines = diff.split("\n");
  let i = 0;

  while (i < lines.length) {
    if (lines[i].startsWith("diff --git")) {
      const patch = parseOneFile(lines, i);
      if (patch) {
        patches.push(patch.filePatch);
        i = patch.nextIndex;
        continue;
      }
    }
    i++;
  }

  return patches;
}

function parseOneFile(
  lines: string[],
  start: number
): { filePatch: FilePatch; nextIndex: number } | null {
  let i = start + 1;

  let oldPath = "";
  let newPath = "";

  while (i < lines.length && !lines[i].startsWith("@@")) {
    if (lines[i].startsWith("--- a/")) {
      oldPath = lines[i].slice(6);
    } else if (lines[i].startsWith("--- /dev/null")) {
      oldPath = "/dev/null";
    } else if (lines[i].startsWith("+++ b/")) {
      newPath = lines[i].slice(6);
    } else if (lines[i].startsWith("+++ /dev/null")) {
      newPath = "/dev/null";
    }
    i++;
  }

  if (!oldPath && !newPath) {
    return null;
  }

  const hunks: Hunk[] = [];

  while (i < lines.length && !lines[i].startsWith("diff --git")) {
    if (lines[i].startsWith("@@")) {
      const hunkHeader = lines[i];
      const match = hunkHeader.match(
        /@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/
      );
      if (match) {
        const hunk: Hunk = {
          oldStart: parseInt(match[1], 10),
          oldCount: match[2] !== undefined ? parseInt(match[2], 10) : 1,
          newStart: parseInt(match[3], 10),
          newCount: match[4] !== undefined ? parseInt(match[4], 10) : 1,
          lines: [],
        };
        i++;
        while (
          i < lines.length &&
          !lines[i].startsWith("@@") &&
          !lines[i].startsWith("diff --git")
        ) {
          const line = lines[i];
          if (line.startsWith("+")) {
            hunk.lines.push({ type: "add", content: line.slice(1) });
          } else if (line.startsWith("-")) {
            hunk.lines.push({ type: "remove", content: line.slice(1) });
          } else if (line.startsWith(" ") || line === "") {
            hunk.lines.push({
              type: "context",
              content: line.startsWith(" ") ? line.slice(1) : line,
            });
          }
          i++;
        }
        hunks.push(hunk);
        continue;
      }
    }
    i++;
  }

  return {
    filePatch: { oldPath, newPath, hunks },
    nextIndex: i,
  };
}

/**
 * Apply a list of hunks to original file content to produce the modified file content.
 * This does a line-level patch application matching hunk oldStart positions.
 */
export function applyPatch(originalContent: string, hunks: Hunk[]): string {
  const originalLines = originalContent.split("\n");
  const resultLines: string[] = [];

  // Sort hunks by oldStart ascending
  const sortedHunks = [...hunks].sort((a, b) => a.oldStart - b.oldStart);

  let currentOrigLine = 0; // 0-indexed pointer into originalLines

  for (const hunk of sortedHunks) {
    const hunkStart = hunk.oldStart - 1; // convert 1-based to 0-based

    // Copy all lines before this hunk from the original
    while (currentOrigLine < hunkStart && currentOrigLine < originalLines.length) {
      resultLines.push(originalLines[currentOrigLine]);
      currentOrigLine++;
    }

    // Apply hunk lines
    for (const line of hunk.lines) {
      switch (line.type) {
        case "context":
          resultLines.push(originalLines[currentOrigLine] ?? line.content);
          currentOrigLine++;
          break;
        case "remove":
          currentOrigLine++;
          break;
        case "add":
          resultLines.push(line.content);
          break;
      }
    }
  }

  // Copy any remaining lines after the last hunk
  while (currentOrigLine < originalLines.length) {
    resultLines.push(originalLines[currentOrigLine]);
    currentOrigLine++;
  }

  return resultLines.join("\n");
}
