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

# MDX: JSX component tags (capitalised names) and import/export lines.
JSX_TAG_RE = re.compile(r"</?[A-Z][A-Za-z0-9]*(?:\s[^>]*?)?/?>")
MDX_IMPORT_RE = re.compile(r"^\s*(import|export)\s")
FRONTMATTER_TITLE_RE = re.compile(r"""^\s*title:\s*['"]?(.+?)['"]?\s*$""")
# A line that is *only* an HTML/JSX wrapper tag (e.g. `<section title="x">`,
# `</section>`). Removing these stops a wrapper tag with no trailing blank line
# from starting an HTML block that swallows the next code fence.
STANDALONE_TAG_RE = re.compile(r"^</?[A-Za-z][\w.-]*(?:\s[^>]*?)?/?>$")


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


def rewrite_image_paths(md, source_dir, root, resolve_site=None):
    """Rewrite relative image refs to be relative to `root`; skip code/URLs.

    Site-relative paths (`/images/x.png`) are passed to `resolve_site` if given
    (used to map them onto local repo assets); left untouched otherwise.
    """

    def remap(path):
        if path.startswith(("http://", "https://", "data:", "#")):
            return path
        if path.startswith("/"):
            if resolve_site:
                resolved = resolve_site(path)
                if resolved:
                    return resolved
            return path
        joined = posixpath.normpath(posixpath.join(source_dir, path))
        return posixpath.relpath(joined, root)

    def sub(text):
        text = IMG_MD_RE.sub(
            lambda m: m.group(1) + remap(m.group(2)) + m.group(3), text
        )
        return IMG_HTML_RE.sub(
            lambda m: m.group(1) + remap(m.group(2)) + m.group(3), text
        )

    # Process non-code regions as whole blocks so multi-line image markdown and
    # multi-line <img> tags (e.g. MDX <Frame><img ... /></Frame>) are matched.
    out, buf, in_code = [], [], False
    for line in md.splitlines(keepends=True):
        if line.lstrip().startswith(("```", "~~~")):
            if buf:
                out.append(sub("".join(buf)))
                buf = []
            out.append(line)
            in_code = not in_code
        elif in_code:
            out.append(line)
        else:
            buf.append(line)
    if buf:
        out.append(sub("".join(buf)))
    return "".join(out)


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


def strip_standalone_html_tags(md):
    """Remove lines that are a single HTML/JSX wrapper tag (outside code)."""
    lines = md.splitlines()
    out = [
        line
        for line, code in zip(lines, _code_mask(lines))
        if code or not STANDALONE_TAG_RE.match(line.strip())
    ]
    return _join_like(md, out)


def preprocess_mdx(md):
    """Clean an MDX source into plain Markdown (frontmatter + JSX stripped)."""
    body, title = strip_yaml_frontmatter(md)
    body = strip_jsx(body)
    body = strip_standalone_html_tags(body)
    if title:
        body = f"# {title}\n\n{body.lstrip()}"
    return body


# Fetched platform.claude.com / code.claude.com pages are MDX-flavored (they
# contain JSX components like <CodeGroup>), so they need the same cleaning as
# .mdx files — otherwise a <CodeGroup> with no trailing blank line swallows the
# following code fence and code comments leak into the TOC as headings.
def needs_mdx_cleaning(path):
    return (
        path.endswith(".mdx")
        or path.startswith("docs/platform/")
        or path.startswith("docs/claude-code/")
    )


FENCE_RE = re.compile(r"^(`{3,}|~{3,})(.*)$")


def _fence_parts(line):
    """(marker, char, has_info) for a fence line, else None."""
    m = FENCE_RE.match(line.strip())
    if not m:
        return None
    marker = m.group(1)
    return marker, marker[0], m.group(2).strip() != ""


def fix_nested_code_fences(md):
    """Re-wrap code blocks that contain inner fences with a longer fence.

    nbconvert wraps a code cell's source in ```` ``` ````; if that source contains
    a fenced example (e.g. a ```html block inside a string), the inner bare ```
    closes the cell early and the rest of the cell spills out as Markdown — code
    comments then become headings. Bumping the outer fence past the inner ones
    (CommonMark: a fence is closed only by a longer-or-equal *bare* fence of the
    same char) keeps the whole cell as code. A no-op when there is no nesting.
    """
    lines = md.splitlines()
    out, i, n = [], 0, len(lines)
    while i < n:
        parts = _fence_parts(lines[i])
        if parts is None:
            out.append(lines[i])
            i += 1
            continue
        marker, ch, _ = parts
        opener_ticks = len(marker)
        j, inner, closer, has_inner = i + 1, 0, None, False
        while j < n:
            pj = _fence_parts(lines[j])
            if pj and pj[1] == ch:
                if pj[2]:  # info-string fence -> inner example opener
                    inner += 1
                    has_inner = True
                elif inner > 0:  # bare fence closes an inner example
                    inner -= 1
                else:  # bare fence closes the cell
                    closer = j
                    break
            j += 1
        if closer is None:  # unbalanced — leave as-is
            out.append(lines[i])
            i += 1
            continue
        if has_inner:
            new_marker = ch * max(opener_ticks + 1, 4)
            info = lines[i].strip()[opener_ticks:]
            out.append(new_marker + info)
            out.extend(lines[i + 1 : closer])
            out.append(new_marker)
        else:
            out.extend(lines[i : closer + 1])
        i = closer + 1
    return _join_like(md, out)


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


def assemble(entries, read_text, root, resolve_site=None):
    """Concatenate entries into one normalized Markdown document.

    `resolve_site(source_path, site_path)` optionally maps a site-relative image
    path onto a local asset; used so repo docs that reference `/images/...`
    embed the cloned image instead of a dead link.
    """
    chunks = []
    for entry in entries:
        if entry["type"] == "part":
            chunks.append(f"# {entry['title']}\n\n")
            continue
        raw = read_text(entry["path"])
        if entry.get("authored"):
            content = raw.rstrip() + "\n"
        else:
            if needs_mdx_cleaning(entry["path"]):
                raw = preprocess_mdx(raw)
            raw = fix_nested_code_fences(raw)
            src_dir = posixpath.dirname(entry["path"])
            site = (lambda p: resolve_site(entry["path"], p)) if resolve_site else None
            raw = rewrite_image_paths(raw, src_dir, root, resolve_site=site)
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

    def resolve_site(source_path, site_path):
        """Map a site-relative image (/images/x.png) onto a local repo asset by
        walking the source file's ancestor directories for a matching file."""
        rel = site_path.lstrip("/").split("?")[0].split("#")[0]
        directory = os.path.dirname(source_path)
        while True:
            candidate = (
                os.path.join(root, directory, rel)
                if directory
                else os.path.join(root, rel)
            )
            if os.path.isfile(candidate):
                return os.path.relpath(candidate, root).replace(os.sep, "/")
            if not directory:
                return None
            parent = os.path.dirname(directory)
            if parent == directory:
                return None
            directory = parent

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

    book = assemble(entries, read_text=read_text, root=".", resolve_site=resolve_site)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(book)

    n_sources = sum(1 for e in entries if e["type"] == "source")
    n_parts = sum(1 for e in entries if e["type"] == "part")
    print(f"[✓] {args.out}: {n_parts} parts, {n_sources} sources, {len(book):,} chars")


if __name__ == "__main__":
    main()
