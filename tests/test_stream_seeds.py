"""Streamline seeds stay on their own plane while the cut plane moves."""

from pathlib import Path

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


def _lines(scene, **query):
    _, parts = wire.unpack(scene.scene({"parts": "stream,slice", "plane_axis": "z", **query}))
    return next(p for p in parts if p["name"] == "stream")["attributes"]["position"].tobytes()


def test_moving_the_cut_plane_keeps_the_streamlines(scene):
    seeded = {"stream_plane_axis": "z", "stream_plane_coord": "1.0"}
    assert _lines(scene, plane_coord="1.0", **seeded) == _lines(scene, plane_coord="2.0", **seeded)


def test_reseeding_moves_them(scene):
    assert (_lines(scene, plane_coord="1.0", stream_plane_axis="z", stream_plane_coord="1.0")
            != _lines(scene, plane_coord="1.0", stream_plane_axis="z", stream_plane_coord="2.0"))


def test_without_a_seed_plane_they_follow_the_cut_plane(scene):
    assert _lines(scene, plane_coord="2.0") == _lines(
        scene, plane_coord="1.0", stream_plane_axis="z", stream_plane_coord="2.0")
