#!/usr/bin/env python3
"""Extract plain-text sources (EN, UK, RU) from the original ebook files.

Reads the untouched originals in the repo root:
  - The Road to Unfreedom by Timothy Snyder_EN.epub
  - The Road to Unfreedom by Timothy Snyder_UA.pdf   (needs `pdftotext`)
  - The Road to Unfreedom by Timothy Snyder_RU.epub

Writes sources/EN.md, sources/UK.md, sources/RU.md:
  one `#` heading per part (prologue, ch1..ch6, epilogue),
  one paragraph per line, paragraphs separated by a blank line,
  epigraphs prefixed with "> ".

The original epub/pdf files are never modified.
Usage: python3 extract_sources.py [--root REPO_ROOT]
"""
import argparse
import html
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from html.parser import HTMLParser

PARTS = ["prologue", "ch1", "ch2", "ch3", "ch4", "ch5", "ch6", "epilogue"]


def norm_space(s: str) -> str:
    s = s.replace("­", "")  # soft hyphen
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# ---------------------------------------------------------------- epub (EN/RU)

class ParaParser(HTMLParser):
    """Collects (tag, class, text) items for <p> and <h1..h6> elements."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []       # list of (kind, cls, text)
        self._stack = []      # (tag, cls, buf) for open p/h elements
        self._skip_depth = 0  # inside <a> that is an endnote link

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        cls = d.get("class", "")
        if self._stack and tag == "a":
            # endnote links like <a ...>[1]</a> -> drop their text
            self._skip_depth += 1
            return
        if tag in ("p", "h1", "h2", "h3", "h4"):
            self._stack.append([tag, cls, []])
        elif tag == "div" and self._stack:
            pass

    def handle_endtag(self, tag):
        if tag == "a" and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._stack and tag == self._stack[-1][0]:
            t, cls, buf = self._stack.pop()
            text = norm_space("".join(buf))
            if text:
                self.items.append((t, cls, text))

    def handle_data(self, data):
        if self._stack and not self._skip_depth:
            self._stack[-1][2].append(data)


def parse_xhtml(data: str):
    p = ParaParser()
    p.feed(data)
    return p.items


def extract_en(epub_path: str) -> dict:
    """-> {part: [paragraph, ...]} ; headings stored under key (part, 'title')."""
    files = {
        "prologue": "prl", "ch1": "c01", "ch2": "c02", "ch3": "c03",
        "ch4": "c04", "ch5": "c05", "ch6": "c06", "epilogue": "epl",
    }
    out = {}
    with zipfile.ZipFile(epub_path) as z:
        names = z.namelist()
        for part, key in files.items():
            name = next(n for n in names if f"_{key}_" in n and n.endswith(".xhtml"))
            items = parse_xhtml(z.read(name).decode("utf-8"))
            title_bits, paras = [], []
            for tag, cls, text in items:
                if tag.startswith("h"):
                    title_bits.append(text)
                elif cls.startswith("epi_author"):
                    paras.append("> — " + text.lstrip("—— "))
                elif cls.startswith("epi_text"):
                    paras.append("> " + text)
                elif cls == "center small":
                    continue  # photo captions (not present in all editions)
                else:
                    paras.append(text)
            out[part] = paras
            out[(part, "title")] = " — ".join(title_bits) if title_bits else part
    return out


RU_PART_STARTS = {  # file that opens each part with <div class="title1">
    "ch1-3": "prologue", "ch1-4": "ch1", "ch1-5": "ch2", "ch1-7": "ch3",
    "ch1-9": "ch4", "ch1-11": "ch5", "ch1-14": "ch6", "ch1-17": "epilogue",
    "ch1-18": None,  # Благодарности -> stop collecting
}


def extract_ru(epub_path: str) -> dict:
    def file_order(n):
        m = re.match(r"ch1-(\d+)\.xhtml$", os.path.basename(n))
        if m:
            return int(m.group(1))
        return 1 if os.path.basename(n) == "ch1.xhtml" else 10**6

    out, cur = {}, None
    with zipfile.ZipFile(epub_path) as z:
        names = sorted(
            (n for n in z.namelist()
             if re.match(r"ch1(-\d+)?\.xhtml$", os.path.basename(n))),
            key=file_order)
        for name in names:
            stem = os.path.basename(name).replace(".xhtml", "")
            if stem in RU_PART_STARTS:
                cur = RU_PART_STARTS[stem]
                if cur is not None:
                    out[cur] = []
            if cur is None:
                continue
            items = parse_xhtml(z.read(name).decode("utf-8"))
            for i, (tag, cls, text) in enumerate(items):
                first = stem in RU_PART_STARTS and not out[cur]
                if cls == "empty-line":
                    continue
                if first and cls == "p":
                    out[(cur, "title")] = text
                    continue
                text = re.sub(r"\[\d+\]", "", text).strip()
                if not text:
                    continue
                if cls == "text-author":
                    out[cur].append("> — " + text)
                elif _ru_in_epigraph(items, i):
                    out[cur].append("> " + text)
                else:
                    out[cur].append(text)
    return out


def _ru_in_epigraph(items, i):
    # Heuristic: a 'p1' paragraph directly followed by 'text-author'
    return (i + 1 < len(items) and items[i + 1][1] == "text-author")


# ------------------------------------------------------------------- pdf (UK)

UK_HEADER_RE = [
    re.compile(r"^Тімоті Снайдер\. Шлях до несвободи$"),
    re.compile(r"^Пролог \(2010\)$"),
    re.compile(r"^\d\. .+ \(\d{4}\)$"),
    re.compile(r"^Епілог \(20—\)$"),
    re.compile(r"^(Подяка|Примітки|Предметно-іменний покажчик)$"),
]
UK_PART_TITLES = {
    "Пролог": "prologue", "Епілог": "epilogue",
}


def extract_uk(pdf_path: str) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
        tmp = tf.name
    try:
        subprocess.run(["pdftotext", "-layout", pdf_path, tmp], check=True)
        raw = open(tmp, encoding="utf-8").read()
    finally:
        os.unlink(tmp)

    out, cur, stopped = {}, None, False
    skipped_pages = 0

    def new_part(part, title):
        nonlocal cur
        cur = part
        out[part] = []           # list of paragraph line-buffers (flushed to str)
        out[(part, "title")] = title

    # paragraph assembly state (per current part)
    buf, prev_indent, dropcap_left = [], None, 0

    def flush():
        nonlocal buf
        if buf and cur is not None:
            out[cur].append(_uk_join(buf))
        buf = []

    for page in raw.split("\f"):
        if stopped:
            break
        lines = [l.rstrip() for l in page.split("\n")]
        lines = [l for l in lines if not re.match(r"^\s*\d+\s*$", l)]
        body = [l for l in lines if l.strip()]
        # graphics pages (maps/photos): mostly very short label lines
        if len(body) >= 8:
            shorts = sum(1 for l in body
                         if len(l.strip()) <= 40 and len(l.split()) <= 3)
            if shorts / len(body) > 0.5:
                skipped_pages += 1
                continue
        i = 0
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i >= len(lines):
            continue
        first = lines[i].strip()
        m = re.match(r"^розділ (\d)$", first, re.I)
        if m and f"ch{m.group(1)}" not in out:
            flush()
            prev_indent, dropcap_left = None, 0
            part = f"ch{m.group(1)}"
            i += 1
            title_lines = []
            while i < len(lines):
                s = lines[i].strip()
                i += 1
                if s:
                    title_lines.append(s)
                    if s.endswith(")"):
                        break
            new_part(part, f"Розділ {m.group(1)}. " + " ".join(title_lines))
        elif first in ("Пролог", "Епілог") and \
                UK_PART_TITLES[first] not in out:
            flush()
            prev_indent, dropcap_left = None, 0
            i += 1
            year = ""
            while i < len(lines):
                s = lines[i].strip()
                i += 1
                if s:
                    year = s
                    break
            new_part(UK_PART_TITLES[first], f"{first} {year}")
        elif re.match(r"^Епілог \(20", first) and "epilogue" not in out:
            flush()
            prev_indent, dropcap_left = None, 0
            new_part("epilogue", "Епілог (20—)")
            i += 1
        elif first in ("Подяка", "Примітки"):
            stopped = True
            break
        elif any(rx.match(first) for rx in UK_HEADER_RE):
            i += 1  # running header
        if cur is None:
            continue

        gap = True  # page boundary acts like a vertical gap
        for line in lines[i:]:
            if not line.strip():
                gap = True
                continue
            indent = len(line) - len(line.lstrip())
            s = line.strip()
            if gap and indent < 2 and not re.match(
                    r"^([А-ЯІЇЄҐA-Z])\s{2,}\S", line):
                # column-0 line after a gap: continuation of the paragraph
                # interrupted by a page break if its last line was full-width
                # or unfinished; otherwise a new (section-break) paragraph.
                if buf and (len(buf[-1]) >= 50 or buf[-1][-1:] not in ".!?»…"):
                    pass            # continuation — fall through to append
                else:
                    flush()
                prev_indent, dropcap_left = None, 0
            gap = False
            dc = re.match(r"^([А-ЯІЇЄҐA-Z])\s{2,}(\S.*)$", line)
            if dc and indent == 0:
                flush()
                buf = [dc.group(1) + dc.group(2)]
                dropcap_left = 2   # body lines typeset beside the drop cap
                prev_indent = 0
                continue
            if dropcap_left and indent >= 2:
                buf.append(s)
                dropcap_left -= 1
                prev_indent = 0    # treat as flowed text
                continue
            dropcap_left = 0
            if indent >= 2:
                cont = (prev_indent is not None and prev_indent >= 2 and buf
                        and (buf[-1].endswith(("\u00ad", "-"))
                             or buf[-1][-1:] not in ".!?»…"))
                if cont:
                    buf.append(s)   # block quote / epigraph continuation
                else:
                    flush()
                    buf = [s]
            else:
                if buf:
                    buf.append(s)
                else:
                    buf = [s]
            prev_indent = indent
    flush()

    for part in list(out):
        if isinstance(part, tuple):
            continue
        out[part] = [p for p in (norm_space(x) for x in out[part]) if p]
    if skipped_pages:
        print(f"UK: skipped {skipped_pages} graphics page(s) (maps/photos)",
              file=sys.stderr)
    return out


def _uk_join(lines):
    """Join wrapped lines of one paragraph, resolving hyphenation."""
    s = ""
    for ln in lines:
        if not s:
            s = ln
        elif s.endswith("\u00ad"):
            s = s[:-1] + ln
        elif s.endswith("-") and ln[:1].islower():
            s = s[:-1] + ln
        else:
            s = s + " " + ln
    return s


# ----------------------------------------------------------------------- main

def write_md(path, data, lang):
    lines = []
    for part in PARTS:
        if part not in data:
            continue
        title = data.get((part, "title"), part)
        lines.append(f"# [{part}] {title}")
        lines.append("")
        for p in data[part]:
            lines.append(p)
            lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    counts = {p: len(data[p]) for p in PARTS if p in data}
    print(f"{lang}: " + ", ".join(f"{k}={v}" for k, v in counts.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    root = args.root
    src = os.path.join(root, "sources")
    os.makedirs(src, exist_ok=True)

    en = extract_en(os.path.join(root, "The Road to Unfreedom by Timothy Snyder_EN.epub"))
    write_md(os.path.join(src, "EN.md"), en, "EN")

    uk = extract_uk(os.path.join(root, "The Road to Unfreedom by Timothy Snyder_UA.pdf"))
    write_md(os.path.join(src, "UK.md"), uk, "UK")

    ru = extract_ru(os.path.join(root, "The Road to Unfreedom by Timothy Snyder_RU.epub"))
    write_md(os.path.join(src, "RU.md"), ru, "RU")


if __name__ == "__main__":
    main()
