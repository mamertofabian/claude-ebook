"""Tests for fetch_docs.py pure helpers.

Run: python3 -m unittest test_fetch_docs -v
"""

import unittest

from fetch_docs import (
    clean_essay_markdown,
    extract_main_content,
    local_path_for,
    rewrite_doc_image_urls,
    select_doc_paths,
)


class RewriteDocImageUrlsTest(unittest.TestCase):
    def test_decodes_nextjs_image_proxy(self):
        md = (
            "![x](/_next/image?url=https%3A%2F%2Fcdn.example.com%2Fa.png&w=3840&q=75)\n"
        )
        out = rewrite_doc_image_urls(md, "https://www.anthropic.com")
        self.assertEqual(out, "![x](https://cdn.example.com/a.png)\n")

    def test_prepends_origin_to_site_relative(self):
        md = "![d](/docs/images/diagram.svg)\n"
        out = rewrite_doc_image_urls(md, "https://platform.claude.com")
        self.assertEqual(
            out, "![d](https://platform.claude.com/docs/images/diagram.svg)\n"
        )

    def test_proxy_with_site_relative_target_gets_origin(self):
        md = "![x](/_next/image?url=%2Fdocs%2Fimages%2Fa.png&w=640)\n"
        out = rewrite_doc_image_urls(md, "https://platform.claude.com")
        self.assertIn("https://platform.claude.com/docs/images/a.png", out)

    def test_leaves_absolute_and_relative_alone(self):
        md = "![a](https://cdn.x/a.png)\n![b](images/local.png)\n"
        self.assertEqual(rewrite_doc_image_urls(md, "https://platform.claude.com"), md)

    def test_rewrites_inline_img_tags(self):
        md = '<img src="/docs/images/x.png" alt="">\n'
        out = rewrite_doc_image_urls(md, "https://code.claude.com")
        self.assertIn('src="https://code.claude.com/docs/images/x.png"', out)

    def test_does_not_rewrite_inside_code_fence(self):
        md = "```\n![x](/docs/images/a.png)\n```\n"
        self.assertEqual(rewrite_doc_image_urls(md, "https://platform.claude.com"), md)

    def test_handles_multiline_alt_text(self):
        # pandoc emits images whose alt text spans lines; the ![ and ](url) end
        # up on different lines, so a per-line regex misses them.
        md = "![alt that wraps\nonto a second line\n](/_next/image?url=https%3A%2F%2Fcdn.x%2Fa.gif&w=10)\n"
        out = rewrite_doc_image_urls(md, "https://www.anthropic.com")
        self.assertIn("https://cdn.x/a.gif", out)
        self.assertNotIn("_next", out)


class SelectDocPathsTest(unittest.TestCase):
    def test_allow_prefix_includes_matching_paths(self):
        paths = ["build-with-claude/vision.md", "api/python/messages.md", "intro.md"]
        got = select_doc_paths(paths, allow=["build-with-claude/", "intro.md"], deny=[])
        self.assertEqual(got, ["build-with-claude/vision.md", "intro.md"])

    def test_deny_substring_excludes(self):
        paths = [
            "build-with-claude/vision.md",
            "build-with-claude/claude-in-bedrock.md",
        ]
        got = select_doc_paths(paths, allow=["build-with-claude/"], deny=["claude-in-"])
        self.assertEqual(got, ["build-with-claude/vision.md"])

    def test_explicit_list_selects_exact_paths_only(self):
        paths = ["overview.md", "glossary.md", "memory.md"]
        got = select_doc_paths(paths, explicit=["overview.md", "memory.md"])
        self.assertEqual(sorted(got), ["memory.md", "overview.md"])

    def test_explicit_missing_path_is_reported(self):
        # Asking for a page that the index does not contain must be surfaced,
        # not silently dropped (fail-loud philosophy).
        paths = ["overview.md"]
        with self.assertRaises(ValueError):
            select_doc_paths(paths, explicit=["overview.md", "does-not-exist.md"])


class LocalPathForTest(unittest.TestCase):
    def test_builds_namespaced_path(self):
        self.assertEqual(
            local_path_for("build-with-claude/vision.md", "platform", "docs"),
            "docs/platform/build-with-claude/vision.md",
        )


class ExtractMainContentTest(unittest.TestCase):
    def test_captures_only_main_content_div(self):
        html = (
            "<header><nav>menu</nav></header>"
            '<div id="main-content"><h1>Title</h1>'
            "<div>nested</div></div>"
            "<footer>links</footer>"
        )
        out = extract_main_content(html)
        self.assertIn("<h1>Title</h1>", out)
        self.assertIn("nested", out)
        self.assertNotIn("menu", out)
        self.assertNotIn("links", out)

    def test_returns_original_when_no_main_content(self):
        html = "<div><h1>x</h1></div>"
        self.assertEqual(extract_main_content(html), html)


class CleanEssayMarkdownTest(unittest.TestCase):
    def test_drops_standalone_html_tag_lines_and_cuts_to_first_heading(self):
        md = '<div class="x">\n</div>\n[nav](/x)\n# Real Title\n\nBody text.\n'
        out = clean_essay_markdown(md)
        self.assertTrue(out.lstrip().startswith("# Real Title"))
        self.assertIn("Body text.", out)
        self.assertNotIn('<div class="x">', out)

    def test_collapses_excess_blank_lines(self):
        md = "# T\n\n\n\nbody\n"
        self.assertEqual(clean_essay_markdown(md), "# T\n\nbody\n")

    def test_cuts_site_footer_nav(self):
        md = (
            "# T\n\nreal body\n\n"
            "## Get the developer newsletter\n\nsignup\n\n"
            "### Products\n- [x](/x)\n### Company\n- [y](/y)\n"
        )
        out = clean_essay_markdown(md)
        self.assertIn("real body", out)
        self.assertNotIn("developer newsletter", out)
        self.assertNotIn("Company", out)


if __name__ == "__main__":
    unittest.main()
