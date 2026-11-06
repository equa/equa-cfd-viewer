"""OBJ groups outline the geometry: a window flush in its wall must show."""

from pathlib import Path

import vtk

from equa.cfd_viewer.foamviz.pipeline import _group_edges
from equa.cfd_viewer.server import wire
from equa.cfd_viewer.server.scene import SceneSource
from equa.cfd_viewer.server.sources import DirectorySource

ROOT = Path(__file__).resolve().parent.parent

# A 4 x 3 wall in y = 0 with a 2 x 1 window in it, both triangulated.
WALL_WITH_WINDOW = """\
v 0 0 0
v 4 0 0
v 4 0 3
v 0 0 3
v 1 0 1
v 3 0 1
v 3 0 2
v 1 0 2
g wall
f 1 2 6
f 1 6 5
f 2 3 7
f 2 7 6
f 3 4 8
f 3 8 7
f 4 1 5
f 4 5 8
g window
f 5 6 7
f 5 7 8
"""


def _read(path):
    reader = vtk.vtkOBJReader()
    reader.SetFileName(str(path))
    reader.Update()
    return reader.GetOutput()


def _pairs(lines):
    ids = vtk.vtkIdList()
    cells = lines.GetLines()
    cells.InitTraversal()
    out = set()
    while cells.GetNextCell(ids):
        out.add(tuple(sorted((ids.GetId(0), ids.GetId(1)))))
    return out


def test_group_edges_outline_the_window(tmp_path):
    obj = tmp_path / "building.obj"
    obj.write_text(WALL_WITH_WINDOW)
    # 0-based: the window's four sides, not its diagonal or the wall's.
    assert _pairs(_group_edges(_read(obj))) == {(4, 5), (5, 6), (6, 7), (4, 7)}


def test_one_group_adds_nothing():
    assert _group_edges(_read(ROOT / "data/hotRoom/constant/triSurface/building.obj")) is None


def test_feature_edges_on_the_wire_include_the_window(tmp_path):
    case = tmp_path / "hotRoom"
    case.symlink_to(ROOT / "data/hotRoom", target_is_directory=True)
    source = SceneSource(DirectorySource([tmp_path]))
    source.open("hotRoom")
    obj = tmp_path / "building.obj"
    obj.write_text(WALL_WITH_WINDOW)
    source.pipeline.geometry_reader.SetFileName(str(obj))
    _, parts = wire.unpack(source.scene({"parts": "geometry", "geometry_mode": "features"}))
    (part,) = parts
    # 4 outer boundary sides + 4 window sides.
    assert part["index"].size // 2 == 8
