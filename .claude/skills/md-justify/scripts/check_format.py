#!/usr/bin/env python3
"""Validate a justified Belarusian (*_BY.md) file.

Checks:
  1. no line longer than WIDTH (85) Unicode chars — except a single word
     that itself is longer than WIDTH;
  2. no trailing spaces;
  3. every non-final line of a paragraph (with 2+ words) is exactly WIDTH
     chars (i.e. the paragraph is justified);
  4. the final line of a paragraph is NOT padded (no double spaces unless
     line is exactly WIDTH — final lines must be <= WIDTH and single-spaced);
  5. headings (# ...) are single lines, not justified (single-spaced);
  5a. blockquote paragraphs (epigraphs): every line starts with "> ", lines
      are wrapped to WIDTH but never stretched (no double spaces);
  6. paragraphs are separated by exactly one blank line;
  7. optionally: the number of body paragraphs equals the EN source part
     (--part prologue|0..7 with --sources sources/EN.md, or --en FILE with
     a clean/justified reference).

Exit code 0 = OK, 1 = violations (printed to stdout and stderr).

Usage:
  python3 check_format.py FILE [--width 85] [--part N] [--sources sources/EN.md]
"""
import argparse
import re
import sys

PART_ALIASES = {
    "0": "prologue", "prologue": "prologue",
    "7": "epilogue", "epilogue": "epilogue",
    **{str(i): f"ch{i}" for i in range(1, 7)},
    **{f"ch{i}": f"ch{i}" for i in range(1, 7)},
}


def paragraphs(lines):
    """Split physical lines into blocks: list of (start_lineno, [lines])."""
    blocks, cur, start = [], [], None
    for i, l in enumerate(lines, 1):
        if l.strip():
            if not cur:
                start = i
            cur.append(l)
        elif cur:
            blocks.append((start, cur))
            cur = []
    if cur:
        blocks.append((start, cur))
    return blocks


def check(path, width=85, en_count=None):
    errors = []
    text = open(path, encoding="utf-8").read()
    lines = text.split("\n")
    if text and not text.endswith("\n"):
        errors.append("файл не заканчваецца пераводам радка")
    for i, l in enumerate(lines, 1):
        if l != l.rstrip():
            errors.append(f"радок {i}: хваставыя прабелы")
        if len(l) > width and " " in l.strip():
            errors.append(f"радок {i}: даўжыня {len(l)} > {width}")
    # blank-line discipline: no two consecutive blank lines
    for i in range(1, len(lines)):
        if not lines[i].strip() and not lines[i - 1].strip() \
                and i < len(lines) - 1:
            errors.append(f"радок {i + 1}: больш за адзін пусты радок запар")
    body_par = 0
    for start, block in paragraphs(lines):
        if block[0].lstrip().startswith("#"):
            if len(block) > 1:
                errors.append(f"радок {start}: заголовак з {len(block)} радкоў")
            if "  " in block[0].strip():
                errors.append(f"радок {start}: заголовак выраўнаваны (двайныя "
                              f"прабелы)")
            continue
        body_par += 1
        if block[0].lstrip().startswith(">"):
            for j, l in enumerate(block):
                ln = start + j
                if not l.startswith("> "):
                    errors.append(f"радок {ln}: радок цытаты без маркера «> »")
                elif "  " in l[2:]:
                    errors.append(f"радок {ln}: цытата расцягнута (двайныя "
                                  f"прабелы)")
            continue
        for j, l in enumerate(block):
            ln = start + j
            last = j == len(block) - 1
            words = l.split()
            if not last:
                if len(words) > 1 and len(l) != width:
                    errors.append(f"радок {ln}: непоўнае выраўноўванне "
                                  f"({len(l)} зам. {width})")
            else:
                if "  " in l.strip() and len(l) != width:
                    errors.append(f"радок {ln}: апошні радок абзаца расцягнуты")
    if en_count is not None and body_par != en_count:
        errors.append(f"абзацаў у BY: {body_par}, у EN: {en_count} — не "
                      f"супадае")
    return errors, body_par


def en_part_count(sources_en, part):
    text = open(sources_en, encoding="utf-8").read()
    pat = re.compile(r"^# \[(\w+)\] .*$", re.M)
    ms = list(pat.finditer(text))
    for i, m in enumerate(ms):
        if m.group(1) == part:
            end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
            return len([p for p in text[m.end():end].split("\n\n")
                        if p.strip()])
    sys.exit(f"part {part!r} not found in {sources_en}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--width", type=int, default=85)
    ap.add_argument("--part")
    ap.add_argument("--sources", default="sources/EN.md")
    ap.add_argument("--en", help="reference file: count its paragraphs")
    args = ap.parse_args()

    en_count = None
    if args.en:
        ref = open(args.en, encoding="utf-8").read().split("\n")
        en_count = sum(1 for _, b in paragraphs(ref)
                       if not b[0].lstrip().startswith("#"))
    elif args.part:
        part = PART_ALIASES.get(str(args.part).lower())
        if not part:
            sys.exit(f"unknown part: {args.part}")
        en_count = en_part_count(args.sources, part)

    errors, body = check(args.file, args.width, en_count)
    if errors:
        for e in errors:
            print(f"{args.file}: {e}")
            print(f"{args.file}: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"OK: {args.file} — {body} абзацаў, фармат правільны"
          + (f", супадае з EN ({en_count})" if en_count is not None else ""))


if __name__ == "__main__":
    main()
