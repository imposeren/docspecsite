import re

from docspecsite.config import ProjectConfig
from docspecsite.indexes import IndexEntry, IndexRenderer
from docspecsite.pages import Page
from docspecsite.vocabulary import Vocabulary

_NO_CONFIG = ProjectConfig((), "", {})
_NO_VOCABULARY = Vocabulary(frozenset(), ())


def _make_entry(path: str, **front_matter: object) -> IndexEntry:
    base: dict[str, object] = {"title": path, "summary": "S", "status": "specified", "layer": "meta"}
    return IndexEntry.from_front_matter(path, path.replace(".md", ".html"), {**base, **front_matter})


def _build_index_pages(
    entries: list[IndexEntry],
    code_entries: list[IndexEntry],
    milestones: tuple[str, ...],
    *,
    site_title: str,
    config: ProjectConfig = _NO_CONFIG,
) -> list[Page]:
    vocabulary = Vocabulary(frozenset(), milestones)
    makers = IndexRenderer(entries, code_entries, config, site_title, vocabulary).make_page_makers()
    return [make() for make in makers.values()]


def test_tag_and_component_pages() -> None:
    entries = [
        _make_entry("b.md", tags=["x"], components=["storage/files"]),
        _make_entry("a.md", tags=["x"]),
    ]
    code = [_make_entry("reference/code/core.md", components=["core"])]
    pages = {p.url: p for p in _build_index_pages(entries, code, (), site_title="Docs")}
    tag = pages["tags/x.html"].body_html
    assert tag.index('href="../a.html"') < tag.index('href="../b.html"')
    assert 'href="../../b.html"' in pages["components/storage/files.html"].body_html
    assert "core.html" in pages["components/core.html"].body_html
    assert "reference/code" not in pages["status.html"].body_html
    assert "reference/code" not in pages["tags/x.html"].body_html


def test_index_pages_decoded_file_names_and_link_home() -> None:
    entries = [_make_entry("a.md", tags=["a b", "x/y", "n\0ul"], components=["p q/r"])]
    pages = {p.url: p for p in _build_index_pages(entries, [], (), site_title="My Docs")}
    assert set(pages) == {"tags/a b.html", "components/p q/r.html", "status.html"}
    for page in pages.values():
        assert [(link.title, link.url) for link in page.breadcrumb] == [("My Docs", "index.html")]
    assert 'href="../../a.html"' in pages["components/p q/r.html"].body_html


def test_status_board_order() -> None:
    entries = [
        _make_entry("a.md", status="implemented", milestone="foundation", priority="must"),
        _make_entry("b.md", milestone="first-release", priority="should"),
        _make_entry("c.md", milestone="foundation", priority="could"),
        _make_entry("d.md"),
    ]
    code = [_make_entry("reference/code/core.md", components=["core"])]
    page = next(
        p
        for p in _build_index_pages(entries, code, ("foundation", "first-release"), site_title="Docs")
        if p.url == "status.html"
    )
    headings = re.findall(r"<h[234]>(.*?)</h[234]>", page.body_html)
    assert headings == [
        "specified", "foundation", "could", "first-release", "should", "no milestone", "none",
        "implemented", "foundation", "must",
    ]  # fmt: skip
    assert "core" not in page.body_html


def test_status_board_unknown_milestones() -> None:
    entries = [
        _make_entry("a.md", milestone="foundation"),
        _make_entry("b.md", milestone="later"),
        _make_entry("c.md", milestone="earlier"),
        _make_entry("d.md"),
    ]
    page = next(
        p for p in _build_index_pages(entries, [], ("foundation",), site_title="Docs") if p.url == "status.html"
    )
    headings = re.findall(r"<h3>(.*?)</h3>", page.body_html)
    assert headings == ["foundation", "earlier", "later", "no milestone"]


def test_status_board_null_and_literal_no_milestone() -> None:
    entries = [
        _make_entry("a.md", milestone=None, priority=None),
        _make_entry("b.md", milestone="no milestone"),
        _make_entry("c.md"),
    ]
    page = next(p for p in _build_index_pages(entries, [], (), site_title="Docs") if p.url == "status.html")
    assert re.findall(r"<h3>(.*?)</h3>", page.body_html) == ["no milestone"]
    assert re.findall(r"<h4>(.*?)</h4>", page.body_html) == ["none"]
    for path in ("a.html", "b.html", "c.html"):
        assert page.body_html.count(f'href="{path}"') == 1, path


def test_llms_txt() -> None:
    entries = [
        _make_entry("meta/a.md", title="A", summary="Sum.\n  More <b>", components=["core"], layer="meta"),
        _make_entry("index.md", title="Home", layer="root"),
    ]
    assert IndexRenderer(entries, [], _NO_CONFIG, "Docs", _NO_VOCABULARY).render_llms_txt("All.") == (
        "# Docs\n\n> All.\n\n## root\n\n"
        "- [Home](index.html): S (status: specified; components: none; source: docs/index.md)\n\n"
        "## meta\n\n"
        "- [A](meta/a.html): Sum. More <b> (status: specified; components: core; source: docs/meta/a.md)\n"
    )


def test_listings_order_adrs_by_prefix() -> None:
    config = ProjectConfig((), "", {}, adr_prefix="APP", external_adr_prefixes=("BASE", "PYRF"))
    entries = [
        _make_entry("architecture/decisions/APP-0001-x.md", tags=["adr"], layer="architecture"),
        _make_entry("architecture/decisions/PYRF-0001-x.md", tags=["adr"], layer="architecture"),
        _make_entry("architecture/decisions/BASE-0001-x.md", tags=["adr"], layer="architecture"),
    ]
    pages = {p.url: p for p in _build_index_pages(entries, [], (), site_title="Docs", config=config)}
    tag = pages["tags/adr.html"].body_html
    assert tag.index("BASE-0001") < tag.index("PYRF-0001") < tag.index("APP-0001")
    llms = IndexRenderer(entries, [], config, "Docs", _NO_VOCABULARY).render_llms_txt("All.")
    assert llms.index("BASE-0001") < llms.index("PYRF-0001") < llms.index("APP-0001")
