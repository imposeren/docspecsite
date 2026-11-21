import re
from dataclasses import replace

from conftest import extract_aside

from docspecsite.history import Version
from docspecsite.markdown import Marker
from docspecsite.pages import (
    OldBanner,
    Page,
    PageLink,
    PickerEntry,
    RedirectNotice,
    Templates,
    build_breadcrumb,
    load_static_files,
    make_picker_label,
)

_PAGE = Page("meta/a.html", "A", "specified", ("core",), ("x",), "<p>Body</p>")


def _render(page: Page) -> str:
    return Templates().render(page, "Docs")


def test_page_chrome() -> None:
    html = _render(replace(_PAGE, breadcrumb=(PageLink("Home", "index.html"),)))
    assert re.search(r'<nav class="breadcrumb">.*?href="\.\./index\.html"', html, re.S)
    assert '<span class="status status-specified">specified</span>' in html
    assert 'href="../components/core.html"' in html
    assert 'href="../tags/x.html"' in html
    assert '<link rel="stylesheet" href="../assets/docspecsite.css">' in html
    assert "<title>A — Docs</title>" in html
    assert "old-banner" not in html
    assert 'class="old"' not in html
    assert '="/' not in html
    assert "<p>Body</p>" in html


def test_render_page_link_without_url() -> None:
    html = _render(replace(_PAGE, breadcrumb=(PageLink("Home", None),), described_in=(PageLink("meta/d.md", None),)))
    breadcrumb = html.split('<nav class="breadcrumb">', 1)[1].split("</nav>", 1)[0]
    assert "Home" in breadcrumb
    assert "href" not in breadcrumb
    described = extract_aside(html, "described-in")
    assert "meta/d.md" in described
    assert "href" not in described


def test_old_version_banner() -> None:
    page = replace(_PAGE, url="meta/a/v/abc123def456.html", old=OldBanner("2026-11-01", "abc123def456", "meta/a.html"))
    html = _render(page)
    assert "⚠ OLD VERSION — 2026-11-01, abc123def456 — this is NOT the current spec." in html
    assert '<a href="../../a.html">→ Latest version</a>' in html
    assert "<title>[OLD] A — Docs</title>" in html
    assert '<body class="old">' in html


def test_picker() -> None:
    picker = (
        PickerEntry("2026-11-02 · bbb · second", "meta/a.html", current=False),
        PickerEntry("2026-11-01 · aaa · first", "meta/a/v/aaa.html", current=True),
    )
    html = _render(replace(_PAGE, picker=picker))
    assert '<select class="version-picker"' in html
    options = re.findall(r"<option[^>]*>", html)
    assert len(options) == 2
    assert "selected" not in options[0]
    assert "selected" in options[1]
    assert 'value="a.html"' in options[0]
    assert 'value="a/v/aaa.html"' in options[1]
    assert '<script src="../assets/docspecsite.js"></script>' in html
    assert "diff vs previous" not in html

    with_diff = _render(replace(_PAGE, picker=picker, diff_url="meta/a/v/aaa.diff.html"))
    assert '<a class="diff-link" href="a/v/aaa.diff.html">diff vs previous</a>' in with_diff


def test_no_picker_without_entries() -> None:
    html = _render(_PAGE)
    assert "version-picker" not in html


def test_redirect_notice() -> None:
    notice = RedirectNotice("Moved", (PageLink("B", "meta/b.html"),), "Because.")
    html = _render(replace(_PAGE, redirect=notice))
    assert '<div class="redirect-notice">' in html
    assert "<strong>Moved</strong>" in html
    assert 'href="b.html"' in html
    assert '<p class="reason">Because.</p>' in html
    assert "http-equiv" not in html


def test_panels() -> None:
    page = replace(
        _PAGE,
        children=(PageLink("Child", "meta/a/c.html", "Child summary."),),
        related=(PageLink("Rel", "meta/r.html", markers=(Marker("moved", "→ moved"),)),),
        backlinks=(PageLink("Back", "x/y.html"),),
    )
    html = _render(page)
    assert 'href="a/c.html"' in extract_aside(html, "children")
    assert "Child summary." in extract_aside(html, "children")
    assert "<h2>Submodules</h2>" in html
    assert "Contents" not in html
    assert "<h2>Packages</h2>" in _render(replace(page, children_heading="Packages"))
    related = extract_aside(html, "related")
    assert 'href="r.html"' in related
    assert '<span class="marker moved">→ moved</span>' in related
    assert 'href="../x/y.html"' in extract_aside(html, "backlinks")
    assert "described-in" not in html

    code = _render(replace(_PAGE, url="reference/code/m.html", described_in=(PageLink("Doc", "meta/a.html"),)))
    assert 'href="../../meta/a.html"' in extract_aside(code, "described-in")
    for cls in ("children", "related", "backlinks"):
        assert f'<aside class="{cls}"' not in code


def test_escaping() -> None:
    nasty = 'a <b> & "c"'
    escaped = "a &lt;b&gt; &amp; &#34;c&#34;"
    page = replace(
        _PAGE,
        title=nasty,
        body_html="<p><em>raw</em></p>",
        picker=(PickerEntry(f"2026-11-01 · aaa · {nasty}", "meta/a.html", current=True),),
        redirect=RedirectNotice("Moved", (PageLink(nasty, "meta/b.html"),), nasty),
        related=(PageLink(nasty, "meta/r.html", nasty),),
        breadcrumb=(PageLink(nasty, "index.html"),),
        old=OldBanner(nasty, nasty, "meta/a.html"),
    )
    html = Templates().render(page, nasty)
    assert f"<title>[OLD] {escaped} — {escaped}</title>" in html
    assert f"<h1>{escaped}</h1>" in html
    assert "<p><em>raw</em></p>" in html
    assert f'<p class="reason">{escaped}</p>' in html
    assert f"2026-11-01 · aaa · {escaped}" in html
    assert "<b>" not in html
    assert '"c"' not in html


def test_mermaid_scripts() -> None:
    html = _render(replace(_PAGE, mermaid=True))
    assert '<script src="../assets/mermaid.min.js"></script>' in html
    assert 'mermaid.initialize({ startOnLoad: true, securityLevel: "strict" })' in html
    plain = _render(_PAGE)
    assert "mermaid.min.js" not in plain
    assert "mermaid.initialize" not in plain


def test_breadcrumb() -> None:
    titles = {"index.md": "Home", "meta/index.md": "Meta", "meta/a.md": "A"}
    assert build_breadcrumb("meta/a.md", titles) == (
        PageLink("Home", "index.html"),
        PageLink("Meta", "meta/index.html"),
    )
    assert build_breadcrumb("meta/index.md", titles) == (PageLink("Home", "index.html"),)
    assert build_breadcrumb("index.md", titles) == ()


def test_picker_label() -> None:
    version = Version("meta/a.md", "abc123def456", "abc123def456" + "0" * 28, 3, "2026-11-01", "add a", "f" * 40)
    assert make_picker_label(version) == "2026-11-01 · abc123def456 · add a"
    worktree = Version("meta/a.md", Version.WORKTREE, None, -1, "", "working copy (uncommitted)", "f" * 40)
    assert make_picker_label(worktree) == "working copy (uncommitted)"


def test_static_files() -> None:
    files = load_static_files()
    assert set(files) == {"assets/docspecsite.css", "assets/docspecsite.js"}
    assert b".old-banner" in files["assets/docspecsite.css"]
    assert b"location.href" in files["assets/docspecsite.js"]


def test_index_links_only_to_produced_indexes() -> None:
    html = Templates().render(_PAGE, "Docs", indexes={"tags/x.html"})
    assert '<a class="tag" href="../tags/x.html">#x</a>' in html
    assert '<span class="component">core</span>' in html
    assert "components/core.html" not in html
    assert "status.html" not in html
    assert "status.html" in Templates().render(_PAGE, "Docs", indexes={"status.html"})
    linked = _render(_PAGE)
    assert 'href="../components/core.html"' in linked


def test_index_links_are_encoded() -> None:
    html = _render(replace(_PAGE, tags=("a b",), components=("p q/r",)))
    assert 'href="../tags/a%20b.html"' in html
    assert 'href="../components/p%20q/r.html"' in html
    only = Templates().render(replace(_PAGE, tags=("a b",)), "Docs", indexes={"tags/a b.html"})
    assert '<a class="tag" href="../tags/a%20b.html">#a b</a>' in only


def test_body_h1_moves_to_title_position() -> None:
    plain = _render(_PAGE)
    assert plain.count("<h1") == 1
    assert plain.index("<h1>A</h1>") < plain.index('class="status')
    moved = _render(replace(_PAGE, body_html='<h1 id="t">T <code>x</code></h1>\n<p>Body</p>'))
    assert moved.count("<h1") == 1
    assert moved.index('<h1 id="t">T <code>x</code></h1>') < moved.index('class="status')
    article = moved.split('<article class="body">', 1)[1]
    assert "<h1" not in article
    assert "<p>Body</p>" in article


def test_status_link_on_every_page() -> None:
    assert re.search(r'<nav class="site">.*?<a href="\.\./status\.html">Status</a>', _render(_PAGE), re.S)
    root = _render(replace(_PAGE, url="index.html"))
    assert '<a href="status.html">Status</a>' in root
