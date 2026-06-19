#!/usr/bin/env python3
"""
anthropic_resources.py
======================

Build a categorized collection of *official* Anthropic / Claude resources by:

  1. Parsing Anthropic's machine-readable `llms.txt` index files
     (every documentation page, already enumerated by Anthropic).
  2. Enumerating content from locally cloned official GitHub repos
     (cookbooks, courses, skills, MCP spec/docs, etc.).
  3. Merging in a small curated seed list for things that have no machine
     index (engineering blog posts, news/research hubs, course platform).

Outputs (next to this script): anthropic_resources.{md,json,csv}

Zero third-party dependencies. Python 3.8+.

Clone the official repos once (from the project root):

    mkdir -p anthropic-collection && cd anthropic-collection
    for repo in \\
      anthropics/claude-cookbooks \\
      anthropics/courses \\
      anthropics/prompt-eng-interactive-tutorial \\
      anthropics/skills \\
      anthropics/anthropic-quickstarts \\
      anthropics/claude-plugins-official \\
      modelcontextprotocol/modelcontextprotocol ; do
        git clone --depth 1 "https://github.com/$repo.git"
    done

Usage:
    python3 anthropic_resources.py                 # full harvest
    python3 anthropic_resources.py --no-api-ref    # skip the ~1500 per-endpoint API pages
    python3 anthropic_resources.py --no-local      # skip local repo enumeration
    python3 anthropic_resources.py --github-api    # also enumerate orgs via GitHub REST API
    python3 anthropic_resources.py --github-token GHTOKEN   # raise GitHub rate limit
    python3 anthropic_resources.py --repos-dir path/to/clones
    python3 anthropic_resources.py --out mydir/collection   # custom output prefix
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPOS_DIR = os.path.join(SCRIPT_DIR, "anthropic-collection")

# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #

# Anthropic publishes one llms.txt per docs surface. Each lists every page as a
# Markdown link; appending nothing is needed — the URLs already end in `.md`,
# so each entry is directly fetchable as raw Markdown if you want the content.
LLMS_SOURCES = [
    ("Claude Developer Platform", "https://platform.claude.com/llms.txt"),
    ("Claude Code", "https://code.claude.com/docs/llms.txt"),
    ("Model Context Protocol", "https://modelcontextprotocol.io/llms.txt"),
]

# Official repos cloned locally (org/repo slug -> directory name is the repo).
LOCAL_REPOS = [
    "anthropics/claude-cookbooks",
    "anthropics/courses",
    "anthropics/prompt-eng-interactive-tutorial",
    "anthropics/skills",
    "anthropics/anthropic-quickstarts",
    "anthropics/claude-plugins-official",
    "modelcontextprotocol/modelcontextprotocol",
]

# When the MCP repo is cloned locally, skip fetching modelcontextprotocol.io/llms.txt.
LOCAL_MCP_REPO = "modelcontextprotocol/modelcontextprotocol"

# Official GitHub orgs — only queried when --github-api is passed.
GITHUB_ORGS = ["anthropics", "modelcontextprotocol"]

CONTENT_EXTENSIONS = {".md", ".ipynb"}
SKIP_DIRS = {
    ".git",
    ".github",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".tox",
    ".pytest_cache",
    ".mypy_cache",
}
SKIP_FILENAMES = {
    "license.md",
    "contributing.md",
    "changelog.md",
    "code_of_conduct.md",
    "security.md",
    "agents.md",
    "claude.md",
}

# Curated seeds: durable official URLs that no llms.txt indexes (the
# engineering blog and news/research have no clean machine index).
SEED_LINKS = [
    (
        "Engineering Blog",
        "Engineering blog (hub)",
        "https://www.anthropic.com/engineering",
        "",
    ),
    (
        "Engineering Blog",
        "Building effective agents",
        "https://www.anthropic.com/research/building-effective-agents",
        "",
    ),
    (
        "Engineering Blog",
        "Effective context engineering for AI agents",
        "https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents",
        "",
    ),
    (
        "Engineering Blog",
        "Writing effective tools for agents — with agents",
        "https://www.anthropic.com/engineering/writing-tools-for-agents",
        "",
    ),
    (
        "Engineering Blog",
        "Effective harnesses for long-running agents",
        "https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents",
        "",
    ),
    (
        "Engineering Blog",
        "Claude Code: Best practices for agentic coding",
        "https://www.anthropic.com/engineering/claude-code-best-practices",
        "",
    ),
    (
        "Engineering Blog",
        "Equipping agents for the real world with Agent Skills",
        "https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills",
        "",
    ),
    ("Learning", "Anthropic Academy (hub)", "https://www.anthropic.com/learn", ""),
    (
        "Learning",
        "Build with Claude (developer guide)",
        "https://www.anthropic.com/learn/build-with-claude",
        "",
    ),
    ("Learning", "Course platform (Skilljar)", "https://anthropic.skilljar.com", ""),
    (
        "News & Research",
        "News (announcements, model cards, launches)",
        "https://www.anthropic.com/news",
        "",
    ),
    ("News & Research", "Research", "https://www.anthropic.com/research", ""),
    ("MCP", "Model Context Protocol (home)", "https://modelcontextprotocol.io", ""),
    (
        "MCP",
        "Introducing the Model Context Protocol (announcement)",
        "https://www.anthropic.com/news/model-context-protocol",
        "",
    ),
]

USER_AGENT = "anthropic-resources-harvester/1.0 (personal use)"

HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$")
LINK_RE = re.compile(
    r"^\s*-\s*\[(?P<title>[^\]]+)\]\((?P<url>[^)]+)\)"
    # Description separator: dash (platform llms.txt) or colon (Claude Code llms.txt).
    r"(?:\s*[-–—:]\s*(?P<desc>.*))?$"
)
MD_TITLE_RE = re.compile(r"^#\s+(.+)$")

PATH_CATEGORIES = [
    ("/api/", "API Reference"),
    ("/agents-and-tools/", "Agents & Tools"),
    ("/build-with-claude/", "Build with Claude"),
    ("/managed-agents/", "Managed Agents"),
    ("/manage-claude/", "Admin & Management"),
    ("/about-claude/", "About Claude & Models"),
    ("/test-and-evaluate/", "Test & Evaluate"),
    ("/release-notes/", "Release Notes"),
    ("code.claude.com", "Claude Code"),
    ("modelcontextprotocol.io", "MCP"),
]


def categorize(url, fallback):
    for frag, name in PATH_CATEGORIES:
        if frag in url:
            return name
    return fallback


def local_mcp_available(repos_dir):
    org, name = LOCAL_MCP_REPO.split("/", 1)
    return os.path.isdir(os.path.join(repos_dir, name))


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #


def fetch(url, token=None, timeout=30, retries=3):
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if token and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    req = urllib.request.Request(url, headers=headers)
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
                last = e
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last}")


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #


def parse_llms(text, source_label):
    section = "(root)"
    for line in text.splitlines():
        h = HEADER_RE.match(line)
        if h:
            if len(h.group(1)) in (2, 3):
                section = h.group(2).strip()
            continue
        m = LINK_RE.match(line)
        if m:
            url = m.group("url").strip()
            if not url.startswith("http"):
                continue
            yield {
                "source": source_label,
                "category": categorize(url, source_label),
                "section": section,
                "title": m.group("title").strip(),
                "url": url,
                "description": (m.group("desc") or "").strip(),
            }


def github_repos(org, token=None):
    out, page = [], 1
    while True:
        url = (
            f"https://api.github.com/orgs/{org}/repos"
            f"?per_page=100&page={page}&type=public&sort=full_name"
        )
        data = json.loads(fetch(url, token=token))
        if not data:
            break
        for r in data:
            if r.get("fork") or r.get("archived"):
                continue
            out.append(
                {
                    "source": f"GitHub: {org}",
                    "category": f"GitHub ({org})",
                    "section": "Repositories",
                    "title": r["full_name"],
                    "url": r["html_url"],
                    "description": (r.get("description") or "").strip(),
                    "stars": r.get("stargazers_count", 0),
                }
            )
        if len(data) < 100:
            break
        page += 1
        time.sleep(0.5)
    out.sort(key=lambda x: x.get("stars", 0), reverse=True)
    return out


def _read_readme_blurb(repo_path):
    for name in ("README.md", "readme.md", "Readme.md"):
        readme = os.path.join(repo_path, name)
        if not os.path.isfile(readme):
            continue
        try:
            with open(readme, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            return ""
        body = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            body.append(stripped)
            if len(body) >= 2:
                break
        return " ".join(body)[:300]
    return ""


def _title_from_markdown(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = MD_TITLE_RE.match(line.strip())
                if m:
                    return m.group(1).strip()
                if line.strip():
                    break
    except OSError:
        pass
    base = os.path.basename(path)
    stem, _ = os.path.splitext(base)
    if stem.upper() == "SKILL":
        return os.path.basename(os.path.dirname(path))
    return stem.replace("-", " ").replace("_", " ").title()


def _local_category(org, repo_slug):
    if org == "modelcontextprotocol":
        return "MCP"
    return f"GitHub ({org})"


def _relative_path(path):
    return os.path.relpath(path, SCRIPT_DIR).replace(os.sep, "/")


def local_repo_resources(repos_dir):
    """Enumerate cloned repos and their markdown/notebook content."""
    for repo_slug in LOCAL_REPOS:
        org, name = repo_slug.split("/", 1)
        repo_path = os.path.join(repos_dir, name)
        if not os.path.isdir(repo_path):
            print(
                f"    !! missing local clone: {repo_slug} (expected {repo_path})",
                file=sys.stderr,
            )
            continue

        category = _local_category(org, repo_slug)
        github_url = f"https://github.com/{repo_slug}"

        yield {
            "source": f"Local: {org}",
            "category": category,
            "section": "Repositories",
            "title": repo_slug,
            "url": _relative_path(repo_path),
            "description": _read_readme_blurb(repo_path),
            "github_url": github_url,
        }

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = sorted(
                d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")
            )
            rel_dir = os.path.relpath(root, repo_path)
            section = (
                name if rel_dir == "." else f"{name}/{rel_dir.replace(os.sep, '/')}"
            )

            for fname in sorted(files):
                ext = os.path.splitext(fname)[1].lower()
                if ext not in CONTENT_EXTENSIONS:
                    continue
                if fname.lower() in SKIP_FILENAMES:
                    continue

                full_path = os.path.join(root, fname)
                title = _title_from_markdown(full_path) if ext == ".md" else fname

                yield {
                    "source": f"Local: {repo_slug}",
                    "category": category,
                    "section": section,
                    "title": title,
                    "url": _relative_path(full_path),
                    "description": "",
                    "github_url": github_url,
                }


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #


def write_outputs(rows, prefix):
    os.makedirs(os.path.dirname(prefix) or ".", exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    with open(prefix + ".json", "w", encoding="utf-8") as f:
        json.dump(
            {"generated": ts, "count": len(rows), "resources": rows},
            f,
            indent=2,
            ensure_ascii=False,
        )

    fieldnames = [
        "category",
        "section",
        "title",
        "url",
        "description",
        "source",
        "stars",
        "github_url",
    ]
    with open(prefix + ".csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})

    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["category"], {}).setdefault(
            r.get("section", ""), []
        ).append(r)
    with open(prefix + ".md", "w", encoding="utf-8") as f:
        f.write("# Official Anthropic / Claude resource collection\n\n")
        f.write(f"_Generated {ts} — {len(rows)} links_\n\n")
        for cat in sorted(by_cat):
            f.write(f"## {cat}\n\n")
            for section in sorted(by_cat[cat]):
                items = by_cat[cat][section]
                if section and section not in ("(root)", "Repositories"):
                    f.write(f"### {section}\n\n")
                for r in sorted(items, key=lambda x: x["title"].lower()):
                    desc = f" — {r['description']}" if r.get("description") else ""
                    star = f" ⭐{r['stars']}" if r.get("stars") else ""
                    gh = (
                        f" ([GitHub]({r['github_url']}))"
                        if r.get("github_url") and not r["url"].startswith("http")
                        else ""
                    )
                    f.write(f"- [{r['title']}]({r['url']}){desc}{star}{gh}\n")
                f.write("\n")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main():
    ap = argparse.ArgumentParser(description="Harvest official Anthropic resources.")
    ap.add_argument(
        "--no-api-ref",
        action="store_true",
        help="Drop the ~1500 per-endpoint API-reference pages.",
    )
    ap.add_argument(
        "--no-local", action="store_true", help="Skip local cloned-repo enumeration."
    )
    ap.add_argument(
        "--github-api",
        action="store_true",
        help="Also enumerate GitHub orgs via REST API (rate-limited).",
    )
    ap.add_argument(
        "--no-seeds",
        action="store_true",
        help="Skip the curated engineering/news seed list.",
    )
    ap.add_argument(
        "--github-token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub token to raise rate limits (or set GITHUB_TOKEN).",
    )
    ap.add_argument(
        "--repos-dir",
        default=DEFAULT_REPOS_DIR,
        help=f"Directory of cloned repos (default: {DEFAULT_REPOS_DIR}).",
    )
    ap.add_argument(
        "--out",
        default="anthropic_resources",
        help="Output path prefix (default: ./anthropic_resources).",
    )
    args = ap.parse_args()

    repos_dir = os.path.abspath(args.repos_dir)
    rows, seen = [], set()

    def add(row):
        u = row["url"].rstrip("/")
        if u in seen:
            return
        seen.add(u)
        rows.append(row)

    skip_mcp_llms = not args.no_local and local_mcp_available(repos_dir)

    # 1) llms.txt indexes (MCP skipped when cloned locally)
    for label, url in LLMS_SOURCES:
        if skip_mcp_llms and label == "Model Context Protocol":
            print(
                "[*] Skipping MCP llms.txt — using local clone instead", file=sys.stderr
            )
            continue
        try:
            print(f"[*] Fetching index: {url}", file=sys.stderr)
            for row in parse_llms(fetch(url), label):
                if args.no_api_ref and row["category"] == "API Reference":
                    continue
                add(row)
        except Exception as e:
            print(f"    !! {url}: {e}", file=sys.stderr)

    # 2) Local cloned repos
    if not args.no_local:
        print(f"[*] Enumerating local repos: {repos_dir}", file=sys.stderr)
        for row in local_repo_resources(repos_dir):
            add(row)

    # 3) Optional GitHub API discovery
    if args.github_api:
        for org in GITHUB_ORGS:
            try:
                print(f"[*] Enumerating GitHub org via API: {org}", file=sys.stderr)
                for row in github_repos(org, token=args.github_token):
                    add(row)
            except Exception as e:
                print(f"    !! github/{org}: {e}", file=sys.stderr)

    # 4) Seeds
    if not args.no_seeds:
        for cat, title, url, desc in SEED_LINKS:
            add(
                {
                    "source": "curated",
                    "category": cat,
                    "section": "",
                    "title": title,
                    "url": url,
                    "description": desc,
                }
            )

    write_outputs(rows, args.out)
    print(
        f"[✓] {len(rows)} unique links -> {args.out}.md / .json / .csv", file=sys.stderr
    )


if __name__ == "__main__":
    main()
