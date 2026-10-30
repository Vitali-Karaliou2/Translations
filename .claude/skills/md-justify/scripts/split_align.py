#!/usr/bin/env python3
"""Extract one part of the book from sources/{EN,UK,RU}.md and align it.

Writes into work/<part>/<model>/:
  - segments.md — a table `ID | EN | UK | RU` (EN paragraphs are the pivot;
    merged paragraphs are joined with " ¶ ") — for the synthesizer;
  - segments_EN.md, segments_UK.md, segments_RU.md — one language each
    (## P### + paragraph), so single-source translators can be given a file
    that mechanically CANNOT leak the other languages into their context.
Reports pairwise paragraph-count divergences (EN/UK, EN/RU, UK/RU) and
where each divergence starts, both to stdout and to
work/<part>/<model>/align_report.md.

Usage:
  python3 split_align.py --part prologue --model fable [--root .]
Parts: prologue (0), ch1..ch6 (1..6), epilogue (7).
"""
import argparse
import os
import re
import sys

PART_ALIASES = {
    "0": "prologue", "prologue": "prologue", "prolog": "prologue",
    "7": "epilogue", "epilogue": "epilogue", "epilog": "epilogue",
    **{str(i): f"ch{i}" for i in range(1, 7)},
    **{f"ch{i}": f"ch{i}" for i in range(1, 7)},
}


def read_part(path, part):
    """Return (title, [paragraphs]) for a part from a sources/*.md file."""
    text = open(path, encoding="utf-8").read()
    pat = re.compile(r"^# \[(\w+)\] (.*)$", re.M)
    matches = list(pat.finditer(text))
    for i, m in enumerate(matches):
        if m.group(1) == part:
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[m.end():end]
            paras = [p.strip() for p in body.split("\n\n") if p.strip()]
            paras = [re.sub(r"\s+", " ", p) for p in paras]
            return m.group(2), paras
    sys.exit(f"part {part!r} not found in {path}")


# ------------------------------------------------- Gale–Church-like alignment

OPS = [(1, 1, 0.0), (1, 0, 6.0), (0, 1, 6.0), (2, 1, 4.0), (1, 2, 4.0)]


def align(a, b):
    """Align two paragraph lists by relative length. Returns list of
    (a_indices, b_indices) tuples covering both lists in order."""
    la = [len(p) for p in a]
    lb = [len(p) for p in b]
    r = (sum(lb) / sum(la)) if sum(la) else 1.0
    INF = float("inf")
    n, m = len(a), len(b)
    cost = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            c0 = cost[i][j]
            if c0 == INF:
                continue
            for da, db, pen in OPS:
                ni, nj = i + da, j + db
                if ni > n or nj > m:
                    continue
                sa = sum(la[i:ni])
                sb = sum(lb[j:nj])
                exp = sa * r
                d = (sb - exp) / ((exp + sb) / 2 + 1) ** 0.5
                c = c0 + d * d + pen
                if c < cost[ni][nj]:
                    cost[ni][nj] = c
                    back[ni][nj] = (i, j)
    # recover path
    path = []
    i, j = n, m
    while (i, j) != (0, 0):
        pi, pj = back[i][j]
        path.append((list(range(pi, i)), list(range(pj, j))))
        i, j = pi, pj
    path.reverse()
    return path


def describe_divergences(name_a, name_b, path, a, b):
    """Human-readable list of non-1:1 alignment operations."""
    lines = []
    for ia, ib in path:
        if len(ia) == 1 and len(ib) == 1:
            continue
        def ids(idx, lang):
            return "+".join(f"{lang}:{k + 1:03d}" for k in idx) or f"{lang}:—"
        frag_a = (a[ia[0]][:60] + "…") if ia else "(няма)"
        frag_b = (b[ib[0]][:60] + "…") if ib else "(няма)"
        kind = {(1, 0): "лішні абзац у " + name_a,
                (0, 1): "лішні абзац у " + name_b,
                (2, 1): f"2 абзацы {name_a} = 1 абзац {name_b}",
                (1, 2): f"1 абзац {name_a} = 2 абзацы {name_b}",
                (2, 2): "перакампаноўка 2:2"}.get((len(ia), len(ib)),
                                                  f"{len(ia)}:{len(ib)}")
        lines.append(f"- **{ids(ia, name_a)} ↔ {ids(ib, name_b)}** ({kind})\n"
                     f"  - {name_a}: {frag_a}\n  - {name_b}: {frag_b}")
    return lines


def esc(s):
    return s.replace("|", "\\|")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True)
    ap.add_argument("--model", required=True, choices=["fable", "opus"])
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    part = PART_ALIASES.get(str(args.part).lower())
    if not part:
        sys.exit(f"unknown part: {args.part}")

    src = os.path.join(args.root, "sources")
    t_en, en = read_part(os.path.join(src, "EN.md"), part)
    t_uk, uk = read_part(os.path.join(src, "UK.md"), part)
    t_ru, ru = read_part(os.path.join(src, "RU.md"), part)

    outdir = os.path.join(args.root, "work", part, args.model)
    os.makedirs(outdir, exist_ok=True)

    p_eu = align(en, uk)
    p_er = align(en, ru)
    p_ur = align(uk, ru)

    # ------- segments.md: EN is the pivot ---------------------------------
    def en_map(path):
        """en index -> list of other-side indices (insertions attach to the
        previous EN paragraph)."""
        mp = {i: [] for i in range(len(en))}
        last = 0
        for ia, ib in path:
            if ia:
                last = ia[-1]
                if len(ia) == len(ib):
                    for k, v in zip(ia, ib):
                        mp[k].append(v)
                else:
                    mp[ia[0]].extend(ib)
            else:
                mp[last].extend(ib)
        return mp

    m_uk = en_map(p_eu)
    m_ru = en_map(p_er)

    rows = []
    for i in range(len(en)):
        pid = f"P{i + 1:03d}"
        cu = " ¶ ".join(uk[k] for k in m_uk.get(i, []))
        cr = " ¶ ".join(ru[k] for k in m_ru.get(i, []))
        rows.append(f"| {pid} | {esc(en[i])} | {esc(cu)} | {esc(cr)} |")

    seg = os.path.join(outdir, "segments.md")
    with open(seg, "w", encoding="utf-8") as f:
        f.write(f"# Сегменты — {part} ({args.model})\n\n")
        f.write(f"- EN: {t_en} — {len(en)} абз.\n")
        f.write(f"- UK: {t_uk} — {len(uk)} абз.\n")
        f.write(f"- RU: {t_ru} — {len(ru)} абз.\n\n")
        f.write("| ID | EN | UK | RU |\n|----|----|----|----|\n")
        f.write("\n".join(rows) + "\n")

    # per-language files: mechanical isolation for single-source translators
    def write_lang(lang, title, cells):
        p = os.path.join(outdir, f"segments_{lang}.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"# Сегменты {lang} — {part}: {title}\n")
            for i, cell in enumerate(cells):
                f.write(f"\n## P{i + 1:03d}\n{cell}\n")
        return p

    write_lang("EN", t_en, en)
    write_lang("UK", t_uk,
               [" ¶ ".join(uk[k] for k in m_uk.get(i, []))
                for i in range(len(en))])
    write_lang("RU", t_ru,
               [" ¶ ".join(ru[k] for k in m_ru.get(i, []))
                for i in range(len(en))])

    # ------- divergence report --------------------------------------------
    rep = [f"# Справаздача выраўноўвання — {part}",
           "",
           f"Абзацаў: EN={len(en)}, UK={len(uk)}, RU={len(ru)}", ""]
    for name_a, name_b, path, a, b in (
            ("EN", "UK", p_eu, en, uk),
            ("EN", "RU", p_er, en, ru),
            ("UK", "RU", p_ur, uk, ru)):
        rep.append(f"## {name_a}/{name_b}: {len(a)} ↔ {len(b)}"
                   + ("" if len(a) != len(b) else " (супадае)"))
        div = describe_divergences(name_a, name_b, path, a, b)
        rep.extend(div or ["- разыходжанняў не выяўлена"])
        rep.append("")
    report = "\n".join(rep)
    with open(os.path.join(outdir, "align_report.md"), "w",
              encoding="utf-8") as f:
        f.write(report + "\n")
    print(report)
    print(f"\nЗапісана: {seg}")


if __name__ == "__main__":
    main()
