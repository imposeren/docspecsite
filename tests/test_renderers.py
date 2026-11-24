from pathlib import Path

import pytest

from docspecsite.build import SiteBuilder
from docspecsite.internal_renderer import InternalRenderer
from docspecsite.renderers import RENDERER_PATHS, RendererName, SiteRenderer, stage_file


def test_stage_file_keeps_each_file_apart_inside_the_staging_dir(tmp_path: Path) -> None:
    first = stage_file(tmp_path, b"one")
    second = stage_file(tmp_path, b"two")
    assert first != second
    assert first.parent == second.parent == tmp_path
    assert (first.read_bytes(), second.read_bytes()) == (b"one", b"two")


@pytest.mark.parametrize("name", list(RendererName))
def test_every_renderer_name_loads_a_site_renderer(name: RendererName) -> None:
    assert name in RENDERER_PATHS
    assert isinstance(SiteBuilder.load_renderer(name), SiteRenderer)


def test_the_internal_renderer_is_loaded_by_its_name() -> None:
    assert type(SiteBuilder.load_renderer(RendererName.INTERNAL)) is InternalRenderer


def test_a_path_that_names_no_site_renderer_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("docspecsite.build.RENDERER_PATHS", {RendererName.INTERNAL: "docspecsite.renderers:PageCount"})
    with pytest.raises(TypeError, match="is not a site renderer"):
        SiteBuilder.load_renderer(RendererName.INTERNAL)
