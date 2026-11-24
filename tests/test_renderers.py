from pathlib import Path

import pytest

from docspecsite.internal_renderer import InternalRenderer
from docspecsite.renderers import RendererName, SiteRenderer, stage_file

_RENDERER_CLASSES: dict[RendererName, type[SiteRenderer]] = {RendererName.INTERNAL: InternalRenderer}


def test_stage_file_keeps_each_file_apart_inside_the_staging_dir(tmp_path: Path) -> None:
    first = stage_file(tmp_path, b"one")
    second = stage_file(tmp_path, b"two")
    assert first != second
    assert first.parent == second.parent == tmp_path
    assert (first.read_bytes(), second.read_bytes()) == (b"one", b"two")


@pytest.mark.parametrize("name", list(RendererName))
def test_every_renderer_name_loads_its_site_renderer(name: RendererName) -> None:
    assert type(SiteRenderer.load(name)) is _RENDERER_CLASSES[name]


def test_a_path_that_names_no_site_renderer_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(SiteRenderer, "IMPORT_PATHS", {RendererName.INTERNAL: "docspecsite.renderers:PageCount"})
    with pytest.raises(TypeError, match="is not a site renderer"):
        SiteRenderer.load(RendererName.INTERNAL)
