import re

from docspecsite.markdown import Marker, RenderedLink, collect_heading_anchors, render_html

_SECTIONS = "Summary.\n\n" + "".join(f"## S{i}\n\ntext\n\n" for i in range(1, 5))


def _make_identity_link(href: str) -> RenderedLink:
    return RenderedLink(href)


def test_render_rewrites_links() -> None:
    seen: list[str] = []

    def make_link(target: str) -> RenderedLink:
        seen.append(target)
        return RenderedLink("b.html#x" if target == "b.md#x" else target)

    html = render_html("[a](b.md#x) [w](https://e.org)", make_link)
    assert '<a href="b.html#x">a</a>' in html
    assert '<a href="https://e.org">w</a>' in html
    assert seen == ["b.md#x", "https://e.org"]


def test_render_plain_text_and_markers() -> None:
    html = render_html("[f](code:m.f)", lambda _t: RenderedLink(None, (Marker("code-gone", "no longer exists"),)))
    assert 'f<span class="marker code-gone">no longer exists</span>' in html
    assert "<a" not in html


def test_render_marker_text_is_escaped() -> None:
    html = render_html("[f](x.md)", lambda _t: RenderedLink("x.html", (Marker("newer", "a<b"),)))
    assert '</a><span class="marker newer">a&lt;b</span>' in html


def test_render_mermaid_fence() -> None:
    assert '<pre class="mermaid">A--&gt;B&lt;C\n</pre>' in render_html("```mermaid\nA-->B<C\n```", _make_identity_link)
    assert '<pre><code class="language-python">' in render_html("```python\nx = 1\n```", _make_identity_link)


def test_render_heading_ids_match_anchors() -> None:
    text = (
        "# No delete, no rename\n\n## The `code:` field\n\n## Example\n\n## Example\n\n"
        "## Every directory has an `index.md`\n"
    )
    ids = set(re.findall(r'<h\d id="([^"]+)"', render_html(text, _make_identity_link)))
    assert ids == collect_heading_anchors(text)
    assert len(ids) == 5


def test_render_reference_links_and_images() -> None:
    seen: list[str] = []

    def make_link(target: str) -> RenderedLink:
        seen.append(target)
        return RenderedLink("out/" + target)

    html = render_html("[x][r]\n\n![i](p.png)\n\n[r]: a.md\n", make_link)
    assert seen == ["a.md", "p.png"]
    assert '<a href="out/a.md">x</a>' in html
    assert 'src="out/p.png"' in html


def test_render_requotes_spaces() -> None:
    html = render_html("[a](my%20doc.md)", lambda t: RenderedLink(t.replace(".md", ".html")))
    assert 'href="my%20doc.html"' in html


def test_render_keeps_reserved_characters() -> None:
    html = render_html("[x](https://e.org/a+b@c?q=1,2;x!$'()*)", _make_identity_link)
    assert 'href="https://e.org/a+b@c?q=1,2;x!$' + "'()*" + '"' in html


def test_render_keeps_encoded_reserved_characters_in_unchanged_links() -> None:
    seen: list[str] = []

    def make_link(target: str) -> RenderedLink:
        seen.append(target)
        return RenderedLink(target)

    text = "[a](https://e.org/s?q=a%26b%3Dc) [b](https://e.org/100%25) [c](https://e.org/a%2Fb) ![i](https://e.org/x%3Fy.png)"
    html = render_html(text, make_link)
    assert 'href="https://e.org/s?q=a%26b%3Dc"' in html
    assert 'href="https://e.org/100%25"' in html
    assert 'href="https://e.org/a%2Fb"' in html
    assert 'src="https://e.org/x%3Fy.png"' in html
    assert seen == ["https://e.org/s?q=a&b=c", "https://e.org/100%", "https://e.org/a/b", "https://e.org/x?y.png"]


def _extract_toc(html: str) -> str | None:
    found = re.search(r'<nav class="toc">.*?</nav>', html, re.S)
    return found.group(0) if found else None


def test_toc_threshold() -> None:
    four = _SECTIONS
    five = four + "## S5\n"
    assert _extract_toc(render_html(four, _make_identity_link, toc_min_headings=5)) is None
    assert render_html(four, _make_identity_link, toc_min_headings=5) == render_html(four, _make_identity_link)
    assert _extract_toc(render_html(five, _make_identity_link, toc_min_headings=5)) is not None
    assert _extract_toc(render_html(four, _make_identity_link, toc_min_headings=4)) is not None
    assert _extract_toc(render_html(five, _make_identity_link, toc_min_headings=0)) is None
    assert _extract_toc(render_html(five, _make_identity_link)) is None


def test_toc_markup_and_position() -> None:
    text = (
        "# Title\n\nSummary.\n\n## One *em* `code`\n\n### Sub A\n\n### Sub & B\n\n## Two\n\n## Two\n\n"
        "```\n## Not a heading\n```\n\n## Four\n\n## Three\n\n### Deep\n"
    )
    html = render_html(text, _make_identity_link, toc_min_headings=5)
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
