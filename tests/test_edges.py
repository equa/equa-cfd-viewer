"""Cell edges on the wire: the real mesh grid, not triangle diagonals."""

from pathlib import Path

import numpy as np
import pytest

from equa.cfd_viewer.server import wire
from equa.cfd_viewer.server.scene import SceneSource
from equa.cfd_viewer.server.sources import DirectorySource

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def scene():
    source = SceneSource(DirectorySource([ROOT / "data"]))
    source.open("hotRoom")
    return source


def _part(scene, name, **query):
    _, parts = wire.unpack(scene.scene({"parts": name, **query}))
    return next(p for p in parts if p["name"] == name)


def _distinct(part):
    """Edges as unordered position pairs, so de-indexed copies compare equal."""
    pos = np.round(part["attributes"]["position"], 6)
    return {
        tuple(sorted((tuple(pos[a]), tuple(pos[b]))))
        for a, b in part["edges"].reshape(-1, 2)
    }


def test_boundary_ships_no_edges_unless_asked(scene):
    assert _part(scene, "boundary")["edges"] is None


def test_boundary_edges_are_the_cell_grid(scene):
    part = _part(scene, "boundary", boundary_edges="1")
    n_vertices = len(part["attributes"]["position"])
    assert part["edges"].max() < n_vertices
    # 400 quads on hotRoom: 880 cell edges, where a triangulation would add
    # a diagonal per quad.
    assert len(part["edges"]) // 2 == 880


def test_crinkle_slice_carries_its_edges(scene):
    part = _part(scene, "slice", slice_edges="1")
    assert part["edges"] is not None and len(part["edges"]) // 2 == 260


def test_cell_values_keep_the_same_edges(scene):
    indexed = _part(scene, "boundary", boundary_edges="1")
    flat = _part(scene, "boundary", boundary_edges="1", cell_data="1")
    assert flat["edges"].max() < len(flat["attributes"]["position"])
    assert _distinct(flat) == _distinct(indexed)
