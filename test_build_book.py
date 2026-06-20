"""Tests for build_book.py — the ebook assembler.

Pure functions only; no filesystem. Run:
    python3 -m unittest test_build_book -v
"""

import unittest

from build_book import (
    assemble,
    demote_headings,
    fix_nested_code_fences,
    min_heading_level,
    normalize_source,
    parse_manifest,
    preprocess_mdx,
    rewrite_image_paths,
    strip_jsx,
    strip_standalone_html_tags,
    strip_yaml_frontmatter,
)


class ParseManifestTest(unittest.TestCase):
    def test_parses_parts_sources_and_authored_includes(self):
        text = (
            "# a comment line\n"
            "\n"
            "PART: I — Foundations\n"
            "~ frontmatter/preface.md\n"
            "docs/get-started.md\n"
            "PART: II — Prompting\n"
            "courses/intro.md\n"
        )
        entries = parse_manifest(text)
        self.assertEqual(entries[0], {"type": "part", "title": "I — Foundations"})
        self.assertEqual(
            entries[1],
            {"type": "source", "path": "frontmatter/preface.md", "authored": True},
        )
        self.assertEqual(
            entries[2],
            {"type": "source", "path": "docs/get-started.md", "authored": False},
        )
        self.assertEqual(entries[3], {"type": "part", "title": "II — Prompting"})
        self.assertEqual(entries[4]["path"], "courses/intro.md")

    def test_ignores_comments_and_blank_lines(self):
        self.assertEqual(parse_manifest("# x\n\n   \n# y\n"), [])


class MinHeadingLevelTest(unittest.TestCase):
    def test_returns_shallowest_level(self):
        self.assertEqual(min_heading_level("## Sub\n# Top\n### Deep\n"), 1)

    def test_ignores_headings_inside_code_fences(self):
        md = "```\n# not a heading\n```\n## Real\n"
        self.assertEqual(min_heading_level(md), 2)

    def test_returns_none_when_no_headings(self):
        self.assertIsNone(min_heading_level("just text\nmore text\n"))


class DemoteHeadingsTest(unittest.TestCase):
    def test_shifts_atx_headings_down(self):
        self.assertEqual(demote_headings("# A\n## B\n", 1), "## A\n### B\n")

    def test_clamps_at_h6(self):
        self.assertEqual(demote_headings("##### E\n", 2), "###### E\n")

    def test_does_not_touch_headings_in_code_fence(self):
        md = "# Title\n```python\n# a comment\n```\n"
        self.assertEqual(
            demote_headings(md, 1), "## Title\n```python\n# a comment\n```\n"
        )

    def test_zero_shift_is_identity(self):
        self.assertEqual(demote_headings("# A\n", 0), "# A\n")


class RewriteImagePathsTest(unittest.TestCase):
    def test_relative_markdown_image_becomes_root_relative(self):
        md = "![cat](images/cat.png)\n"
        out = rewrite_image_paths(md, source_dir="repo/sub", root="repo")
        self.assertEqual(out, "![cat](sub/images/cat.png)\n")

    def test_leaves_http_images_alone(self):
        md = "![x](https://example.com/x.png)\n"
        self.assertEqual(rewrite_image_paths(md, "repo/sub", "repo"), md)

    def test_leaves_images_in_code_fence_alone(self):
        md = "```\n![x](images/x.png)\n```\n"
        self.assertEqual(rewrite_image_paths(md, "repo/sub", "repo"), md)


class NormalizeSourceTest(unittest.TestCase):
    def test_demotes_to_base_level_and_adds_attribution(self):
        md = "# Recipe\n\nbody\n\n## Step\n"
        out = normalize_source(md, rel_path="repo/recipe.md", base=2)
        lines = out.splitlines()
        self.assertEqual(lines[0], "## Recipe")  # H1 -> H2 chapter
        self.assertIn("*Source: repo/recipe.md*", out)
        self.assertIn("### Step", out)  # H2 -> H3
        # attribution sits directly under the chapter heading
        self.assertTrue(out.index("*Source:") < out.index("body"))

    def test_source_without_heading_gets_synthesized_title(self):
        out = normalize_source("plain text\n", rel_path="repo/notes.md", base=2)
        self.assertTrue(out.startswith("## "))
        self.assertIn("plain text", out)


class MdxTest(unittest.TestCase):
    def test_strip_yaml_frontmatter_returns_body_and_title(self):
        md = "---\ntitle: Architecture overview\ntype: docs\n---\n\nBody here\n"
        body, title = strip_yaml_frontmatter(md)
        self.assertEqual(title, "Architecture overview")
        self.assertEqual(body, "Body here\n")

    def test_strip_yaml_frontmatter_noop_without_frontmatter(self):
        self.assertEqual(strip_yaml_frontmatter("# T\n"), ("# T\n", None))

    def test_strip_jsx_removes_component_tags_keeps_text(self):
        out = strip_jsx("<Note>\nkeep this\n</Note>\n")
        self.assertIn("keep this", out)
        self.assertNotIn("<Note>", out)

    def test_strip_jsx_leaves_code_fences_untouched(self):
        md = "```\n<Note>x</Note>\n```\n"
        self.assertEqual(strip_jsx(md), md)

    def test_strip_jsx_drops_import_lines(self):
        self.assertNotIn("import", strip_jsx("import X from 'y'\ntext\n"))

    def test_preprocess_mdx_prepends_title_and_cleans(self):
        md = "---\ntitle: Concepts\n---\n\n<Note>hi</Note>\n\nbody\n"
        out = preprocess_mdx(md)
        self.assertTrue(out.startswith("# Concepts"))
        self.assertIn("body", out)
        self.assertNotIn("<Note>", out)
        self.assertNotIn("---", out)

    def test_strip_standalone_html_tags_removes_wrapper_lines(self):
        md = (
            '<section title="X">\n'
            "```bash\n# a comment\n```\n"
            "</section>\n"
            "keep <Note>inline</Note> text\n"
        )
        out = strip_standalone_html_tags(md)
        self.assertNotIn("<section", out)
        self.assertNotIn("</section>", out)
        self.assertIn("# a comment", out)  # code fence content untouched
        self.assertIn("keep <Note>inline</Note> text", out)  # inline tag kept

    def test_strip_standalone_html_tags_keeps_tags_in_code(self):
        md = "```\n<section title='x'>\n```\n"
        self.assertEqual(strip_standalone_html_tags(md), md)


class FixNestedCodeFencesTest(unittest.TestCase):
    def test_block_with_inner_fence_is_rewrapped_with_longer_fence(self):
        # A notebook code cell whose string contains a ```html ... ``` example:
        # the inner bare ``` must not close the outer block.
        md = (
            "```python\n"
            'PROMPT = """\n'
            "```html\n"
            "<div>x</div>\n"
            "```\n"
            '"""\n'
            "# Generate with prompt\n"
            "run()\n"
            "```\n"
        )
        out = fix_nested_code_fences(md)
        self.assertIn("````python", out)  # outer bumped to 4 backticks
        self.assertIn("```html", out)  # inner fence preserved
        # The comment stays inside the (now correctly closed) code block:
        import subprocess

        headers = subprocess.run(
            ["pandoc", "-f", "gfm", "-t", "native"],
            input=out,
            capture_output=True,
            text=True,
        ).stdout.count("Header ")
        self.assertEqual(headers, 0)

    def test_simple_block_without_nesting_is_unchanged(self):
        md = "```python\nx = 1\n```\n"
        self.assertEqual(fix_nested_code_fences(md), md)

    def test_prose_between_blocks_is_preserved(self):
        md = "```\na\n```\ntext\n```\nb\n```\n"
        self.assertEqual(fix_nested_code_fences(md), md)


class AssembleTest(unittest.TestCase):
    def test_builds_parts_with_demoted_sources(self):
        entries = [
            {"type": "part", "title": "I — Foundations"},
            {"type": "source", "path": "a.md", "authored": False},
        ]
        fake_files = {"a.md": "# Alpha\n\nhello\n"}
        book = assemble(entries, read_text=lambda p: fake_files[p], root=".")
        self.assertIn("# I — Foundations", book)
        self.assertIn("## Alpha", book)
        self.assertIn("hello", book)
        # Part heading appears before the source chapter
        self.assertTrue(book.index("# I — Foundations") < book.index("## Alpha"))

    def test_mdx_source_is_cleaned_then_demoted(self):
        entries = [
            {"type": "part", "title": "VI — MCP"},
            {"type": "source", "path": "mcp/arch.mdx", "authored": False},
        ]
        raw = "---\ntitle: Architecture\n---\n\n<Note>note</Note>\n\nMCP body\n"
        book = assemble(entries, read_text=lambda p: raw, root=".")
        self.assertIn("## Architecture", book)
        self.assertIn("MCP body", book)
        self.assertNotIn("<Note>", book)

    def test_fetched_platform_doc_is_jsx_cleaned(self):
        # platform.claude.com / code.claude.com pages are MDX-flavored: a
        # <CodeGroup> with no blank line after it starts an HTML block that
        # swallows the following ``` fence, leaking code comments as headings.
        entries = [
            {"type": "part", "title": "III"},
            {
                "type": "source",
                "path": "docs/platform/build-with-claude/caching.md",
                "authored": False,
            },
        ]
        raw = "# Caching\n\n<CodeGroup>\n```bash\n# a comment\nprintf hi\n```\n</CodeGroup>\n"
        book = assemble(entries, read_text=lambda p: raw, root=".")
        self.assertNotIn("<CodeGroup>", book)
        self.assertIn("## Caching", book)
        self.assertIn("# a comment", book)  # comment kept inside the code block

    def test_authored_include_is_not_demoted_or_attributed(self):
        entries = [
            {"type": "part", "title": "I"},
            {"type": "source", "path": "preface.md", "authored": True},
        ]
        book = assemble(entries, read_text=lambda p: "## Welcome\n\nintro\n", root=".")
        self.assertIn("## Welcome", book)
        self.assertNotIn("*Source:", book)


if __name__ == "__main__":
    unittest.main()
