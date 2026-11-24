import re
import warnings
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import griffe
import pytest
from conftest import load_sample_code, write_roles_module

from docspecsite.codeindex import CodeTarget
from docspecsite.coderef import (
    BrokenReference,
    Codebase,
    CodeError,
    CodeReference,
    DocsLine,
    FoundPackages,
    Package,
    ParsedDocstring,
    UnusableInput,
    split_docs_lines,
)
from docspecsite.config import ProjectConfig
from docspecsite.errors import DocspecsiteWarning
from docspecsite.markdown import MarkdownText
from docspecsite.pages import Page, PageLink
from docspecsite.urls import make_doc_url

OVERLOADED = (
    "from typing import overload\n\n\n"
    "@overload\n"
    "def f(x: int) -> int:\n"
    '    """Uses :meth:`.nope`.\n\n    Docs: missing.md\n    """\n\n\n'
    "@overload\n"
    "def f(x: str) -> str: ...\n\n\n"
    "def f(x):\n    return x\n"
)
SAMPLE_MODULE_PATH = "tools/sample/src/sample/mod.py"
ROLES_MODULE = """from sample.base import Base


def f() -> None:
    \"\"\"A function, see [the S class](code:sample.roles.S).\"\"\"


def _private() -> None:
    \"\"\"Hidden.\"\"\"


class R:
    \"\"\"Use :meth:`.go`, :class:`~sample.base.Base`, :meth:`~.nope` and :meth:`the nope <.nope2>`.\"\"\"

    def __init__(self) -> None:
        \"\"\"Make one.\"\"\"

    def go(self) -> S:
        \"\"\"Go.\"\"\"


class S:
    \"\"\"No init.\"\"\"
"""


def test_find_packages(code_tree: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    found = Codebase.find_packages(code_tree, ProjectConfig.load(code_tree))
    assert found == FoundPackages((Package("sample", code_tree / "tools/sample/src/sample", "tools/sample/src"),), ())
    empty = Codebase.find_packages(tmp_path_factory.mktemp("empty"), ProjectConfig.from_bytes(None))
    assert empty == FoundPackages((), ())


def test_find_packages_leaves_out_names_python_cannot_import(code_tree: Path) -> None:
    src = code_tree / "tools/sample/src"
    for name in ("a.b", "class", "1pkg", "a-b"):
        (src / name).mkdir()
        (src / name / "__init__.py").write_text("", encoding="utf-8")
    (src / "not_a_package.d").mkdir()  # no __init__.py: not a package, so its name is not checked
    found = Codebase.find_packages(code_tree, ProjectConfig.load(code_tree))
    assert [package.name for package in found.packages] == ["sample"]
    assert found.left_out == tuple(
        UnusableInput(f"tools/sample/src/{name}", f'directory name "{name}" is not a valid Python package name')
        for name in ("1pkg", "a-b", "a.b", "class")
    )


def test_find_packages_follows_a_symlinked_code_dir_to_its_target(code_tree: Path) -> None:
    target = code_tree / "lib/python/other"
    target.mkdir(parents=True)
    (target / "__init__.py").write_text("", encoding="utf-8")
    (code_tree / "tools/linked").mkdir()
    (code_tree / "tools/linked/src").symlink_to("../../lib/python")
    (code_tree / "tools/broken").mkdir()
    (code_tree / "tools/broken/src").symlink_to("../../nowhere")
    found = Codebase.find_packages(code_tree, ProjectConfig.load(code_tree))
    assert Package("other", code_tree / "lib/python/other", "lib/python") in found.packages
    assert found.left_out == (
        UnusableInput("tools/broken/src", "symlink to an absolute path, outside the repo or to a missing file"),
    )


def test_codebase_without_valid_packages_has_no_modules(code_tree: Path) -> None:
    (code_tree / "tools/sample/src/sample").rename(code_tree / "tools/sample/src/a.b")
    codebase = Codebase.load(code_tree, ProjectConfig.load(code_tree))
    assert codebase.modules == []
    assert [left_out.path for left_out in codebase.left_out] == ["tools/sample/src/a.b"]


def test_find_packages_rejects_a_name_in_two_code_dirs(code_tree: Path) -> None:
    other = code_tree / "tools/other/src/sample"
    other.mkdir(parents=True)
    (other / "__init__.py").write_text('"""Other sample."""\n', encoding="utf-8")
    with pytest.raises(CodeError) as raised:
        Codebase.find_packages(code_tree, ProjectConfig.load(code_tree))
    assert str(raised.value) == "package sample is in more than one code directory: tools/other/src, tools/sample/src"


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


def test_docs_line_in_single_quoted_docstring(code_tree: Path) -> None:
    assert _docs_lines_for(code_tree, '"Docs: a.md"\n') == [DocsLine("a.md", SAMPLE_MODULE_PATH, 1)]
    assert _docs_lines_for(code_tree, "r'Docs: b.md'\n") == [DocsLine("b.md", SAMPLE_MODULE_PATH, 1)]


def test_docs_line_in_docstring_with_trailing_comment(code_tree: Path) -> None:
    source = '"""Title.\n\nDocs: a.md\n"""  # noqa\n'
    assert _docs_lines_for(code_tree, source) == [DocsLine("a.md", SAMPLE_MODULE_PATH, 3)]
    assert _docs_lines_for(code_tree, '"""Docs: b.md"""  # a "#" """ b\n') == [DocsLine("b.md", SAMPLE_MODULE_PATH, 1)]


def test_form_feed_and_line_separator_keep_docstring_lines(code_tree: Path) -> None:
    source = (
        '# x\x0c\n# y\u2028z\x85\ndef f() -> None:\n    """F.\n\n    Docs: b.md\n\n    See :meth:`.nope`.\n    """\n'
    )
    write_roles_module(code_tree, source)
    codebase = load_sample_code(code_tree)
    roles_path = "tools/sample/src/sample/roles.py"
    assert codebase.collect_docs_lines() == [
        DocsLine("meta/vocabulary.md", SAMPLE_MODULE_PATH, 3),
        DocsLine("b.md", roles_path, 6),
    ]
    assert codebase.collect_broken_references() == [BrokenReference(":meth:`.nope`", roles_path, 8)]


def test_overload_docstring_checked(code_tree: Path) -> None:
    write_roles_module(code_tree, OVERLOADED)
    codebase = load_sample_code(code_tree)
    roles_path = "tools/sample/src/sample/roles.py"
    assert DocsLine("missing.md", roles_path, 8) in codebase.collect_docs_lines()
    assert codebase.collect_broken_references() == [BrokenReference(":meth:`.nope`", roles_path, 6)]


def test_implementation_docstring_wins_over_overload_docstring(code_tree: Path) -> None:
    write_roles_module(code_tree, OVERLOADED.replace("    return x\n", '    """Impl."""\n    return x\n'))
    codebase = load_sample_code(code_tree)
    assert codebase.collect_broken_references() == []
    assert [d for d in codebase.collect_docs_lines() if d.file.endswith("roles.py")] == []


def test_empty_code_target_in_docstring_problem_and_plain_text(code_tree: Path) -> None:
    write_roles_module(
        code_tree, 'def f() -> None:\n    """Go.\n\n    See [this](code:) and [that](code:sample.gone).\n    """\n'
    )
    codebase = load_sample_code(code_tree)
    roles_path = "tools/sample/src/sample/roles.py"
    assert codebase.collect_broken_references() == [
        BrokenReference("code:", roles_path, 4, is_empty_target=True),
        BrokenReference("code:sample.gone", roles_path, 4),
    ]
    code_reference = CodeReference.for_commit(
        codebase, ProjectConfig.load(code_tree), "c0ffee", locate_doc=make_doc_url
    )
    module = next(m for m in codebase.modules if m.path == "sample.roles")
    with pytest.warns(DocspecsiteWarning, match=r"^tools/sample/src/sample/roles\.py:4: empty code: target; left out$"):
        body = code_reference.build_page(module, ()).body_html
    assert "See this and" in body
    assert 'class="marker code-gone">no longer exists</span>' in body
    assert body.count("no longer exists") == 1


def test_unlocatable_broken_reference_still_renders_the_page(code_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_roles_module(code_tree, 'def f() -> None:\n    """Go to [this](code:).\n    """\n')
    codebase = load_sample_code(code_tree)
    original_iter_texts = ParsedDocstring.iter_texts

    def iter_unlocatable_texts(parsed: ParsedDocstring) -> Iterator[str]:
        # A rendered line that is in no line of the docstring's source cannot be placed.
        return (text.replace("Go to", "Gone to") for text in original_iter_texts(parsed))

    monkeypatch.setattr(ParsedDocstring, "iter_texts", iter_unlocatable_texts)
    code_reference = CodeReference.for_commit(
        codebase, ProjectConfig.load(code_tree), "c0ffee", locate_doc=make_doc_url
    )
    module = next(m for m in codebase.modules if m.path == "sample.roles")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        body = code_reference.build_page(module, ()).body_html
    assert "Go to this" in body


def test_unreadable_docstring_source_still_renders_the_page(code_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_roles_module(code_tree, 'def f() -> None:\n    """Go to [this](code:).\n    """\n')
    codebase = load_sample_code(code_tree)

    def raise_not_utf8(_codebase: Codebase, obj: griffe.Object, _docstring: griffe.Docstring) -> list[str]:
        raise CodeError("source of %s is not valid UTF-8", obj.path)

    monkeypatch.setattr(Codebase, "read_docstring_lines", raise_not_utf8)
    code_reference = CodeReference.for_commit(
        codebase, ProjectConfig.load(code_tree), "c0ffee", locate_doc=make_doc_url
    )
    module = next(m for m in codebase.modules if m.path == "sample.roles")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        body = code_reference.build_page(module, ()).body_html
    assert "Go to this" in body


def test_code_module_template_anchor_exists() -> None:
    root = Path(__file__).parents[1]
    template = (root / "src/docspecsite/templates/code_module.html").read_text(encoding="utf-8")
    [anchor] = re.findall(r"docs-tooling\.md#([\w-]+)", template.splitlines()[0])
    tooling = MarkdownText((root / "docs/architecture/docs-tooling.md").read_text(encoding="utf-8"))
    assert anchor in tooling.collect_heading_anchors()


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
    code_reference = CodeReference.for_commit(
        codebase, replace(config, source_url=source_url), "c0ffee", locate_doc=make_doc_url
    )
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
    assert mod.statuses == ("implemented",)
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
    code_reference = CodeReference(
        load_sample_code(code_tree), ProjectConfig.load(code_tree), "", locate_doc=make_doc_url
    )
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

    codebase = load_sample_code(code_tree)
    config = ProjectConfig.load(code_tree)
    module = next(m for m in codebase.modules if m.path == "sample.mod")
    linking_reference = CodeReference.for_commit(
        codebase, config, "c0ffee", locate_doc=lambda path: f"https://h/{path}"
    )
    assert (
        '<a href="https://h/meta/vocabulary.md">meta/vocabulary.md</a>'
        in linking_reference.build_page(module, ()).body_html
    )
    text_reference = CodeReference.for_commit(codebase, config, "c0ffee", locate_doc=lambda path: None)
    assert "<li>meta/vocabulary.md</li>" in text_reference.build_page(module, ()).body_html


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


def test_code_pages_of_changed_files_have_no_source_links(code_tree: Path) -> None:
    config = ProjectConfig.load(code_tree)
    codebase = Codebase.load(code_tree, config)
    code_reference = CodeReference.for_commit(
        codebase,
        config,
        "c0ffee",
        locate_doc=make_doc_url,
        changed_paths=frozenset({"tools/sample/src/sample/mod.py"}),
    )
    pages = {module.path: code_reference.build_page(module, []) for module in codebase.modules}
    assert "/blob/" not in pages["sample.mod"].body_html
    assert "https://github.com/o/r/blob/c0ffee/tools/sample/src/sample/base.py#L" in pages["sample.base"].body_html


def test_source_link_percent_encodes_path(code_tree: Path) -> None:
    (code_tree / "tools/sample").rename(code_tree / "tools/s #%?")
    pages = _build_pages(code_tree)
    body = pages["reference/code/sample.mod.html"].body_html
    assert 'href="https://github.com/o/r/blob/c0ffee/tools/s%20%23%25%3F/src/sample/mod.py#L' in body


def test_code_page_griffe_error_is_code_error(code_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_griffe_error(*args: object) -> str:
        raise griffe.GriffeError("cannot resolve sample.gone")

    monkeypatch.setattr("docspecsite.coderef.CodePage.render_body", raise_griffe_error)
    with pytest.raises(CodeError) as raised:
        _build_pages(code_tree)
    assert str(raised.value) == "cannot document sample: cannot resolve sample.gone"
    assert isinstance(raised.value.__cause__, griffe.GriffeError)


def _load_roles_module(root: Path) -> tuple[Codebase, griffe.Module]:
    write_roles_module(root, ROLES_MODULE)
    codebase = load_sample_code(root)
    return codebase, next(m for m in codebase.modules if m.path == "sample.roles")


def test_find_role_target(code_tree: Path) -> None:
    codebase, module = _load_roles_module(code_tree)
    class_r, method_go = module["R"], module["R.go"]
    assert codebase.find_role_target(".go", method_go) == "sample.roles.R.go"
    assert codebase.find_role_target(".go", class_r) == "sample.roles.R.go"
    assert codebase.find_role_target(".f", method_go) == "sample.roles.f"
    assert codebase.find_role_target(".S.__init__", module) == "sample.roles.S"
    assert codebase.find_role_target(".__init__", method_go) == "sample.roles.R.__init__"
    assert codebase.find_role_target("sample.base.Base", module) == "sample.base.Base"
    assert codebase.find_role_target("go", method_go) == "sample.roles.R.go"
    assert codebase.find_role_target("__init__", method_go) == "sample.roles.R.__init__"
    assert codebase.find_role_target("S.__init__", module) == "sample.roles.S"
    assert codebase.find_role_target("f", method_go) == "sample.roles.f"
    assert codebase.find_role_target("Base", module) is None
    assert codebase.find_role_target(".Base", module) is None
    assert codebase.find_role_target("._private", module) is None


def test_code_page_roles(code_tree: Path) -> None:
    codebase, module = _load_roles_module(code_tree)
    code_reference = CodeReference.for_commit(
        codebase, ProjectConfig.load(code_tree), "c0ffee", locate_doc=make_doc_url
    )
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        body = code_reference.build_page(module, ()).body_html
    assert '<a href="#sample.roles.R.go"><code>sample.roles.R.go</code></a>' in body
    assert '<a href="sample.base.html#sample.base.Base"><code>Base</code></a>' in body
    assert '<code>.nope</code><span class="marker code-gone">no longer exists</span>' in body
    assert '<code>the nope</code><span class="marker code-gone">no longer exists</span>' in body
    assert [type(w.message) for w in recorded] == [DocspecsiteWarning, DocspecsiteWarning]
    assert '<a href="#sample.roles.S">the S class</a>' in body
    assert '-&gt; <a href="#sample.roles.S">S</a>' in body


def test_collect_broken_references(code_tree: Path) -> None:
    write_roles_module(
        code_tree,
        "def f() -> None:\n"
        '    """\n'
        "    Summary.\n"
        "\n"
        "    See :meth:`.nope`, [a](CODE:sample.gone), [b](CODE:sample.roles.f) and [c](code:sample.mod).\n"
        "\n"
        "    Args:\n"
        "        a: First, :meth:`.f`.\n"
        "\n"
        "            More about :meth:`.nope2`.\n"
        "\n"
        "    Returns:\n"
        "        Nothing, :class:`.gone`.\n"
        '    """\n',
    )
    found = load_sample_code(code_tree).collect_broken_references()
    roles_path = "tools/sample/src/sample/roles.py"
    assert found == [
        BrokenReference(":meth:`.nope`", roles_path, 5),
        BrokenReference("CODE:sample.gone", roles_path, 5),
        BrokenReference(":meth:`.nope2`", roles_path, 10),
        BrokenReference(":class:`.gone`", roles_path, 13),
    ]


def test_collect_broken_references_skips_namespace_package(tmp_path: Path) -> None:
    namespace = griffe.Module("ns", filepath=[tmp_path / "a" / "ns", tmp_path / "b" / "ns"])
    namespace.docstring = griffe.Docstring("See :meth:`.nope`.", lineno=1, endlineno=1, parent=namespace)
    assert Codebase([namespace], []).collect_broken_references() == []


def test_cached_property_shown_as_cached_property(code_tree: Path) -> None:
    write_roles_module(
        code_tree,
        "from functools import cached_property\n\n\n"
        "class C:\n"
        '    @cached_property\n    def slow(self) -> int:\n        """Slow."""\n        return 1\n\n'
        '    @property\n    def fast(self) -> int:\n        """Fast."""\n        return 1\n',
    )
    body = _build_pages(code_tree)["reference/code/sample.roles.html"].body_html
    assert '<span class="decorator">@cached_property</span>' in body
    assert body.count('<span class="decorator">@property</span>') == 1


def test_inherited_member_from_private_mixin_not_credited_to_later_base(code_tree: Path) -> None:
    write_roles_module(
        code_tree,
        "class _Mixin:\n    def run(self) -> None: ...\n\n    def only_mixin(self) -> None: ...\n\n\n"
        "class Base:\n    def run(self) -> None: ...\n\n    def only_base(self) -> None: ...\n\n\n"
        'class C(_Mixin, Base):\n    """C."""\n',
    )
    body = _build_pages(code_tree)["reference/code/sample.roles.html"].body_html
    inherited = body[body.index("Inherited from") :]
    assert "only_base" in inherited
    assert ">run<" not in inherited
