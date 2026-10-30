#!/usr/bin/env python3
"""Justify a "clean" Markdown file to fixed-width lines.

Input format: paragraph = one line, paragraphs separated by one blank line,
Markdown headings (# ...) on their own lines.

Output: lines of at most WIDTH (default 85) Unicode characters; every line
of a paragraph except the last is padded to exactly WIDTH by distributing
extra spaces between words starting from the middle of the line outwards;
the last line of a paragraph and single-word lines are never stretched;
no trailing spaces; paragraphs separated by one blank line; headings are
left untouched (never justified).

Blockquote paragraphs (epigraphs, lines starting with "> ") are wrapped
greedily to the same width with the "> " marker repeated on every line
(the marker counts toward the width) but are NOT stretched — like
headings, they are never justified.

A single word longer than WIDTH is left on its own (overlong) line.

Usage: python3 justify.py INPUT [-o OUTPUT] [--width 85]
       (without -o the result goes to stdout)
"""
import argparse
import re
import sys


def fill_paragraph(text, width):
    """Greedy fill + full justification. Returns list of output lines."""
    words = text.split()
    if not words:
        return []
    lines, cur, cur_len = [], [], 0
    for w in words:
        add = len(w) if not cur else len(w) + 1
        if cur and cur_len + add > width:
            lines.append(cur)
            cur, cur_len = [w], len(w)
        else:
            cur.append(w)
            cur_len += add
    if cur:
        lines.append(cur)
    out = []
    for i, line_words in enumerate(lines):
        last = i == len(lines) - 1
        if last or len(line_words) == 1:
            out.append(" ".join(line_words))
        else:
            out.append(stretch(line_words, width))
    return out


def stretch(words, width):
    """Pad a line to exactly `width` chars, adding the extra spaces between
    words starting from the middle gap and alternating outwards."""
    base = " ".join(words)
    extra = width - len(base)
    if extra <= 0:
        return base
    gaps = len(words) - 1
    add = [extra // gaps] * gaps
    rem = extra % gaps
    # order of gaps: middle first, then alternate outwards
    mid = (gaps - 1) // 2
    order = [mid]
    step = 1
    while len(order) < gaps:
        if mid + step < gaps:
            order.append(mid + step)
        if len(order) < gaps and mid - step >= 0:
            order.append(mid - step)
        step += 1
    for k in range(rem):
        add[order[k]] += 1
    parts = [words[0]]
    for g in range(gaps):
        parts.append(" " * (1 + add[g]))
        parts.append(words[g + 1])
    return "".join(parts)


def justify_text(text, width):
    out = []
    for block in text.split("\n\n"):
        block = block.strip("\n")
        if not block.strip():
            continue
        # a clean-file paragraph is one line; be forgiving about stray wraps
        merged = " ".join(l.strip() for l in block.splitlines() if l.strip())
        if merged.startswith("#"):
            out.append(merged)
        elif merged.startswith(">"):
            text = re.sub(r"^(>\s*)+", "", merged)
            words = text.split()
            lines, cur = [], ""
            for w in words:
                cand = (cur + " " + w) if cur else w
                if cur and len("> " + cand) > width:
                    lines.append("> " + cur)
                    cur = w
                else:
                    cur = cand
            if cur:
                lines.append("> " + cur)
            out.extend(lines)
        else:
            out.extend(fill_paragraph(merged, width))
        out.append("")
    while out and not out[-1]:
        out.pop()
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    ap.add_argument("--width", type=int, default=85)
    args = ap.parse_args()
    text = open(args.input, encoding="utf-8").read()
    result = justify_text(text, args.width)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
    else:
        sys.stdout.write(result)


if __name__ == "__main__":
    main()
