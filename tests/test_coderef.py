from dataclasses import replace
from pathlib import Path

import griffe
import pytest
from conftest import load_sample_code

from docspecsite.codeindex import CodeTarget
from docspecsite.coderef import (
    Codebase,
    CodeError,
    CodeReference,
    DocsLine,
    Package,
    split_docs_lines,
)
from docspecsite.config import ProjectConfig
from docspecsite.pages import Page, PageLink

SAMPLE_MODULE_PATH = "tools/sample/src/sample/mod.py"


def test_find_packages(code_tree: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    packages = Codebase.find_packages(code_tree, ProjectConfig.load(code_tree))
    assert packages == [Package("sample", code_tree / "tools/sample/src/sample", "tools/sample/src")]
    assert Codebase.find_packages(tmp_path_factory.mktemp("empty"), ProjectConfig.from_bytes(None)) == []


def test_index_targets(code_tree: Path) -> None:
    codebase = load_sample_code(code_tree)
    assert codebase.index.get("sample.mod") == CodeTarget("sample.mod", None)
    assert codebase.index.get("sample.mod.Thing.run") == CodeTarget("sample.mod", "sample.mod.Thing.run")
    assert codebase.index.get("sample.mod.LIMIT") is not None
    assert codebase.index.get("sample.mod.Alias") is not None
    assert codebase.index.get("sample.mod._helper") is None
    assert codebase.index.get("sample._private") is None
    assert codebase.index.get("sample.mod.Base") is None


def test_modules_listed(code_tree: Path) -> None:
    codebase = load_sample_code(code_tree)
    assert [m.path for m in codebase.modules] == ["sample", "sample.base", "sample.mod"]


def test_docs_lines(code_tree: Path) -> None:
    codebase = load_sample_code(code_tree)
    source = (code_tree / "tools/sample/src/sample/mod.py").read_text(encoding="utf-8").splitlines()
    line = source.index("Docs: meta/vocabulary.md") + 1
    assert codebase.collect_docs_lines() == [DocsLine("meta/vocabulary.md", "tools/sample/src/sample/mod.py", line)]


def test_split_docs_lines() -> None:
    assert split_docs_lines("Text.\n\nDocs: a.md\nDocs: b.md#x\n") == (["a.md", "b.md#x"], "Text.\n")
    assert split_docs_lines("See Docs: a.md inline") == ([], "See Docs: a.md inline")


def test_load_ignores_cwd_decoy(
    code_tree: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    decoy = tmp_path_factory.mktemp("cwd")
    (decoy / "sample").mkdir()
    (decoy / "sample" / "__init__.py").write_text('"""Decoy."""\n', encoding="utf-8")
    monkeypatch.chdir(decoy)
    codebase = load_sample_code(code_tree)
    assert [m.path for m in codebase.modules] == ["sample", "sample.base", "sample.mod"]
    assert codebase.modules[0].docstring is not None
    assert codebase.modules[0].docstring.value == "Sample package."


def _docs_lines_for(root: Path, source: str) -> list[DocsLine]:
    (root / "tools/sample/src/sample/mod.py").write_text(source, encoding="utf-8")
    return load_sample_code(root).collect_docs_lines()


def test_docs_line_one_line_docstring(code_tree: Path) -> None:
    assert _docs_lines_for(code_tree, '"""Docs: a.md"""\n') == [DocsLine("a.md", SAMPLE_MODULE_PATH, 1)]


def test_docs_line_closing_quotes_on_docs_line(code_tree: Path) -> None:
    source = '"""Title.\n\n    Docs: a.md"""\n'
    assert _docs_lines_for(code_tree, source) == [DocsLine("a.md", SAMPLE_MODULE_PATH, 3)]


def test_docs_lines_two_in_one_docstring(code_tree: Path) -> None:
    source = 'X = 1\n\n\ndef f() -> None:\n    """\n    Title.\n\n    Docs: a.md\n    Docs: b.md#x\n    """\n'
    assert _docs_lines_for(code_tree, source) == [
        DocsLine("a.md", SAMPLE_MODULE_PATH, 8),
        DocsLine("b.md#x", SAMPLE_MODULE_PATH, 9),
    ]


def _build_module_pages(
    codebase: Codebase, config: ProjectConfig, *, source_url: str, described_in: dict[str, list[PageLink]]
) -> list[Page]:
    """Return the page of each module of the codebase.

    Args:
        codebase: Loaded code whose modules get pages.
        config: Settings giving the modules' components.
        source_url: Repository web URL used in the source links, in place of the config's; empty means no source links.
        described_in: Docs that describe each module, by module path, shown on its page.
    """
    code_reference = CodeReference.for_commit(codebase, replace(config, source_url=source_url), "c0ffee")
    return [code_reference.build_page(module, described_in.get(module.path, [])) for module in codebase.modules]


def _build_pages(root: Path, described_in: dict[str, list[PageLink]] | None = None) -> dict[str, Page]:
    config = ProjectConfig.load(root)
    codebase = Codebase.load(root, config)
    pages = _build_module_pages(codebase, config, source_url="https://github.com/o/r", described_in=described_in or {})
    return {page.url: page for page in pages}


def test_code_pages_list(code_tree: Path) -> None:
    pages = _build_pages(code_tree)
    assert list(pages) == [
        "reference/code/sample.html",
        "reference/code/sample.base.html",
        "reference/code/sample.mod.html",
    ]
    mod = pages["reference/code/sample.mod.html"]
    assert mod.components == ("core",)
    assert mod.status == "implemented"
    assert [link.url for link in mod.breadcrumb] == [
        "index.html",
        "reference/index.html",
        "reference/code/index.html",
        "reference/code/sample.html",
    ]
    assert [link.url for link in pages["reference/code/sample.html"].children] == [
        "reference/code/sample.base.html",
        "reference/code/sample.mod.html",
    ]
    assert pages["reference/code/sample.base.html"].children == ()
    code_reference = CodeReference(load_sample_code(code_tree), ProjectConfig.load(code_tree), "")
    assert code_reference.build_module_children() == (
        PageLink("sample", "reference/code/sample.html", "Sample package."),
    )


def test_code_page_members(code_tree: Path) -> None:
    body = _build_pages(code_tree)["reference/code/sample.mod.html"].body_html
    for expected in (
        'id="sample.mod.Thing"',
        'id="sample.mod.Thing.run"',
        'id="sample.mod.LIMIT"',
        'id="sample.mod.Alias"',
        "@property",
        "@classmethod",
        "n: int = 3",
        "fast: bool = False",
        "-&gt; str",
        "ValueError",
        "When n is negative.",
        "The limit.",
        "How big.",
        "<details",
        '<nav class="members">',
    ):
        assert expected in body, expected
    assert "_helper" not in body
    assert "->" not in body


def test_code_page_links(code_tree: Path) -> None:
    body = _build_pages(code_tree)["reference/code/sample.mod.html"].body_html
    assert 'href="sample.base.html#sample.base.Base"' in body
    inherited = body[body.index("Inherited from") :]
    assert 'href="sample.base.html#sample.base.Base.hello"' in inherited
    assert ">hello<" in inherited
    assert 'href="https://github.com/o/r/blob/c0ffee/tools/sample/src/sample/mod.py#L' in body
    assert 'href="#sample.mod.Thing"' in body


def test_code_page_docs_lines_and_described_in(code_tree: Path) -> None:
    pages = _build_pages(code_tree, {"sample.mod": [PageLink("X", "meta/x.html")]})
    mod = pages["reference/code/sample.mod.html"]
    assert 'href="../../meta/vocabulary.html"' in mod.body_html
    assert "Docs: meta/vocabulary.md" not in mod.body_html
    assert mod.described_in == (PageLink("X", "meta/x.html"),)
    assert pages["reference/code/sample.html"].described_in == ()


def test_code_page_escapes_and_signature_forms(code_tree: Path) -> None:
    (code_tree / "tools/sample/src/sample/mod.py").write_text(
        "from sample.base import Base\n\n\n"
        "def f(a, b='<x>', /, c: Base | None = None, *args: int, d, **kw: str) -> list[Base]:\n"
        '    """See [the base](code:sample.base.Base)."""\n\n\ndef g[T: int](x: T) -> T:\n    return x\n',
        encoding="utf-8",
    )
    body = _build_pages(code_tree)["reference/code/sample.mod.html"].body_html
    assert "def f(a, b=&#39;&lt;x&gt;&#39;, /, c: " in body
    assert '<a href="sample.base.html#sample.base.Base">Base</a> | None = None, *args: int, d, **kw: str)' in body
    assert '-&gt; list[<a href="sample.base.html#sample.base.Base">Base</a>]' in body
    assert '<a href="sample.base.html#sample.base.Base">the base</a>' in body
    assert "def g[T: int](x: T) -&gt; T" in body


def test_code_page_overloads(code_tree: Path) -> None:
    (code_tree / "tools/sample/src/sample/mod.py").write_text(
        "from typing import overload\n\n\n"
        '@overload\ndef f(a: int) -> int:\n    """Int form."""\n\n\n'
        "@overload\ndef f(a: str) -> str: ...\n\n\n"
        "def f(a):\n    return a\n\n\n"
        "class C:\n"
        "    @overload\n    def m(self, a: int) -> int: ...\n\n"
        "    @overload\n    def m(self, a: str) -> str: ...\n\n"
        '    def m(self, a):\n        """Impl doc."""\n        return a\n',
        encoding="utf-8",
    )
    body = _build_pages(code_tree)["reference/code/sample.mod.html"].body_html
    order = ["def f(a: int) -&gt; int", "def f(a: str) -&gt; str", "def f(a)"]
    positions = [body.index(text) for text in order]
    assert positions == sorted(positions)
    assert "Int form." in body
    assert body.count('id="sample.mod.f"') == 1
    order = ["def m(self, a: int)", "def m(self, a: str)", "def m(self, a)"]
    positions = [body.index(text) for text in order]
    assert positions == sorted(positions)
    assert body.count('id="sample.mod.C.m"') == 1
    assert "Impl doc." in body


def test_code_page_overload_decorators_above_implementation(code_tree: Path) -> None:
    (code_tree / "tools/sample/src/sample/mod.py").write_text(
        "from typing import overload\n\n\n"
        "class D:\n"
        "    @overload\n    @staticmethod\n    def s(a: int) -> int: ...\n\n"
        "    @overload\n    @staticmethod\n    def s(a: str) -> str: ...\n\n"
        '    @staticmethod\n    def s(a):\n        """Impl doc."""\n        return a\n',
        encoding="utf-8",
    )
    body = _build_pages(code_tree)["reference/code/sample.mod.html"].body_html
    decorator = body.index('<span class="decorator">@staticmethod')
    assert body.index("def s(a: str)") < decorator < body.index("def s(a)")


def test_code_pages_without_source_url_have_no_source_links(code_tree: Path) -> None:
    config = ProjectConfig.load(code_tree)
    codebase = Codebase.load(code_tree, config)
    pages = _build_module_pages(codebase, config, source_url="", described_in={})
    assert pages
    for page in pages:
        assert "/blob/" not in page.body_html, page.url
        assert 'class="source"' not in page.body_html, page.url


def test_code_page_griffe_error_is_code_error(code_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_griffe_error(*args: object) -> str:
        raise griffe.GriffeError("cannot resolve sample.gone")

    monkeypatch.setattr("docspecsite.coderef.CodePage.render_body", raise_griffe_error)
    with pytest.raises(CodeError) as raised:
        _build_pages(code_tree)
    assert str(raised.value) == "cannot document sample: cannot resolve sample.gone"
    assert isinstance(raised.value.__cause__, griffe.GriffeError)
