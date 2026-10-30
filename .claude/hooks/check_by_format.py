#!/usr/bin/env python3
"""Hook validating final *_BY.md files in the repository root.

Two modes, selected by the hook event in the stdin JSON:

- PostToolUse (matcher: Write|Edit): if tool_input.file_path is a *_BY.md
  file in the repository root, checks that one file. Catches direct
  Write/Edit of a final file.
- Stop: checks the *_BY.md files in the repository root that were CHANGED
  in this session (modified or untracked per `git status`), because the
  final file is normally produced by `justify.py -o ...` through Bash,
  which PostToolUse(Write|Edit) never sees. Committed files from other
  sessions (e.g. a finished Fable file during an Opus run) are left alone.
  If git is unavailable, falls back to checking every root *_BY.md.
  Guarded by stop_hook_active to avoid an infinite stop loop.

On violations exits with code 2 and prints the errors to stderr
(blocking feedback for the agent).
"""
import glob
import json
import os
import re
import subprocess
import sys


def check_one(root, path):
    """Run check_format.py on one file; return error text or ''."""
    name = os.path.basename(path)
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
        return (f"check_by_format: {name} нарушает формат BY:\n"
                + res.stdout + res.stderr)
    return ""


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    root = os.path.abspath(root)
    event = data.get("hook_event_name", "")

    if event == "Stop":
        if data.get("stop_hook_active"):
            sys.exit(0)  # already continuing after this hook — don't loop
        targets = sorted(glob.glob(os.path.join(root, "*_BY.md")))
        try:
            st = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                capture_output=True, text=True, cwd=root, check=True)
            changed = set()
            for line in st.stdout.splitlines():
                p = line[3:].strip().strip('"')
                if " -> " in p:
                    p = p.split(" -> ", 1)[1].strip('"')
                changed.add(os.path.abspath(os.path.join(root, p)))
            targets = [p for p in targets if os.path.abspath(p) in changed]
        except Exception:
            pass  # no git — check every root *_BY.md
        errors = ""
        for path in targets:
            errors += check_one(root, path)
        if errors:
            sys.stderr.write(errors)
            sys.exit(2)
        sys.exit(0)

    # PostToolUse (Write|Edit)
    file_path = (data.get("tool_input") or {}).get("file_path") or ""
    if not file_path:
        sys.exit(0)
    path = os.path.abspath(file_path)
    if not path.endswith("_BY.md"):
        sys.exit(0)
    if os.path.dirname(path) != root:
        sys.exit(0)  # only final files in the repo root are checked
    if not os.path.exists(path):
        sys.exit(0)
    errors = check_one(root, path)
    if errors:
        sys.stderr.write(errors)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
