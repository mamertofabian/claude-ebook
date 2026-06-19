#!/usr/bin/env python3
"""
build_book.py
=============

Assemble a curated set of Markdown sources into a single cohesive `book.md`
ready for Pandoc.  Reads a human-editable `manifest.txt` (reading order), and
for each source:

  * demotes its headings so every source sits at chapter level (H2) under its
    Part (H1) — giving a clean, comprehensive Part -> chapter TOC;
  * rewrites relative image paths so they resolve from the project root after
    everything is concatenated into one file;
  * prepends a "*Source: ...*" attribution line.

Authored front-matter includes (prefixed `~ ` in the manifest) are inserted
verbatim — no demotion, no attribution — because their heading levels are
already correct.

The transformation functions are pure (no I/O); `main()` does the reading and
writing at the edges.

Usage:
    python3 build_book.py --manifest manifest.txt --root . --out build/book.md
"""

import argparse
import os
import posixpath
import re

HEADING_RE = re.compile(r"^(#{1,6})(\s+\S.*)$")
IMG_MD_RE = re.compile(r"(!\[[^\]]*\]\()([^)\s]+)(\))")
IMG_HTML_RE = re.compile(r'(<img[^>]*?\ssrc=")([^"]+)(")', re.IGNORECASE)
_ABSOLUTE_URL = ("http://", "https://", "data:", "/", "#")

# MDX: JSX component tags (capitalised names) and import/export lines.
JSX_TAG_RE = re.compile(r"</?[A-Z][A-Za-z0-9]*(?:\s[^>]*?)?/?>")
MDX_IMPORT_RE = re.compile(r"^\s*(import|export)\s")
FRONTMATTER_TITLE_RE = re.compile(r"""^\s*title:\s*['"]?(.+?)['"]?\s*$""")


# --------------------------------------------------------------------------- #
# Code-fence awareness
# --------------------------------------------------------------------------- #


def _is_fence(line):
    s = line.lstrip()
    return s.startswith("```") or s.startswith("~~~")


def _code_mask(lines):
    """True for every line that is a fence marker or inside a fenced block."""
    mask, in_code = [], False
    for line in lines:
        if _is_fence(line):
            mask.append(True)
            in_code = not in_code
        else:
            mask.append(in_code)
    return mask


def _join_like(original, lines):
    body = "\n".join(lines)
    return body + "\n" if original.endswith("\n") else body


# --------------------------------------------------------------------------- #
# Pure transforms
# --------------------------------------------------------------------------- #


def min_heading_level(md):
    """Shallowest ATX heading level outside code fences, or None."""
    lines = md.splitlines()
    levels = [
        len(m.group(1))
        for line, code in zip(lines, _code_mask(lines))
        if not code and (m := HEADING_RE.match(line))
    ]
    return min(levels) if levels else None


def demote_headings(md, shift):
    """Shift every ATX heading by `shift`, clamped to [1, 6]; skip code."""
    if shift == 0:
        return md
    lines = md.splitlines()
    out = []
    for line, code in zip(lines, _code_mask(lines)):
        if not code:
            m = HEADING_RE.match(line)
            if m:
                level = min(6, max(1, len(m.group(1)) + shift))
                line = "#" * level + m.group(2)
        out.append(line)
    return _join_like(md, out)


def rewrite_image_paths(md, source_dir, root):
    """Rewrite relative image refs to be relative to `root`; skip code/URLs."""

    def remap(path):
        if path.startswith(_ABSOLUTE_URL):
            return path
        joined = posixpath.normpath(posixpath.join(source_dir, path))
        return posixpath.relpath(joined, root)

    def sub_line(line):
        line = IMG_MD_RE.sub(
            lambda m: m.group(1) + remap(m.group(2)) + m.group(3), line
        )
        line = IMG_HTML_RE.sub(
            lambda m: m.group(1) + remap(m.group(2)) + m.group(3), line
        )
        return line

    lines = md.splitlines()
    out = [
        line if code else sub_line(line) for line, code in zip(lines, _code_mask(lines))
    ]
    return _join_like(md, out)


def strip_yaml_frontmatter(md):
    """Return (body, title) — strip a leading `--- ... ---` YAML block."""
    if not md.startswith("---\n") and not md.startswith("---\r\n"):
        return md, None
    lines = md.splitlines()
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            title = None
            for meta_line in lines[1:i]:
                m = FRONTMATTER_TITLE_RE.match(meta_line)
                if m:
                    title = m.group(1).strip()
                    break
            body = "\n".join(lines[i + 1 :]).lstrip("\n")
            if md.endswith("\n") and not body.endswith("\n"):
                body += "\n"
            return body, title
    return md, None


def strip_jsx(md):
    """Remove MDX JSX component tags and import/export lines; keep inner text."""
    lines = md.splitlines()
    out = []
    for line, code in zip(lines, _code_mask(lines)):
        if code:
            out.append(line)
            continue
        if MDX_IMPORT_RE.match(line):
            continue
        out.append(JSX_TAG_RE.sub("", line))
    return _join_like(md, out)


def preprocess_mdx(md):
    """Clean an MDX source into plain Markdown (frontmatter + JSX stripped)."""
    body, title = strip_yaml_frontmatter(md)
    body = strip_jsx(body)
    if title:
        body = f"# {title}\n\n{body.lstrip()}"
    return body


def _title_from_path(rel_path):
    stem = posixpath.splitext(posixpath.basename(rel_path))[0]
    if stem.upper() in ("README", "SKILL"):
        stem = posixpath.basename(posixpath.dirname(rel_path)) or stem
    return stem.replace("-", " ").replace("_", " ").strip().title() or "Untitled"


def normalize_source(md, rel_path, base=2):
    """Demote a source to chapter level `base` and attach attribution."""
    attribution = f"*Source: {rel_path}*"
    level = min_heading_level(md)
    if level is None:
        title = _title_from_path(rel_path)
        return f"## {title}\n\n{attribution}\n\n{md.rstrip()}\n"

    shifted = demote_headings(md, base - level)
    lines = shifted.splitlines()
    mask = _code_mask(lines)
    head_idx = next(
        i
        for i, (line, code) in enumerate(zip(lines, mask))
        if not code and HEADING_RE.match(line)
    )
    out = lines[: head_idx + 1] + ["", attribution] + lines[head_idx + 1 :]
    return "\n".join(out) + "\n"


def parse_manifest(text):
    """Parse reading-order directives into part / source entries.

    Directives:
        PART: <title>     -> a Part divider (becomes an H1 chapter group)
        ~ <path>          -> authored include (verbatim, no demote/attribution)
        <path>            -> curated source (demoted + attributed)
        # ... / blank     -> ignored
    """
    entries = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("PART:"):
            entries.append({"type": "part", "title": line[len("PART:") :].strip()})
        elif line.startswith("~ "):
            entries.append(
                {"type": "source", "path": line[2:].strip(), "authored": True}
            )
        else:
            entries.append({"type": "source", "path": line, "authored": False})
    return entries


def assemble(entries, read_text, root):
    """Concatenate entries into one normalized Markdown document."""
    chunks = []
    for entry in entries:
        if entry["type"] == "part":
            chunks.append(f"# {entry['title']}\n\n")
            continue
        raw = read_text(entry["path"])
        if entry.get("authored"):
            content = raw.rstrip() + "\n"
        else:
            if entry["path"].endswith(".mdx"):
                raw = preprocess_mdx(raw)
            src_dir = posixpath.dirname(entry["path"])
            raw = rewrite_image_paths(raw, src_dir, root)
            content = normalize_source(raw, entry["path"], base=2)
        chunks.append(content.rstrip() + "\n\n")
    return "".join(chunks)


# --------------------------------------------------------------------------- #
# I/O edges
# --------------------------------------------------------------------------- #


def main():
    ap = argparse.ArgumentParser(description="Assemble manifest sources into book.md")
    ap.add_argument("--manifest", default="manifest.txt")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="build/book.md")
    args = ap.parse_args()

    root = os.path.abspath(args.root)

    def read_text(rel_path):
        with open(
            os.path.join(root, rel_path), encoding="utf-8", errors="replace"
        ) as f:
            return f.read()

    with open(args.manifest, encoding="utf-8") as f:
        entries = parse_manifest(f.read())

    missing = [
        e["path"]
        for e in entries
        if e["type"] == "source" and not os.path.isfile(os.path.join(root, e["path"]))
    ]
    if missing:
        raise SystemExit(
            "build_book: missing sources (fix manifest or run fetch/notebooks):\n  "
            + "\n  ".join(missing)
        )

    book = assemble(entries, read_text=read_text, root=".")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(book)

    n_sources = sum(1 for e in entries if e["type"] == "source")
    n_parts = sum(1 for e in entries if e["type"] == "part")
    print(f"[✓] {args.out}: {n_parts} parts, {n_sources} sources, {len(book):,} chars")


if __name__ == "__main__":
    main()
