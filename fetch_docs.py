#!/usr/bin/env python3
"""
fetch_docs.py
=============

Fetch the official Claude content that lives *only* as rendered web pages (not
in a cloned repo) and write it as Markdown under `docs/`, so the ebook build has
real page content to compile — not just an index of links.

Three sources:

  * **Platform docs** (`platform.claude.com`) — pages are published as `.md`;
    downloaded directly. Curated by path allow/deny lists.
  * **Claude Code docs** (`code.claude.com`) — also `.md`; a curated explicit
    page list (the index is flat, so an allow-prefix would be too coarse).
  * **Engineering essays** (`anthropic.com`) — HTML only; the `main-content`
    region is extracted and converted to Markdown with Pandoc.

Fail-loud: any selected page that cannot be fetched/converted is collected and
reported, and the run exits non-zero. Nothing is silently skipped.

Reuses `fetch()` and `parse_llms()` from anthropic_resources.py.

Usage:
    python3 fetch_docs.py                 # fetch into ./docs (skip existing)
    python3 fetch_docs.py --force         # re-fetch even if files exist
    python3 fetch_docs.py --out-dir docs  # custom output root
"""

import argparse
import os
import re
import subprocess
import sys
import urllib.parse
from html.parser import HTMLParser

from anthropic_resources import fetch, parse_llms

_IMG_MD_RE = re.compile(r"(!\[[^\]]*\]\()([^)\s]+)(\))")
_IMG_HTML_RE = re.compile(r'(<img[^>]*?\ssrc=")([^"]+)(")', re.IGNORECASE)

# --------------------------------------------------------------------------- #
# Curation
# --------------------------------------------------------------------------- #

PLATFORM_INDEX = "https://platform.claude.com/llms.txt"
PLATFORM_BASE_URL = "https://platform.claude.com/docs/en/"
PLATFORM_ALLOW = [
    "intro.md",
    "get-started.md",
    "build-with-claude/",
    "agents-and-tools/tool-use/",
    "agents-and-tools/agent-skills/",
    "agents-and-tools/remote-mcp-servers.md",
    "agents-and-tools/mcp-connector.md",
]
PLATFORM_DENY = [
    "build-with-claude/claude-in-",
    "build-with-claude/claude-on-",
    "build-with-claude/claude-platform-on-aws",
    "build-with-claude/cache-diagnostics",
    "build-with-claude/fallback-credit",
    "build-with-claude/mid-conversation-",
    "build-with-claude/fast-mode",
]

CLAUDE_CODE_INDEX = "https://code.claude.com/docs/llms.txt"
CLAUDE_CODE_BASE_URL = "https://code.claude.com/docs/en/"
CLAUDE_CODE_PAGES = [
    "overview.md",
    "quickstart.md",
    "how-claude-code-works.md",
    "features-overview.md",
    "setup.md",
    "common-workflows.md",
    "best-practices.md",
    "interactive-mode.md",
    "cli-reference.md",
    "memory.md",
    "settings.md",
    "model-config.md",
    "output-styles.md",
    "statusline.md",
    "commands.md",
    "sub-agents.md",
    "skills.md",
    "hooks.md",
    "plugins.md",
    "mcp.md",
    "permissions.md",
    "permission-modes.md",
    "checkpointing.md",
    "costs.md",
    "sandboxing.md",
    "security.md",
    "headless.md",
    "github-actions.md",
    "troubleshooting.md",
    "agent-sdk/overview.md",
    "agent-sdk/quickstart.md",
    "agent-sdk/agent-loop.md",
    "agent-sdk/custom-tools.md",
    "agent-sdk/permissions.md",
    "agent-sdk/sessions.md",
    "agent-sdk/subagents.md",
    "agent-sdk/skills.md",
    "agent-sdk/slash-commands.md",
    "agent-sdk/streaming-output.md",
    "agent-sdk/mcp.md",
    "agent-sdk/cost-tracking.md",
]

# (slug, url) — essays have no machine index, so they're curated by hand.
ESSAYS = [
    (
        "building-effective-agents",
        "https://www.anthropic.com/research/building-effective-agents",
    ),
    (
        "effective-context-engineering",
        "https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents",
    ),
    (
        "writing-tools-for-agents",
        "https://www.anthropic.com/engineering/writing-tools-for-agents",
    ),
    (
        "effective-harnesses-for-long-running-agents",
        "https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents",
    ),
    (
        "claude-code-best-practices",
        "https://www.anthropic.com/engineering/claude-code-best-practices",
    ),
    (
        "equipping-agents-with-skills",
        "https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills",
    ),
    ("introducing-mcp", "https://www.anthropic.com/news/model-context-protocol"),
]


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def select_doc_paths(paths, allow=None, deny=None, explicit=None):
    """Select doc paths by allow/deny prefixes, or by an explicit list.

    With `explicit`, every requested path must be present in `paths`; a missing
    one raises ValueError (fail-loud — the curated list has gone stale).
    """
    if explicit is not None:
        available = set(paths)
        missing = [p for p in explicit if p not in available]
        if missing:
            raise ValueError(f"curated pages missing from index: {missing}")
        return [p for p in paths if p in set(explicit)]

    allow = allow or []
    deny = deny or []
    selected = []
    for p in paths:
        if any(p.startswith(a) for a in allow) and not any(d in p for d in deny):
            selected.append(p)
    return selected


def local_path_for(rel_path, base, out_dir):
    return f"{out_dir}/{base}/{rel_path}"


def _normalize_img_src(src, origin):
    """Turn a doc image src into a fetchable absolute URL.

    Anthropic docs render images through a Next.js proxy
    (`/_next/image?url=<encoded real URL>&w=..`) and reference site-relative
    paths (`/docs/images/x.svg`). Both are unresolvable once the page is pulled
    out of the site, so decode the proxy and give site-relative paths an origin.
    """
    if src.startswith("/_next/image"):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(src).query)
        if params.get("url"):
            src = params["url"][0]  # parse_qs already URL-decodes
    if src.startswith("/"):
        src = origin + src
    return src


def rewrite_doc_image_urls(md, origin):
    """Rewrite Next.js-proxy and site-relative image srcs to absolute URLs.

    Non-code regions are rewritten as whole blocks (not line by line) so that
    images whose alt text wraps across lines are still matched. Fenced code
    blocks are left untouched.
    """

    def sub(text):
        text = _IMG_MD_RE.sub(
            lambda m: m.group(1) + _normalize_img_src(m.group(2), origin) + m.group(3),
            text,
        )
        return _IMG_HTML_RE.sub(
            lambda m: m.group(1) + _normalize_img_src(m.group(2), origin) + m.group(3),
            text,
        )

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


def _origin_of(url):
    p = urllib.parse.urlparse(url)
    return f"{p.scheme}://{p.netloc}"


class _MainContentExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.capturing = False
        self.depth = 0
        self.parts = []
        self.found = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if not self.capturing and tag == "div" and a.get("id") == "main-content":
            self.capturing = True
            self.found = True
            self.depth = 0
        if self.capturing:
            if tag == "div":
                self.depth += 1
            self.parts.append(self.get_starttag_text() or f"<{tag}>")

    def handle_startendtag(self, tag, attrs):
        if self.capturing:
            self.parts.append(self.get_starttag_text() or f"<{tag}/>")

    def handle_endtag(self, tag):
        if self.capturing:
            self.parts.append(f"</{tag}>")
            if tag == "div":
                self.depth -= 1
                if self.depth == 0:
                    self.capturing = False

    def handle_data(self, data):
        if self.capturing:
            self.parts.append(data)


def extract_main_content(html):
    """Return the inner HTML of the page's `#main-content` div, else the input."""
    parser = _MainContentExtractor()
    parser.feed(html)
    return "".join(parser.parts) if parser.found else html


def _is_standalone_tag_line(line):
    s = line.strip()
    return s.startswith("<") and s.endswith(">") and "](" not in s


# Headings that mark the start of the anthropic.com site mega-footer; everything
# from the earliest one onward is navigation chrome, not article content.
FOOTER_SENTINELS = (
    "## Get the developer newsletter",
    "### Products",
    "### Help and security",
)


def clean_essay_markdown(md):
    """Drop HTML chrome, cut to the first H1, drop the site footer, tidy blanks."""
    lines = [ln for ln in md.splitlines() if not _is_standalone_tag_line(ln)]

    for i, ln in enumerate(lines):
        if ln.startswith("# "):
            lines = lines[i:]
            break

    cut = next(
        (i for i, ln in enumerate(lines) if ln.strip() in FOOTER_SENTINELS), None
    )
    if cut is not None:
        lines = lines[:cut]

    out, blank_run = [], 0
    for ln in lines:
        if ln.strip() == "":
            blank_run += 1
            if blank_run > 1:
                continue
        else:
            blank_run = 0
        out.append(ln)
    while out and out[0].strip() == "":
        out.pop(0)
    while out and out[-1].strip() == "":
        out.pop()
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- #
# I/O edges
# --------------------------------------------------------------------------- #


def _index_paths(index_url, base_url):
    text = fetch(index_url)
    rel = []
    for row in parse_llms(text, "idx"):
        url = row["url"]
        if url.startswith(base_url) and url.endswith(".md"):
            rel.append(url[len(base_url) :])
    return rel


def _write(path, content):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _html_to_markdown(html_fragment):
    proc = subprocess.run(
        ["pandoc", "-f", "html", "-t", "gfm", "--wrap=none"],
        input=html_fragment,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pandoc html->md failed: {proc.stderr.strip()}")
    return proc.stdout


def fetch_md_pages(rel_paths, base_url, base, out_dir, force, failures):
    written = 0
    for rel in rel_paths:
        dest = local_path_for(rel, base, out_dir)
        if not force and os.path.isfile(dest):
            written += 1
            continue
        try:
            content = fetch(base_url + rel)
            if len(content) < 200 or "<html" in content[:500].lower():
                raise RuntimeError(f"unexpected non-markdown body ({len(content)} B)")
            content = rewrite_doc_image_urls(content, _origin_of(base_url))
            _write(dest, content)
            written += 1
            print(f"  [md] {dest}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001 - fail-loud, collected below
            failures.append(f"{base_url + rel}: {e}")
    return written


def fetch_essays(out_dir, force, failures):
    written = 0
    for slug, url in ESSAYS:
        dest = f"{out_dir}/essays/{slug}.md"
        if not force and os.path.isfile(dest):
            written += 1
            continue
        try:
            html = fetch(url)
            md = clean_essay_markdown(_html_to_markdown(extract_main_content(html)))
            md = rewrite_doc_image_urls(md, _origin_of(url))
            if len(md) < 400:
                raise RuntimeError(f"essay too short after extraction ({len(md)} B)")
            _write(dest, md)
            written += 1
            print(f"  [essay] {dest}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001 - fail-loud, collected below
            failures.append(f"{url}: {e}")
    return written


def main():
    ap = argparse.ArgumentParser(description="Fetch web-only Claude docs into docs/.")
    ap.add_argument("--out-dir", default="docs")
    ap.add_argument("--force", action="store_true", help="Re-fetch existing files.")
    args = ap.parse_args()

    failures = []

    print("[*] Platform docs index...", file=sys.stderr)
    platform_paths = select_doc_paths(
        _index_paths(PLATFORM_INDEX, PLATFORM_BASE_URL),
        allow=PLATFORM_ALLOW,
        deny=PLATFORM_DENY,
    )
    n_platform = fetch_md_pages(
        platform_paths,
        PLATFORM_BASE_URL,
        "platform",
        args.out_dir,
        args.force,
        failures,
    )

    print("[*] Claude Code docs index...", file=sys.stderr)
    cc_paths = select_doc_paths(
        _index_paths(CLAUDE_CODE_INDEX, CLAUDE_CODE_BASE_URL),
        explicit=CLAUDE_CODE_PAGES,
    )
    n_cc = fetch_md_pages(
        cc_paths,
        CLAUDE_CODE_BASE_URL,
        "claude-code",
        args.out_dir,
        args.force,
        failures,
    )

    print("[*] Engineering essays...", file=sys.stderr)
    n_essay = fetch_essays(args.out_dir, args.force, failures)

    print(
        f"[✓] platform:{n_platform}  claude-code:{n_cc}  essays:{n_essay}",
        file=sys.stderr,
    )
    if failures:
        print(f"\n[!] {len(failures)} failures:", file=sys.stderr)
        for f in failures:
            print(f"    {f}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
