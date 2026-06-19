#!/usr/bin/env python3
"""
anthropic_resources.py
======================

Build a categorized collection of *official* Anthropic / Claude resources by:

  1. Parsing Anthropic's machine-readable `llms.txt` index files
     (every documentation page, already enumerated by Anthropic).
  2. Enumerating official GitHub repos via the GitHub REST API.
  3. Merging in a small curated seed list for things that have no machine
     index (engineering blog posts, news/research hubs, course platform).

Outputs (next to this script): anthropic_resources.{md,json,csv}

Zero third-party dependencies. Python 3.8+.

Usage:
    python3 anthropic_resources.py                 # full harvest
    python3 anthropic_resources.py --no-api-ref    # skip the ~1500 per-endpoint API pages
    python3 anthropic_resources.py --no-github     # skip GitHub enumeration
    python3 anthropic_resources.py --github-token GHTOKEN   # raise GitHub rate limit
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

# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #

# Anthropic publishes one llms.txt per docs surface. Each lists every page as a
# Markdown link; appending nothing is needed — the URLs already end in `.md`,
# so each entry is directly fetchable as raw Markdown if you want the content.
LLMS_SOURCES = [
    ("Claude Developer Platform", "https://platform.claude.com/llms.txt"),
    ("Claude Code",               "https://code.claude.com/docs/en/llms.txt"),
    ("Model Context Protocol",    "https://modelcontextprotocol.io/llms.txt"),
]

# Official GitHub orgs. Public, non-fork repos are enumerated via the API.
GITHUB_ORGS = ["anthropics", "modelcontextprotocol"]

# Curated seeds: durable official URLs that no llms.txt indexes (the
# engineering blog and news/research have no clean machine index).
SEED_LINKS = [
    ("Engineering Blog", "Engineering blog (hub)",
     "https://www.anthropic.com/engineering", ""),
    ("Engineering Blog", "Building effective agents",
     "https://www.anthropic.com/research/building-effective-agents", ""),
    ("Engineering Blog", "Effective context engineering for AI agents",
     "https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents", ""),
    ("Engineering Blog", "Writing effective tools for agents — with agents",
     "https://www.anthropic.com/engineering/writing-tools-for-agents", ""),
    ("Engineering Blog", "Effective harnesses for long-running agents",
     "https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents", ""),
    ("Engineering Blog", "Claude Code: Best practices for agentic coding",
     "https://www.anthropic.com/engineering/claude-code-best-practices", ""),
    ("Engineering Blog", "Equipping agents for the real world with Agent Skills",
     "https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills", ""),
    ("Learning", "Anthropic Academy (hub)",
     "https://www.anthropic.com/learn", ""),
    ("Learning", "Build with Claude (developer guide)",
     "https://www.anthropic.com/learn/build-with-claude", ""),
    ("Learning", "Course platform (Skilljar)",
     "https://anthropic.skilljar.com", ""),
    ("News & Research", "News (announcements, model cards, launches)",
     "https://www.anthropic.com/news", ""),
    ("News & Research", "Research",
     "https://www.anthropic.com/research", ""),
    ("MCP", "Model Context Protocol (home)",
     "https://modelcontextprotocol.io", ""),
    ("MCP", "Introducing the Model Context Protocol (announcement)",
     "https://www.anthropic.com/news/model-context-protocol", ""),
]

USER_AGENT = "anthropic-resources-harvester/1.0 (personal use)"

# Markdown patterns in llms.txt:  "## Section"  and  "- [Title](url) - description"
HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$")
LINK_RE = re.compile(
    r"^\s*-\s*\[(?P<title>[^\]]+)\]\((?P<url>[^)]+)\)"
    r"(?:\s*[-–—]\s*(?P<desc>.*))?$"
)

# Map URL path fragments -> a friendly top-level category, so the output is
# organized "a level deeper" rather than one flat dump.
PATH_CATEGORIES = [
    ("/api/",                 "API Reference"),
    ("/agents-and-tools/",    "Agents & Tools"),
    ("/build-with-claude/",   "Build with Claude"),
    ("/managed-agents/",      "Managed Agents"),
    ("/manage-claude/",       "Admin & Management"),
    ("/about-claude/",        "About Claude & Models"),
    ("/test-and-evaluate/",   "Test & Evaluate"),
    ("/release-notes/",       "Release Notes"),
    ("code.claude.com",       "Claude Code"),
    ("modelcontextprotocol.io", "MCP"),
]


def categorize(url, fallback):
    for frag, name in PATH_CATEGORIES:
        if frag in url:
            return name
    return fallback


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
                time.sleep(5 * (attempt + 1))  # rate limited; back off
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
        url = (f"https://api.github.com/orgs/{org}/repos"
               f"?per_page=100&page={page}&type=public&sort=full_name")
        data = json.loads(fetch(url, token=token))
        if not data:
            break
        for r in data:
            if r.get("fork") or r.get("archived"):
                continue
            out.append({
                "source": f"GitHub: {org}",
                "category": f"GitHub ({org})",
                "section": "Repositories",
                "title": r["full_name"],
                "url": r["html_url"],
                "description": (r.get("description") or "").strip(),
                "stars": r.get("stargazers_count", 0),
            })
        if len(data) < 100:
            break
        page += 1
        time.sleep(0.5)
    out.sort(key=lambda x: x.get("stars", 0), reverse=True)
    return out


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

def write_outputs(rows, prefix):
    os.makedirs(os.path.dirname(prefix) or ".", exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # JSON
    with open(prefix + ".json", "w", encoding="utf-8") as f:
        json.dump({"generated": ts, "count": len(rows), "resources": rows},
                  f, indent=2, ensure_ascii=False)

    # CSV
    with open(prefix + ".csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["category", "section", "title", "url",
                           "description", "source", "stars"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})

    # Markdown, grouped by category then section
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["category"], {}).setdefault(
            r.get("section", ""), []).append(r)
    with open(prefix + ".md", "w", encoding="utf-8") as f:
        f.write(f"# Official Anthropic / Claude resource collection\n\n")
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
                    f.write(f"- [{r['title']}]({r['url']}){desc}{star}\n")
                f.write("\n")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    ap = argparse.ArgumentParser(description="Harvest official Anthropic resources.")
    ap.add_argument("--no-api-ref", action="store_true",
                    help="Drop the ~1500 per-endpoint API-reference pages.")
    ap.add_argument("--no-github", action="store_true",
                    help="Skip GitHub repo enumeration.")
    ap.add_argument("--no-seeds", action="store_true",
                    help="Skip the curated engineering/news seed list.")
    ap.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"),
                    help="GitHub token to raise rate limits (or set GITHUB_TOKEN).")
    ap.add_argument("--out", default="anthropic_resources",
                    help="Output path prefix (default: ./anthropic_resources).")
    args = ap.parse_args()

    rows, seen = [], set()

    def add(row):
        u = row["url"].rstrip("/")
        if u in seen:
            return
        seen.add(u)
        rows.append(row)

    # 1) llms.txt indexes
    for label, url in LLMS_SOURCES:
        try:
            print(f"[*] Fetching index: {url}", file=sys.stderr)
            for row in parse_llms(fetch(url), label):
                if args.no_api_ref and row["category"] == "API Reference":
                    continue
                add(row)
        except Exception as e:
            print(f"    !! {url}: {e}", file=sys.stderr)

    # 2) GitHub
    if not args.no_github:
        for org in GITHUB_ORGS:
            try:
                print(f"[*] Enumerating GitHub org: {org}", file=sys.stderr)
                for row in github_repos(org, token=args.github_token):
                    add(row)
            except Exception as e:
                print(f"    !! github/{org}: {e}", file=sys.stderr)

    # 3) Seeds
    if not args.no_seeds:
        for cat, title, url, desc in SEED_LINKS:
            add({"source": "curated", "category": cat, "section": "",
                 "title": title, "url": url, "description": desc})

    write_outputs(rows, args.out)
    print(f"[✓] {len(rows)} unique links -> "
          f"{args.out}.md / .json / .csv", file=sys.stderr)


if __name__ == "__main__":
    main()
