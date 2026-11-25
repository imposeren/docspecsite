import re

from docspecsite.markdown import HtmlRenderer, MarkdownText, Marker, RenderedLink

_SECTIONS = "Summary.\n\n" + "".join(f"## S{i}\n\ntext\n\n" for i in range(1, 5))


def _make_identity_link(href: str) -> RenderedLink:
    return RenderedLink(href)


def test_render_rewrites_links() -> None:
    seen: list[str] = []

    def make_link(target: str) -> RenderedLink:
        seen.append(target)
        return RenderedLink("b.html#x" if target == "b.md#x" else target)

    html = HtmlRenderer(make_link).render("[a](b.md#x) [w](https://e.org)")
    assert '<a href="b.html#x">a</a>' in html
    assert '<a href="https://e.org">w</a>' in html
    assert seen == ["b.md#x", "https://e.org"]


def test_render_plain_text_and_markers() -> None:
    renderer = HtmlRenderer(lambda _t: RenderedLink(None, (Marker("code-gone", "no longer exists"),)))
    html = renderer.render("[f](code:m.f)")
    assert 'f<span class="marker code-gone">no longer exists</span>' in html
    assert "<a" not in html


def test_render_marker_text_is_escaped() -> None:
    html = HtmlRenderer(lambda _t: RenderedLink("x.html", (Marker("newer", "a<b"),))).render("[f](x.md)")
    assert '</a><span class="marker newer">a&lt;b</span>' in html


def test_render_mermaid_fence() -> None:
    renderer = HtmlRenderer(_make_identity_link)
    assert '<pre class="mermaid">A--&gt;B&lt;C\n</pre>' in renderer.render("```mermaid\nA-->B<C\n```")
    assert '<pre><code class="language-python">' in renderer.render("```python\nx = 1\n```")


def test_render_heading_ids_match_anchors() -> None:
    text = (
        "# No delete, no rename\n\n## The `code:` field\n\n## Example\n\n## Example\n\n"
        "## Every directory has an `index.md`\n"
    )
    ids = set(re.findall(r'<h\d id="([^"]+)"', HtmlRenderer(_make_identity_link).render(text)))
    assert ids == MarkdownText(text).collect_heading_anchors()
    assert len(ids) == 5


def test_render_reference_links_and_images() -> None:
    seen: list[str] = []

    def make_link(target: str) -> RenderedLink:
        seen.append(target)
        return RenderedLink("out/" + target)

    html = HtmlRenderer(make_link).render("[x][r]\n\n![i](p.png)\n\n[r]: a.md\n")
    assert seen == ["a.md", "p.png"]
    assert '<a href="out/a.md">x</a>' in html
    assert 'src="out/p.png"' in html


def test_render_requotes_spaces() -> None:
    html = HtmlRenderer(lambda t: RenderedLink(t.replace(".md", ".html"))).render("[a](my%20doc.md)")
    assert 'href="my%20doc.html"' in html


def test_render_keeps_reserved_characters() -> None:
    html = HtmlRenderer(_make_identity_link).render("[x](https://e.org/a+b@c?q=1,2;x!$'()*)")
    assert 'href="https://e.org/a+b@c?q=1,2;x!$' + "'()*" + '"' in html


def test_render_keeps_encoded_reserved_characters_in_unchanged_links() -> None:
    seen: list[str] = []

    def make_link(target: str) -> RenderedLink:
        seen.append(target)
        return RenderedLink(target)

    text = "[a](https://e.org/s?q=a%26b%3Dc) [b](https://e.org/100%25) [c](https://e.org/a%2Fb) ![i](https://e.org/x%3Fy.png)"
    html = HtmlRenderer(make_link).render(text)
    assert 'href="https://e.org/s?q=a%26b%3Dc"' in html
    assert 'href="https://e.org/100%25"' in html
    assert 'href="https://e.org/a%2Fb"' in html
    assert 'src="https://e.org/x%3Fy.png"' in html
    assert seen == ["https://e.org/s?q=a&b=c", "https://e.org/100%", "https://e.org/a/b", "https://e.org/x?y.png"]


def _extract_toc(html: str) -> str | None:
    found = re.search(r'<nav class="toc">.*?</nav>', html, re.DOTALL)
    return found.group(0) if found else None


def test_toc_threshold() -> None:
    four = _SECTIONS
    five = four + "## S5\n"
    five_renderer = HtmlRenderer(_make_identity_link, toc_min_headings=5)
    assert _extract_toc(five_renderer.render(four)) is None
    assert five_renderer.render(four) == HtmlRenderer(_make_identity_link).render(four)
    assert _extract_toc(five_renderer.render(five)) is not None
    assert _extract_toc(HtmlRenderer(_make_identity_link, toc_min_headings=4).render(four)) is not None
    assert _extract_toc(HtmlRenderer(_make_identity_link, toc_min_headings=0).render(five)) is None
    assert _extract_toc(HtmlRenderer(_make_identity_link).render(five)) is None


def test_toc_markup_and_position() -> None:
    text = (
        "# Title\n\nSummary.\n\n## One *em* `code`\n\n### Sub A\n\n### Sub & B\n\n## Two\n\n## Two\n\n"
        "```\n## Not a heading\n```\n\n## Four\n\n## Three\n\n### Deep\n"
    )
    html = HtmlRenderer(_make_identity_link, toc_min_headings=5).render(text)
    toc = _extract_toc(html)
    assert toc == (
        '<nav class="toc"><h2 class="toc-title">Contents</h2><ol>'
        '<li><a href="#one-em-code">One em code</a><ol>'
        '<li><a href="#sub-a">Sub A</a></li><li><a href="#sub--b">Sub &amp; B</a></li></ol></li>'
        '<li><a href="#two">Two</a></li><li><a href="#two-1">Two</a></li>'
        '<li><a href="#four">Four</a></li>'
        '<li><a href="#three">Three</a><ol><li><a href="#deep">Deep</a></li></ol></li></ol></nav>'
    )
    assert html.index("Summary.") < html.index(toc) < html.index("<h2 id=")
    assert html.count("<h2") == 6
    ids = set(re.findall(r'<h\d id="([^"]+)"', html))
    assert {m for m in re.findall(r'href="#([^"]+)"', toc)} <= ids
    assert 'id="contents"' not in html
