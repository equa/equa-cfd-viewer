"""The vtkBlockColors pseudo-field: patch ids on the boundary, nothing inside."""

from pathlib import Path

import numpy as np
import pytest

from equa.cfd_viewer.foamviz.case import BLOCK_COLORS
from equa.cfd_viewer.server import wire
from equa.cfd_viewer.server.scene import SceneSource
from equa.cfd_viewer.server.sources import DirectorySource

DATA = Path(__file__).parents[1] / "data"
PARTS = "boundary,slice,iso,stream,glyph"


@pytest.fixture(scope="module")
def source():
    src = SceneSource(DirectorySource([DATA]))
    src.open("hotRoom")
    return src


def _scene(source, **query):
    header, parts = wire.unpack(source.scene({"case": "hotRoom", "parts": PARTS, **query}))
    return header, {p["name"]: p for p in parts}


def test_meta_offers_it_apart_from_the_fields(source):
    meta = source.meta()
    assert meta["patchField"] == BLOCK_COLORS
    assert BLOCK_COLORS not in meta["fields"]


@pytest.mark.parametrize("cell_data", ["0", "1"])
def test_boundary_carries_patch_ids_and_internal_parts_none(source, cell_data):
    header, parts = _scene(source, field=BLOCK_COLORS, cell_data=cell_data)
    n = len(source.case.patches)
    assert header["range"] == [-0.5, n - 0.5]
    ids = np.unique(parts["boundary"]["attributes"]["scalar"])
    assert ids.tolist() == list(range(n))
    for name in ("slice", "stream", "glyph"):
        assert "scalar" not in parts[name]["attributes"], name
    assert "iso" not in parts


def test_ids_survive_deselecting_patches(source):
    kept = source.case.patches[1:]
    header, parts = _scene(source, field=BLOCK_COLORS, patches=",".join(kept))
    ids = np.unique(parts["boundary"]["attributes"]["scalar"])
    assert ids.tolist() == list(range(1, len(source.case.patches)))
    assert header["range"] == [0.5, len(source.case.patches) - 0.5]


def test_a_real_field_colours_the_internal_parts_again(source):
    _scene(source, field=BLOCK_COLORS)
    _, parts = _scene(source, field="U")
    for name in ("boundary", "slice", "iso", "stream", "glyph"):
        assert "scalar" in parts[name]["attributes"], name
