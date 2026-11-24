import re
from dataclasses import replace

from docspecsite.config import ProjectConfig
from docspecsite.index_pages import IndexRenderer
from docspecsite.indexes import IndexEntry, IndexGroup, SiteIndex
from docspecsite.pages import Page
from docspecsite.vocabulary import Vocabulary

_NO_CONFIG = ProjectConfig((), "", {})
_NO_VOCABULARY = Vocabulary(frozenset(), ())


def _make_entry(path: str, **front_matter: object) -> IndexEntry:
    base: dict[str, object] = {"title": path, "summary": "S", "status": "specified", "layer": "meta"}
    return IndexEntry.from_front_matter(path, {**base, **front_matter})


def _build_index_pages(
    entries: list[IndexEntry],
    code_entries: list[IndexEntry],
    milestones: tuple[str, ...],
    *,
    site_title: str,
    config: ProjectConfig = _NO_CONFIG,
) -> list[Page]:
    vocabulary = Vocabulary(frozenset(), milestones)
    makers = IndexRenderer(SiteIndex(entries, code_entries, config, site_title, vocabulary)).make_page_makers()
    return [make() for make in makers.values()]


def test_tag_and_component_htmls() -> None:
    entries = [
        _make_entry("b.md", tags=["x"], components=["storage/files"]),
        _make_entry("a.md", tags=["x"]),
    ]
    code = [replace(_make_entry("core", components=["core"]), is_code_module=True)]
    pages = {p.url: p for p in _build_index_pages(entries, code, (), site_title="Docs")}
    tag = pages["tags/x.html"].body_html
    assert tag.index('href="../a.html"') < tag.index('href="../b.html"')
    assert 'href="../../b.html"' in pages["components/storage/files.html"].body_html
    assert 'href="../reference/code/core.html"' in pages["components/core.html"].body_html
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
    code = [replace(_make_entry("core", components=["core"]), is_code_module=True)]
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


def test_status_board_groups_by_status_milestone_and_priority() -> None:
    a = _make_entry("a.md", status=["implemented", "specified"], milestone="foundation", priority="must")
    b = _make_entry("b.md", milestone="foundation", priority="should")
    c = _make_entry("c.md", status="not-a-status")
    vocabulary = Vocabulary(frozenset(), ("foundation",))
    groups = SiteIndex([a, b, c], [], _NO_CONFIG, "Docs", vocabulary).group_status_board()
    assert groups == [
        IndexGroup(
            "specified",
            (),
            (IndexGroup("foundation", (), (IndexGroup("must", (a,)), IndexGroup("should", (b,)))),),
        ),
        IndexGroup("implemented", (), (IndexGroup("foundation", (), (IndexGroup("must", (a,)),)),)),
    ]


def test_group_by_tag_lists_each_doc_under_each_usable_tag() -> None:
    a = _make_entry("a.md", tags=["x", "y"])
    b = _make_entry("b.md", tags=["x", "bad/tag"])
    code = [replace(_make_entry("core", tags=["x"]), is_code_module=True)]
    by_tag = SiteIndex([a, b], code, _NO_CONFIG, "Docs", _NO_VOCABULARY).group_by_tag()
    assert by_tag == {"x": [a, b], "y": [a]}


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


def test_status_board_lists_doc_under_each_status() -> None:
    entries = [_make_entry("a.md", status=["implemented", "changed"], milestone="later", priority="should")]
    page = next(p for p in _build_index_pages(entries, [], ("later",), site_title="Docs") if p.url == "status.html")
    headings = re.findall(r"<h[234]>(.*?)</h[234]>", page.body_html)
    assert headings == ["changed", "later", "should", "implemented", "later", "should"]
    assert page.body_html.count('href="a.html"') == 2
    assert 'status-implemented">implemented</span> <span class="status status-changed">changed</span>' in page.body_html


def test_entries_with_unusable_status() -> None:
    entries = [_make_entry("a.md", status=5, tags=["x"])]
    page = next(p for p in _build_index_pages(entries, [], (), site_title="D") if p.url == "tags/x.html")
    assert 'class="status' not in page.body_html


def test_status_board_unknown_priorities_after_known() -> None:
    entries = [
        _make_entry("a.md", priority="high"),
        _make_entry("b.md", priority="Must"),
        _make_entry("c.md"),
        _make_entry("d.md", priority="could"),
        _make_entry("e.md", priority="should"),
        _make_entry("f.md", priority="must"),
    ]
    page = next(p for p in _build_index_pages(entries, [], (), site_title="Docs") if p.url == "status.html")
    assert re.findall(r"<h4>(.*?)</h4>", page.body_html) == ["must", "should", "could", "Must", "high", "none"]
    for path in ("a.html", "b.html", "c.html", "d.html", "e.html", "f.html"):
        assert page.body_html.count(f'href="{path}"') == 1, path


def test_status_board_milestone_order() -> None:
    entries = [
        _make_entry("a.md"),
        _make_entry("b.md", milestone="zeta"),
        _make_entry("c.md", milestone="second"),
        _make_entry("d.md", milestone="Alpha"),
        _make_entry("e.md", milestone="first"),
    ]
    page = next(
        p for p in _build_index_pages(entries, [], ("first", "second"), site_title="Docs") if p.url == "status.html"
    )
    assert re.findall(r"<h3>(.*?)</h3>", page.body_html) == ["first", "second", "Alpha", "zeta", "no milestone"]


def _make_scenario_entry(**front_matter: object) -> IndexEntry:
    fields = {
        "title": "Import — scenarios",
        "layer": "scenarios",
        "components": ["checks"],
        "status": "implemented",
        "milestone": "later",
        "priority": "must",
        **front_matter,
    }
    return _make_entry("scenarios/import.md", **fields)


def test_the_machine_listing_leaves_out_the_status_of_a_doc_without_one() -> None:
    llms = SiteIndex([_make_scenario_entry()], [], _NO_CONFIG, "Docs", _NO_VOCABULARY).make_llms_txt("All.")
    assert (
        "- [Import — scenarios](scenarios/import.html): S (components: checks; source: docs/scenarios/import.md)\n"
        in llms
    )
    assert "status:" not in llms


def test_a_doc_without_a_status_is_not_on_the_status_board() -> None:
    pages = {p.url: p for p in _build_index_pages([_make_scenario_entry()], [], ("later",), site_title="Docs")}
    assert "scenarios/import.html" not in pages["status.html"].body_html
    component_html = pages["components/checks.html"].body_html
    assert "import.html" in component_html
    assert 'class="status' not in component_html


def test_a_draft_scenario_doc_is_on_the_status_board() -> None:
    entries = [_make_scenario_entry(status=["draft", "implemented"])]
    page = next(p for p in _build_index_pages(entries, [], ("later",), site_title="Docs") if p.url == "status.html")
    assert re.findall(r"<h[234]>(.*?)</h[234]>", page.body_html) == ["draft", "no milestone", "none"]
    assert 'href="scenarios/import.html"' in page.body_html


def test_llms_txt_escapes_url_and_title() -> None:
    entry = IndexEntry.from_front_matter(
        "meta/a (b)é.md",
        {"title": "T [x] \\ y", "summary": "S", "status": "specified", "layer": "meta"},
    )
    text = SiteIndex([entry], [], _NO_CONFIG, "Docs", _NO_VOCABULARY).make_llms_txt("All.")
    assert "- [T \\[x\\] \\\\ y](meta/a%20%28b%29%C3%A9.html): S (" in text
    assert "source: docs/meta/a (b)é.md)" in text


def test_llms_txt() -> None:
    entries = [
        _make_entry("meta/a.md", title="A", summary="Sum.\n  More <b>", components=["core"], layer="meta"),
        _make_entry("index.md", title="Home", layer="root"),
        _make_entry("meta/b.md", title="B", status=["implemented", "specified"], layer="meta"),
    ]
    assert SiteIndex(entries, [], _NO_CONFIG, "Docs", _NO_VOCABULARY).make_llms_txt("All.") == (
        "# Docs\n\n> All.\n\n## root\n\n"
        "- [Home](index.html): S (status: specified; components: none; source: docs/index.md)\n\n"
        "## meta\n\n"
        "- [A](meta/a.html): Sum. More <b> (status: specified; components: core; source: docs/meta/a.md)\n"
        "- [B](meta/b.html): S (status: implemented,specified; components: none; source: docs/meta/b.md)\n"
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
    llms = SiteIndex(entries, [], config, "Docs", _NO_VOCABULARY).make_llms_txt("All.")
    assert llms.index("BASE-0001") < llms.index("PYRF-0001") < llms.index("APP-0001")
