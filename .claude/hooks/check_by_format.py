#!/usr/bin/env python3
"""PostToolUse hook (matcher: Write|Edit).

Reads the hook JSON from stdin; if tool_input.file_path is a *_BY.md file in
the repository root, runs check_format.py on it. On violations exits with
code 2 and prints the errors to stderr (blocking feedback for the agent).
"""
import json
import os
import re
import subprocess
import sys


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    file_path = (data.get("tool_input") or {}).get("file_path") or ""
    if not file_path:
        sys.exit(0)

    root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    root = os.path.abspath(root)
    path = os.path.abspath(file_path)

    name = os.path.basename(path)
    if not name.endswith("_BY.md"):
        sys.exit(0)
    if os.path.dirname(path) != root:
        sys.exit(0)  # only final files in the repo root are checked
    if not os.path.exists(path):
        sys.exit(0)

    checker = os.path.join(root, ".claude", "skills", "md-justify",
                           "scripts", "check_format.py")
    cmd = [sys.executable, checker, path]
    # part number from the canonical file name -> EN paragraph-count check
    m = re.search(r"_(\d+)_BY\.md$", name)
    if m and m.group(1) in [str(i) for i in range(8)] \
            and os.path.exists(os.path.join(root, "sources", "EN.md")):
        cmd += ["--part", m.group(1),
                "--sources", os.path.join(root, "sources", "EN.md")]

    res = subprocess.run(cmd, capture_output=True, text=True, cwd=root)
    if res.returncode != 0:
        sys.stderr.write(f"check_by_format: {name} нарушает формат BY:\n")
        sys.stderr.write(res.stdout + res.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
