from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import NamedTuple

import pytest
from conftest import HistoryRepo, make_commit, write_doc

from docspecsite.codeindex import CodeTarget
from docspecsite.config import ProjectConfig
from docspecsite.errors import DocspecsiteWarning
from docspecsite.git import Git
from docspecsite.history import History, Version
from docspecsite.markdown import RenderedLink
from docspecsite.urls import MARKERS, DocPages, PageLinks, Resolver, find_reserved_owner, make_relative_url

SOURCE = "https://github.com/o/r"
CONFIG = ProjectConfig((), SOURCE, {})
NO_SOURCE_CONFIG = ProjectConfig((), "", {})
CODE = {
    "pkg.mod": CodeTarget("pkg.mod", None),
    "pkg.mod.C": CodeTarget("pkg.mod", "pkg.mod.C"),
}


class HistoryAndVersions(NamedTuple):
    """The history of ``history_repo`` with its doc versions by name."""

    history: History
    versions: dict[str, Version]
    """Versions of ``meta/a.md`` and ``meta/b.md`` by doc and commit name, e.g. ``a@c1``."""
    commits: dict[str, str]
    """Full SHA hash of each named commit, by name (``c1``..``c5``)."""


def get_no_front_matter(_: Version) -> Mapping[str, object] | None:
    return None


@dataclass(frozen=True)
class _DocPages:
    """Doc pages of a fake build: every doc is built and has versions, unless listed."""

    unbuilt_docs: frozenset[str] = frozenset()
    versionless_docs: frozenset[str] = frozenset()
    base_url: str | None = None
    """Base URL that unbuilt docs are linked under; None makes them text."""

    def is_built_doc(self, path: str) -> bool:
        return path not in self.unbuilt_docs

    def is_versionless(self, path: str) -> bool:
        return path in self.versionless_docs

    def locate_doc(self, path: str) -> str | None:
        return f"{self.base_url}/{path}" if self.base_url is not None else None


def load_history_and_versions(repo: HistoryRepo) -> HistoryAndVersions:
    """Return the history of ``history_repo`` and its versions of ``meta/a.md`` and ``meta/b.md``.

    Args:
        repo: The ``history_repo`` fixture's repository.
    """
    root, commits = repo
    history = History.load(Git(root), "main")
    key = {sha: name for name, sha in commits.items()}
    versions = {
        f"{p[5]}@{key[v.commit.sha]}": v
        for p in ("meta/a.md", "meta/b.md")
        for v in history.versions_by_path[p]
        if v.commit is not None
    }
    return HistoryAndVersions(history, versions, commits)


def make_resolver(
    history: History,
    front_matter_of: Callable[[Version], Mapping[str, object] | None] = get_no_front_matter,
    *,
    code: Mapping[str, CodeTarget] | None = CODE,
    config: ProjectConfig = CONFIG,
    doc_pages: DocPages | None = None,
    found_files: frozenset[str] | None = None,
) -> Resolver:
    """Return a resolver over a history; by default every file of its tree is found and every doc is built."""
    return Resolver(
        history,
        code,
        config,
        front_matter_of,
        doc_pages=_DocPages() if doc_pages is None else doc_pages,
        found_files=frozenset(history.tree) if found_files is None else found_files,
        unbuilt_part_files=frozenset(),
    )


def test_latest_links_to_latest(history_repo: HistoryRepo, recwarn: pytest.WarningsRecorder) -> None:
    history, v, commits = load_history_and_versions(history_repo)
    link_resolver = make_resolver(history)
    assert PageLinks(link_resolver, v["a@c5"], "meta/a.html").resolve_link("b.md") == RenderedLink("b.html")
    assert PageLinks(link_resolver, v["a@c5"], f"meta/a/v/{commits['c5'][:12]}.html").resolve_link(
        "b.md"
    ) == RenderedLink("../../b.html")
    assert not recwarn


def test_old_links_to_contemporary(history_repo: HistoryRepo) -> None:
    history, v, commits = load_history_and_versions(history_repo)
    rewritten_link = PageLinks(make_resolver(history), v["a@c3"], f"meta/a/v/{commits['c3'][:12]}.html").resolve_link(
        "b.md#s"
    )
    assert rewritten_link == RenderedLink(f"../../b/v/{commits['c2'][:12]}.html#s")


def test_old_link_to_newer_doc(history_repo: HistoryRepo) -> None:
    history, v, commits = load_history_and_versions(history_repo)
    rewritten_link = PageLinks(make_resolver(history), v["a@c1"], f"meta/a/v/{commits['c1'][:12]}.html").resolve_link(
        "b.md"
    )
    assert rewritten_link == RenderedLink("../../b.html", (MARKERS["newer"],))


def test_link_to_redirect_doc(history_repo: HistoryRepo) -> None:
    history, v, commits = load_history_and_versions(history_repo)

    def front_matter_of(version: Version) -> Mapping[str, object] | None:
        return {"status": "redirect"} if version.short_id == commits["c2"][:12] and version.path == "meta/b.md" else {}

    link_resolver = make_resolver(history, front_matter_of)
    rewritten_link = PageLinks(link_resolver, v["a@c3"], f"meta/a/v/{commits['c3'][:12]}.html").resolve_link("b.md")
    assert rewritten_link == RenderedLink(f"../../b/v/{commits['c2'][:12]}.html", (MARKERS["moved"],))
    assert PageLinks(link_resolver, v["a@c5"], "meta/a.html").resolve_link("b.md") == RenderedLink("b.html")


def test_directory_and_index_links(history_repo: HistoryRepo) -> None:
    history, _, _ = load_history_and_versions(history_repo)
    link_resolver = make_resolver(history)
    index = history.find_latest("index.md")
    assert PageLinks(link_resolver, index, "index.html").resolve_link("meta/") == RenderedLink("meta/index.html")
    arch = history.find_latest("architecture/index.md")
    assert PageLinks(link_resolver, arch, "architecture/index.html").resolve_link("../meta/") == RenderedLink(
        "../meta/index.html"
    )
    assert PageLinks(link_resolver, arch, "architecture/index.html").resolve_link("../meta/index.md") == RenderedLink(
        "../meta/index.html"
    )


def test_docs_root_links(history_repo: HistoryRepo) -> None:
    history, _, _ = load_history_and_versions(history_repo)
    link_resolver = make_resolver(history)
    index = history.find_latest("index.md")
    assert PageLinks(link_resolver, index, "index.html").resolve_link("./") == RenderedLink("index.html")
    arch = history.find_latest("architecture/index.md")
    assert PageLinks(link_resolver, arch, "architecture/index.html").resolve_link("../") == RenderedLink(
        "../index.html"
    )


def test_non_doc_targets(history_repo: HistoryRepo) -> None:
    root, _ = history_repo
    (root / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (root / "docs/meta/img.png").write_bytes(b"\x89PNG")
    write_doc(root, "meta/templates/t.md", "Template.\n")
    (root / "tools/x").mkdir(parents=True)
    (root / "tools/x/f.py").write_text("", encoding="utf-8")
    write_doc(root, "meta/a.md", "Changed with the files.\n")
    sha = make_commit(root, "add files", "2026-11-06T12:00:00+00:00")
    history = History.load(Git(root), "main")
    doc_a_latest = history.find_latest("meta/a.md")
    link_resolver = make_resolver(history)

    def make_link(href: str) -> RenderedLink:
        return PageLinks(link_resolver, doc_a_latest, "meta/a.html").resolve_link(href)

    assert make_link("../../compose.yaml") == RenderedLink(f"{SOURCE}/blob/{sha}/compose.yaml")
    assert make_link("templates/t.md") == RenderedLink(f"{SOURCE}/blob/{sha}/docs/meta/templates/t.md")
    assert make_link("../../tools/x/") == RenderedLink(f"{SOURCE}/tree/{sha}/tools/x")
    assert make_link("img.png") == RenderedLink("img.png")
    with pytest.warns(DocspecsiteWarning) as recorded:
        assert make_link("missing.md") == RenderedLink(None, (MARKERS["not-found"],))
    assert [str(w.message) for w in recorded] == [f"docs/meta/a.md@{sha[:12]}: unresolvable link: missing.md"]
    assert make_link("#local") == RenderedLink("#local")
    assert make_link("https://e.org") == RenderedLink("https://e.org")


def test_found_files_decide_file_links(history_repo: HistoryRepo) -> None:
    root, _ = history_repo
    (root / "docs/meta/img.png").write_bytes(b"\x89PNG")
    make_commit(root, "add an image", "2026-11-06T12:00:00+00:00")
    history = History.load(Git(root), "main")
    latest_a = history.find_latest("meta/a.md")
    link_resolver = make_resolver(history, found_files=frozenset({"docs/meta/alias.md", "docs/meta/shared/flow.png"}))
    links = PageLinks(link_resolver, latest_a, "meta/a.html")
    assert links.resolve_link("alias.md") == RenderedLink("alias.md")
    assert links.resolve_link("shared/flow.png") == RenderedLink("shared/flow.png")
    with pytest.warns(DocspecsiteWarning) as recorded:
        assert links.resolve_link("img.png") == RenderedLink(None, (MARKERS["not-found"],))
    assert [str(w.message) for w in recorded] == [f"docs/meta/a.md@{latest_a.short_id}: unresolvable link: img.png"]


def test_resolve_code_link_without_code_part(history_repo: HistoryRepo, recwarn: pytest.WarningsRecorder) -> None:
    history, v, _ = load_history_and_versions(history_repo)
    link_resolver = make_resolver(history, code=None)
    links = PageLinks(link_resolver, v["a@c5"], "meta/a.html")
    assert links.resolve_link("code:a.b") == RenderedLink(None, use_code_style=True)
    assert not recwarn.list


def test_code_links(history_repo: HistoryRepo) -> None:
    history, v, commits = load_history_and_versions(history_repo)
    link_resolver = make_resolver(history)
    assert PageLinks(link_resolver, v["a@c5"], "meta/a.html").resolve_link("code:pkg.mod.C") == RenderedLink(
        "../reference/code/pkg.mod.html#pkg.mod.C"
    )
    assert PageLinks(link_resolver, v["a@c5"], "meta/a.html").resolve_link("code:pkg.mod") == RenderedLink(
        "../reference/code/pkg.mod.html"
    )
    old = PageLinks(link_resolver, v["a@c3"], f"meta/a/v/{commits['c3'][:12]}.html").resolve_link("code:pkg.mod.C")
    assert old == RenderedLink("../../../reference/code/pkg.mod.html#pkg.mod.C", (MARKERS["code-current"],))
    with pytest.warns(DocspecsiteWarning, match="unknown code element: code:pkg.gone"):
        gone = PageLinks(link_resolver, v["a@c5"], "meta/a.html").resolve_link("code:pkg.gone")
    assert gone == RenderedLink(None, (MARKERS["code-gone"],))


def test_web_api_link_is_text(history_repo: HistoryRepo, recwarn: pytest.WarningsRecorder) -> None:
    history, v, _ = load_history_and_versions(history_repo)
    link_resolver = make_resolver(history)
    assert PageLinks(link_resolver, v["a@c5"], "meta/a.html").resolve_link("web-api:x") == RenderedLink(None)
    assert not recwarn


def test_relative() -> None:
    assert make_relative_url("meta/b.html", "meta/a/v/x.html") == "../../b.html"
    assert make_relative_url("b.html", "meta/a/v/x.html") == "../../../b.html"
    assert make_relative_url("index.html#x", "index.html") == "index.html#x"
    assert make_relative_url("https://e.org/a", "meta/a.html") == "https://e.org/a"
    assert make_relative_url("#x", "meta/a.html") == "#x"


def test_repo_links_without_source_url_are_plain_text(
    history_repo: HistoryRepo, recwarn: pytest.WarningsRecorder
) -> None:
    root, _ = history_repo
    (root / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (root / "docs/meta/img.png").write_bytes(b"\x89PNG")
    write_doc(root, "meta/templates/t.md", "Template.\n")
    (root / "tools/x").mkdir(parents=True)
    (root / "tools/x/f.py").write_text("", encoding="utf-8")
    make_commit(root, "add files", "2026-11-06T12:00:00+00:00")
    history = History.load(Git(root), "main")
    link_resolver = make_resolver(history, config=NO_SOURCE_CONFIG)

    def make_link(href: str) -> RenderedLink:
        return PageLinks(link_resolver, history.find_latest("meta/a.md"), "meta/a.html").resolve_link(href)

    assert make_link("../../compose.yaml") == RenderedLink(None)
    assert make_link("templates/t.md") == RenderedLink(None)
    assert make_link("../../tools/x/") == RenderedLink(None)
    assert make_link("../..") == RenderedLink(None)
    assert make_link("img.png") == RenderedLink("img.png")
    assert make_link("b.md") == RenderedLink("b.html")
    short_id = history.find_latest("meta/a.md").short_id
    assert [str(w.message) for w in recwarn] == [
        (
            f"docs/meta/a.md@{short_id}: docspecsite.toml has no source-url: "
            "links to repository files, such as ../../compose.yaml, are plain text"
        )
    ]


def test_old_link_to_contemporary_that_is_latest(history_repo: HistoryRepo) -> None:
    root, commits = history_repo
    write_doc(root, "meta/a.md", "See [b](b.md). Changed a third time.\n")
    make_commit(root, "change a once more", "2026-11-06T12:00:00+00:00")
    history = History.load(Git(root), "main")
    old = next(v for v in history.versions_by_path["meta/a.md"] if v.short_id == commits["c5"][:12])
    assert history.find_latest("meta/b.md").short_id == commits["c4"][:12]
    rewritten_link = PageLinks(make_resolver(history), old, f"meta/a/v/{commits['c5'][:12]}.html").resolve_link("b.md")
    assert rewritten_link == RenderedLink(f"../../b/v/{commits['c4'][:12]}.html")


def test_repo_links_use_the_version_commit(history_repo: HistoryRepo) -> None:
    root, commits = history_repo
    (root / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    head = make_commit(root, "add compose", "2026-11-06T12:00:00+00:00")
    write_doc(root, "meta/a.md", "Edited, not committed.\n")
    history = History.load(Git(root), "main", worktree_root=root)
    a_versions_by_commit = {v.commit.sha: v for v in history.versions_by_path["meta/a.md"] if v.commit is not None}
    link_resolver = make_resolver(history)
    old = PageLinks(link_resolver, a_versions_by_commit[commits["c3"]], "meta/a.html").resolve_link(
        "../../compose.yaml"
    )
    assert old == RenderedLink(f"{SOURCE}/blob/{commits['c3']}/compose.yaml")
    working = history.find_latest("meta/a.md")
    assert working.commit is None
    assert PageLinks(link_resolver, working, "meta/a.html").resolve_link("../../compose.yaml") == RenderedLink(
        f"{SOURCE}/blob/{head}/compose.yaml"
    )


def test_link_to_unbuilt_doc(history_repo: HistoryRepo, recwarn: pytest.WarningsRecorder) -> None:
    history, v, _ = load_history_and_versions(history_repo)

    def make_link(doc_pages: _DocPages) -> RenderedLink:
        link_resolver = make_resolver(history, doc_pages=doc_pages)
        return PageLinks(link_resolver, v["a@c5"], "meta/a.html").resolve_link("b.md#x")

    unbuilt_docs = frozenset({"meta/b.md"})
    assert make_link(_DocPages(unbuilt_docs, base_url="https://h")) == RenderedLink("https://h/meta/b.md#x")
    assert make_link(_DocPages(unbuilt_docs)) == RenderedLink(None)
    assert not recwarn.list


def test_old_link_to_versionless_doc(history_repo: HistoryRepo) -> None:
    history, v, commits = load_history_and_versions(history_repo)
    link_resolver = make_resolver(history, doc_pages=_DocPages(versionless_docs=frozenset({"meta/b.md"})))
    old_link = PageLinks(link_resolver, v["a@c3"], f"meta/a/v/{commits['c3'][:12]}.html").resolve_link("b.md#s")
    assert old_link == RenderedLink("../../b.html#s", (MARKERS["code-current"],))


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("status.md", "the status page"),
        ("tags/x.md", "the tag pages"),
        ("tags/index.md", "the tag pages"),
        ("components/a/b.md", "the component pages"),
        ("reference/code/sample.mod.md", "the code reference pages"),
        ("reference/code/index.md", None),
        ("meta/v/x.md", "the version pages of docs/meta.md"),
        ("meta/v/deep/x.md", "the version pages of docs/meta.md"),
        ("index/v/x.md", "the version pages of docs/index.md"),
        ("guides/v/x.md", None),
        ("v/x.md", None),
        ("meta/status.md", None),
        ("tags.md", None),
    ],
)
def test_find_reserved_owner(path: str, expected: str | None) -> None:
    assert find_reserved_owner(path, {"index.md", "meta.md", path}) == expected
