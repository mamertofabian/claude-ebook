I'll search for official Anthropic resources across the main categories — documentation, cookbooks, blogs, prompt engineering guides, Claude Code, and more. Let me gather these systematically.Good start. Let me search for the Anthropic Cookbook and prompt engineering resources.The official Anthropic GitHub org has many repos. Let me search for their engineering blog and key best-practices posts.The engineering blog has a rich archive. Let me find the prompt engineering tutorials and courses.Let me get the prompt engineering documentation pages and the Agent Skills resources.Now let me capture Agent Skills, MCP, and the news/announcements resources.Let me get Model Context Protocol resources and the Anthropic resources/guides hub.Let me round this out with the Anthropic Academy learning hub and the Claude Code documentation structure.Let me capture the news/research hub and the machine-readable docs index, which will be especially useful for bulk-pulling.Here's a compiled set of official, first-party Anthropic resources, organized by category. I've stuck to canonical Anthropic-owned domains (anthropic.com, claude.com, docs/platform/code.claude.com, github.com/anthropics, modelcontextprotocol.io) and excluded the many third-party mirrors that surfaced.

## ⭐ Best starting point for bulk-pulling

Anthropic publishes machine-readable documentation indexes — these are the single most efficient way to grab everything at once rather than scraping page by page:

- **Slim index:** https://docs.anthropic.com/llms.txt (links to all ~1,540 doc pages)
- **Full content export:** https://platform.claude.com/llms-full.txt (entire docs as one Markdown file)
- **Claude Code docs index:** https://code.claude.com/docs/en/llms.txt

## Core documentation hubs

- Developer Platform docs (home): https://platform.claude.com/docs/en/home — also resolves at https://docs.anthropic.com/en/home
- API overview: https://platform.claude.com/docs/en/api/overview
- Intro to Claude: https://docs.anthropic.com/en/docs/intro-to-claude
- Models overview: https://platform.claude.com/docs/en/about-claude/models/overview
- Claude Code docs (home): https://code.claude.com/docs/en/overview
- Claude Code best practices (docs): https://code.claude.com/docs/en/best-practices

## Prompt engineering

- Prompt engineering overview: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview
- Prompting best practices (living reference): https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices

## Agent Skills & MCP (docs)

- Agent Skills overview: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- Model Context Protocol home: https://modelcontextprotocol.io
- MCP announcement (Anthropic): https://www.anthropic.com/news/model-context-protocol

## Engineering blog (confirmed post URLs)

Hub: https://www.anthropic.com/engineering

- Building effective agents: https://www.anthropic.com/research/building-effective-agents
- Effective context engineering for AI agents: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Writing effective tools for agents — with agents: https://www.anthropic.com/engineering/writing-tools-for-agents
- Effective harnesses for long-running agents: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- Claude Code: Best practices for agentic coding: https://www.anthropic.com/engineering/claude-code-best-practices
- Equipping agents for the real world with Agent Skills: https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills

Additional posts I saw in the archive but whose exact slugs I didn't individually confirm (grab them from the hub above): "How we built our multi-agent research system," "Code execution with MCP," "Building agents with the Claude Agent SDK," "Beyond permission prompts," "A postmortem of three recent issues," "Desktop Extensions," "The 'think' tool," "Raising the bar on SWE-bench Verified," and "Introducing Contextual Retrieval."

## Official GitHub repositories (github.com/anthropics)

- Org index: https://github.com/anthropics
- Claude Cookbooks (notebooks/recipes — formerly `anthropic-cookbook`): https://github.com/anthropics/claude-cookbooks
- Courses (5 educational courses): https://github.com/anthropics/courses
- Interactive Prompt Engineering Tutorial: https://github.com/anthropics/prompt-eng-interactive-tutorial
- Agent Skills (public skills repo): https://github.com/anthropics/skills
- Claude Code: https://github.com/anthropics/claude-code
- Official Claude Code plugins directory: https://github.com/anthropics/claude-plugins-official
- Claude Agent SDK (Python): https://github.com/anthropics/claude-agent-sdk-python
- Anthropic Quickstarts: https://github.com/anthropics/anthropic-quickstarts
- MCP spec & docs: https://github.com/modelcontextprotocol/modelcontextprotocol

## Learning / Anthropic Academy

- Academy hub: https://www.anthropic.com/learn
- Build with Claude (developer guide): https://www.anthropic.com/learn/build-with-claude
- Course platform (Skilljar, free + certificates): https://anthropic.skilljar.com

## News & research (announcements, model cards, launch posts)

- News: https://www.anthropic.com/news
- Research: https://www.anthropic.com/research

Two practical notes for your compile step: the cookbook repo was renamed from `anthropic-cookbook` to `claude-cookbooks`, so old links may 404 or redirect — use the new one. And much of the developer documentation now lives canonically under `platform.claude.com` / `code.claude.com`, with `docs.anthropic.com` still resolving for many pages, so you may hit duplicate content across those domains when pulling.

Want me to go a level deeper on any one category — e.g., enumerate every Claude Code doc subpage (subagents, hooks, settings, GitHub Actions, headless mode) or the full course/notebook list inside the `courses` and `claude-cookbooks` repos?

=============

Going deeper by hand would mean me retyping hundreds of doc subpages from memory — error-prone and stale the moment Anthropic ships an update. The better path: Anthropic's own `llms.txt` indexes already enumerate every page, and the GitHub API enumerates every official repo. Let me pull the real indexes now so I can give you both an accurate deeper listing *and* a script that reproduces it on demand.The platform index confirms the format — every page is a parseable Markdown link, and each URL already ends in `.md` (so it's directly fetchable as raw Markdown). Let me grab the Claude Code index too, since you'd asked specifically about subagents/hooks/settings.I have what I need. The most durable deliverable here is a script that harvests these indexes for you (and re-runs whenever Anthropic updates them), rather than a hand-typed list that goes stale. Let me build it and test the parts I can reach from here (the GitHub API enumeration and the parser logic).Now let me test it. I can't reach the `*.claude.com` domains from this sandbox (restricted egress), but I can verify the GitHub enumeration live and the llms.txt parser against the real sample I just fetched.Parser works — categorization, sections, descriptions, and the API-reference filter all behave. Now the live GitHub enumeration:That 403 is the shared-sandbox IP hitting GitHub's unauthenticated rate limit (`x-ratelimit-remaining: 0`) — not a script bug. On your machine you get 60 req/hr unauthenticated (plenty for two orgs) or 5,000/hr with a token. Let me validate the repo-parsing path with a mock response so the JSON handling is confirmed too:Everything checks out — fork/archive filtering, star-sorting, dedup, categorization, and all three output formats generate cleanly. The only two things I couldn't exercise live are the `*.claude.com` fetch (sandbox egress) and the live GitHub call (shared-IP rate limit), both of which work normally on your machine. Let me stage the script for you.## How to run it

```bash
python3 anthropic_resources.py
```

That fetches Anthropic's three `llms.txt` indexes (Developer Platform, Claude Code, MCP), enumerates the `anthropics` and `modelcontextprotocol` GitHub orgs, merges a small curated seed list, dedupes, and writes `anthropic_resources.md`, `.json`, and `.csv` side by side. Stdlib only — nothing to `pip install`. Useful flags:

- `--no-api-ref` — drops the ~1,500 per-endpoint × per-language API stubs (the platform index is 1,752 pages, mostly these). Recommended unless you want the full API surface.
- `--github-token GHTOKEN` (or `GITHUB_TOKEN` env) — raises GitHub's limit from 60/hr to 5,000/hr.
- `--out path/prefix` — custom output location.

Since each indexed URL already ends in `.md`, you can pull the actual page content for any link with a trivial follow-up loop (`for url in ...: fetch(url)`) to build an offline mirror or a RAG corpus — which, given your MAID/skills work, is probably where this is headed.

## The "level deeper" breakdown (from the live indexes)

Here's what the indexes actually contain, so you know what the script harvests:

**Claude Developer Platform** (`platform.claude.com`, ~1,752 EN pages) splits into:
- *Agents & Tools* — tool use (define/handle/parallel/strict, bash, text-editor, computer-use, code-execution, web-search, web-fetch, memory, advisor tools), Agent Skills (overview, quickstart, best-practices, enterprise), MCP connector, remote MCP servers, MCP tunnels.
- *Build with Claude* — extended/adaptive thinking, prompt caching, context windows/editing/compaction, structured outputs, vision, PDF support, Files API, embeddings, citations, batch processing, streaming, token counting, multilingual, effort/task-budgets.
- *Managed Agents* — the newer agent-infra surface: sessions, environments, sandboxes, vaults, webhooks, memory stores, multi-agent.
- *Admin & Management* — Admin API, Analytics/Usage-Cost/Spend-Limits/Rate-Limits APIs, Compliance API, CMEK, Workload Identity Federation, workspaces, data residency/retention.
- *API Reference* — every endpoint, generated for 9 SDK languages (CLI, C#, Go, Java, PHP, Python, Ruby, Terraform, TypeScript). This is the bulk; `--no-api-ref` skips it.

**Claude Code** (`code.claude.com/docs`) — overview, best-practices, features-overview, plus the extension stack you asked about: CLAUDE.md/memory, slash commands, subagents, hooks, skills, plugins, MCP, settings, headless mode, GitHub Actions, and the Agent SDK.

**MCP** (`modelcontextprotocol.io`) — spec, concepts (tools/resources/prompts/transports), SDK docs, plus the `modelcontextprotocol` org's SDK repos (Python, TypeScript, Go, C#, Java, PHP, Rust, etc.).

**GitHub (`anthropics`)** — claude-cookbooks, courses, prompt-eng-interactive-tutorial, skills, claude-code, claude-plugins-official, claude-agent-sdk-python, anthropic-quickstarts, and more, sorted by stars.

**Engineering blog / News / Academy** — the curated seeds, since these have no machine index.

One caveat worth knowing before you pull: the engineering-blog seed list is the one part that isn't auto-discovered, so if you want every post (the "think" tool, multi-agent research, contextual retrieval, code-execution-with-MCP, the postmortem, etc.) you'd add their URLs to `SEED_LINKS` — there's no clean feed to enumerate them the way `llms.txt` does for docs.

==========

Correct — and it's actually a better approach than my script's GitHub step for the repos, for a reason worth separating out.

There are two different "hitting GitHub" operations in play:

The rate-limited one is the **REST API** call my script makes to *discover* what repos exist in the org (`api.github.com/orgs/anthropics/repos`). That's the 60/hr unauthenticated limit, and it's what failed in my sandbox — but only because the shared cloud IP had already burned its quota. On your own machine that enumeration is just ~2–4 calls total, so it'd succeed fine. You only need it at all if you *don't already know* which repos you want.

`git clone` is a **completely different channel** (the git protocol over codeload.github.com), and it does *not* count against that REST 60/hr limit. So for a known, small set of repos, you skip the rate-limited endpoint entirely. Clone once, then everything is local; `git pull` later to refresh. That's strictly better than fetching when you want the actual *content* (recipes, course notebooks, skills) rather than just a list of URLs.

A ready-to-run clone set for the content-rich official repos:

```bash
mkdir -p anthropic-collection && cd anthropic-collection
for repo in \
  anthropics/claude-cookbooks \
  anthropics/courses \
  anthropics/prompt-eng-interactive-tutorial \
  anthropics/skills \
  anthropics/anthropic-quickstarts \
  anthropics/claude-plugins-official \
  modelcontextprotocol/modelcontextprotocol ; do
    git clone --depth 1 "https://github.com/$repo.git"
done
```

`--depth 1` grabs just the latest snapshot (faster, less disk; drop it if you want full history). Update later with `git -C <repo> pull`.

The one thing cloning *won't* cover: the actual documentation pages on `platform.claude.com` and `code.claude.com` aren't published as an official public git repo — those live only as rendered docs. So your collection ends up hybrid: **clone** the repos above for cookbooks/courses/skills/quickstarts, and **fetch** the doc pages via the `llms.txt` route from the earlier script for the Platform and Claude Code reference material. (The MCP docs are the exception — cloning `modelcontextprotocol/modelcontextprotocol` gives you their Markdown source directly, so you don't need to fetch those.)

So your plan is sound: clone the handful of repos, and reserve fetching for just the docs that don't live in a repo.
