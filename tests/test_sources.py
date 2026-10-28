"""Case discovery, ids, labels and lookups (openspec standalone-viewer, case-sources).

Runs under pytest. The directory-tree tests build synthetic cases -- a case is
just ``system/controlDict`` to discovery, plus whatever metadata a test needs --
so they take milliseconds; the HTTP tests at the end open the real demo case.
"""

import asyncio
import gzip
import json
import os
import time
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer
from zipcases import SERIAL, project, unsafe, zip_tree

from equa.cfd_viewer.foamviz.case import find_cases
from equa.cfd_viewer.server.app import make_app
from equa.cfd_viewer.server.scene import SceneSource
from equa.cfd_viewer.server.sources import (
    AmbiguousCase,
    CaseNotFound,
    DirectorySource,
)

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "data" / "hotRoom"

OWNER_HEADER = """FoamFile
{{
    format      binary;
    class       labelList;
    note        "nPoints:10  nCells:{cells}  nFaces:100  nInternalFaces:80";
    location    "constant/polyMesh";
    object      owner;
}}
"""


def make_case(directory, *, cells=None, gz=False, metadata=None, times=("0",)):
    """A directory discovery treats as a case, with optional mesh header and metadata."""
    directory = Path(directory)
    (directory / "system").mkdir(parents=True)
    (directory / "system" / "controlDict").write_text("FoamFile {}\n")
    for t in times:
        (directory / t).mkdir()
    if cells is not None:
        mesh = directory / "constant" / "polyMesh"
        mesh.mkdir(parents=True)
        header = OWNER_HEADER.format(cells=cells).encode()
        if gz:
            with gzip.open(mesh / "owner.gz", "wb") as f:
                f.write(header)
        else:
            (mesh / "owner").write_bytes(header)
    if metadata is not None:
        (directory / "metadata.json").write_text(json.dumps(metadata))
    return directory


def names(source):
    return [ref.name for ref in source.list()]


# -- discovery ---------------------------------------------------------------


def test_nested_case_found_with_depth(tmp_path):
    make_case(tmp_path / "projects" / "officeA" / "run1")
    assert names(DirectorySource([tmp_path], depth=3)) == ["run1"]


def test_server_mode_finds_cases_where_the_backend_does(tmp_path):
    """The cockpit's CFD_HOME as found at the phase-1 gate: ordinary cases at
    CFD_HOME/<uuid>, test-suite cases at CFD_HOME/tests/<name>. cfd-backend's
    finder (rglob) lists both, so the default scan must too."""
    make_case(tmp_path / "e2614af7")
    make_case(tmp_path / "tests" / "window-radiator-no-ahu_0")
    make_case(tmp_path / "tests" / "therm-beam-only_1")
    assert sorted(names(DirectorySource([tmp_path]))) == [
        "e2614af7", "therm-beam-only_1", "window-radiator-no-ahu_0"]
    source = DirectorySource([tmp_path])
    assert source.resolve("therm-beam-only_1").path == "tests/therm-beam-only_1"


def test_default_bound(tmp_path):
    make_case(tmp_path / "a" / "b" / "c" / "level4")
    make_case(tmp_path / "a" / "b" / "c" / "d" / "level5")
    assert names(DirectorySource([tmp_path])) == ["level4"]


def test_root_that_is_a_case(tmp_path):
    case = make_case(tmp_path / "hotRoom")
    refs = DirectorySource([case]).list()
    assert [(r.name, r.path) for r in refs] == [("hotRoom", ".")]


def test_depth_is_bounded(tmp_path):
    make_case(tmp_path / "a" / "b" / "c" / "deep")
    assert names(DirectorySource([tmp_path], depth=3)) == []
    assert names(DirectorySource([tmp_path], depth=4)) == ["deep"]


def test_several_roots(tmp_path):
    make_case(tmp_path / "A" / "run1")
    make_case(tmp_path / "B" / "run2")
    assert names(DirectorySource([tmp_path / "A", tmp_path / "B"])) == ["run1", "run2"]


def test_skips_processor_and_time_directories_not_hidden(tmp_path):
    """processor* and time directories are case internals; hidden ones are
    searched, as cfd-backend's rglob searches them."""
    make_case(tmp_path / ".staging" / "hidden")
    make_case(tmp_path / "processor0" / "inside")
    make_case(tmp_path / "1730" / "timedir")
    make_case(tmp_path / "visible")
    assert sorted(names(DirectorySource([tmp_path], depth=3))) == ["hidden", "visible"]


def test_does_not_descend_into_a_case(tmp_path):
    outer = make_case(tmp_path / "outer")
    make_case(outer / "nested")
    assert names(DirectorySource([tmp_path], depth=3)) == ["outer"]


# CI runs as root, which chmod 0 does not lock out.
@pytest.mark.skipif(os.name == "posix" and os.geteuid() == 0, reason="root ignores chmod 0")
def test_unreadable_directory_is_reported_not_silent(tmp_path, caplog):
    """A directory the server cannot read is skipped, the rest still listed,
    and a warning names it -- otherwise a permission problem on CFD_HOME looks
    exactly like "no cases"."""
    make_case(tmp_path / "e2614af7")
    locked = tmp_path / "tests"
    make_case(locked / "window-radiator-no-ahu_0")
    locked.chmod(0)
    try:
        with caplog.at_level("WARNING", logger="cfdviewer.sources"):
            assert names(DirectorySource([tmp_path])) == ["e2614af7"]
            DirectorySource([tmp_path]).list()          # a rescan warns no more
    finally:
        locked.chmod(0o755)
    warnings = [r.getMessage() for r in caplog.records if str(locked) in r.getMessage()]
    assert len(warnings) == 1 and "cannot search" in warnings[0]


def test_new_case_appears_without_restart(tmp_path):
    source = DirectorySource([tmp_path])
    assert source.list() == []
    make_case(tmp_path / "late")
    assert names(source) == ["late"]


def test_depth_one_matches_find_cases():
    """Depth 1 is exactly the old one-level scan, on the real data/."""
    data = ROOT / "data"
    assert DirectorySource([data], depth=1).names() == [p.name for p in find_cases(data)]


def test_missing_root_lists_nothing(tmp_path):
    assert DirectorySource([tmp_path / "absent"]).list() == []


# -- identity ----------------------------------------------------------------


def test_ids_are_stable_and_hide_the_path(tmp_path):
    make_case(tmp_path / "runs" / "run1")
    first = DirectorySource([tmp_path], depth=2).list()[0]
    again = DirectorySource([tmp_path], depth=2).list()[0]
    assert first.id == again.id
    assert first.path == "runs/run1"
    assert str(tmp_path) not in first.id and "/" not in first.id


def test_same_name_in_two_places(tmp_path):
    a = make_case(tmp_path / "A" / "run1")
    b = make_case(tmp_path / "B" / "run1")
    source = DirectorySource([tmp_path / "A", tmp_path / "B"])
    ids = [r.id for r in source.list()]
    assert len(set(ids)) == 2
    assert [source.resolve(i).directory for i in ids] == [a, b]
    with pytest.raises(AmbiguousCase) as exc:
        source.resolve("run1")
    assert sorted(exc.value.args[1]) == sorted(ids)


def test_unique_name_resolves(tmp_path):
    case = make_case(tmp_path / "e2614af7")
    assert DirectorySource([tmp_path]).resolve("e2614af7").directory == case


def test_unknown_key(tmp_path):
    make_case(tmp_path / "run1")
    with pytest.raises(CaseNotFound):
        DirectorySource([tmp_path]).resolve("nope")


# -- description -------------------------------------------------------------


def test_ida_ice_case(tmp_path):
    """Label from metadata NAME, cells from the owner note, N-CELLS ignored."""
    make_case(tmp_path / "e2614af7-3602", cells=15757775,
              metadata={"NAME": "case-4", "N-CELLS": 0, "case_info": {"ncells": 1}})
    ref = DirectorySource([tmp_path]).list()[0]
    assert (ref.label, ref.cells, ref.decomposed) == ("case-4", 15757775, False)


def test_gzipped_owner(tmp_path):
    make_case(tmp_path / "run1", cells=1234, gz=True)
    assert DirectorySource([tmp_path]).list()[0].cells == 1234


def test_case_without_metadata_or_note(tmp_path):
    case = make_case(tmp_path / "run1")
    mesh = case / "constant" / "polyMesh"
    mesh.mkdir(parents=True)
    (mesh / "owner").write_text("FoamFile { format ascii; object owner; }\n3\n(0 0 1)\n")
    ref = DirectorySource([tmp_path]).list()[0]
    assert (ref.label, ref.cells) == ("run1", None)


def test_cells_from_case_info_when_no_header(tmp_path):
    make_case(tmp_path / "run1", metadata={"N-CELLS": 999, "case_info": {"ncells": 4321}})
    assert DirectorySource([tmp_path]).list()[0].cells == 4321


def test_stale_n_cells_alone_is_not_used(tmp_path):
    make_case(tmp_path / "run1", metadata={"N-CELLS": 999})
    assert DirectorySource([tmp_path]).list()[0].cells is None


def test_blank_name_falls_back_to_directory(tmp_path):
    make_case(tmp_path / "run1", metadata={"NAME": "  "})
    assert DirectorySource([tmp_path]).list()[0].label == "run1"


def test_unreadable_metadata_is_ignored(tmp_path):
    case = make_case(tmp_path / "run1")
    (case / "metadata.json").write_text("{not json")
    assert DirectorySource([tmp_path]).list()[0].label == "run1"


def test_decomposed_case(tmp_path):
    """Newest time only in processor*: decomposed, cells summed over processors."""
    case = make_case(tmp_path / "par", times=("0",))
    for i, n in enumerate((100, 250)):
        proc = case / f"processor{i}"
        (proc / "90").mkdir(parents=True)
        mesh = proc / "constant" / "polyMesh"
        mesh.mkdir(parents=True)
        (mesh / "owner").write_text(OWNER_HEADER.format(cells=n))
    ref = DirectorySource([tmp_path]).list()[0]
    assert (ref.decomposed, ref.cells) == (True, 350)


def test_json_shape(tmp_path):
    make_case(tmp_path / "run1", cells=7)
    entry = DirectorySource([tmp_path]).list()[0].to_json()
    assert set(entry) == {"id", "name", "label", "path", "decomposed", "cells"}


# -- HTTP --------------------------------------------------------------------


def _get(source, *paths):
    """[(status, body), ...] for GETs against an app over *source*."""

    async def run():
        async with TestClient(TestServer(make_app(source))) as client:
            out = []
            for path in paths:
                response = await client.get(path)
                body = (await response.json() if response.content_type == "application/json"
                        else await response.text())
                out.append((response.status, body))
            return out

    return asyncio.run(run())


def test_cases_endpoint_keeps_names_and_adds_entries(tmp_path):
    make_case(tmp_path / "run1", cells=7, metadata={"NAME": "Office"})
    [(status, body)] = _get(DirectorySource([tmp_path]), "/api/cases")
    assert status == 200
    assert body["cases"] == ["run1"]
    assert body["entries"][0]["label"] == "Office"


def test_unknown_and_missing_case_are_404(tmp_path):
    make_case(tmp_path / "run1")
    (s1, t1), (s2, t2) = _get(DirectorySource([tmp_path]),
                              "/api/meta?case=nope", "/api/meta")
    assert (s1, s2) == (404, 404)
    assert "no case 'nope'" in t1 and "no case given" in t2


def test_ambiguous_name_is_404_with_ids(tmp_path):
    make_case(tmp_path / "A" / "run1")
    make_case(tmp_path / "B" / "run1")
    source = DirectorySource([tmp_path / "A", tmp_path / "B"])
    [(status, text)] = _get(source, "/api/meta?case=run1")
    assert status == 404 and "ambiguous" in text
    assert all(ref.id in text for ref in source.list())


@pytest.mark.skipif(not (DEMO / "constant" / "polyMesh").is_dir(),
                    reason="demo case not built")
def test_open_by_id_and_by_name(tmp_path):
    (tmp_path / "hotRoom").symlink_to(DEMO)
    source = DirectorySource([tmp_path])
    ident = source.list()[0].id
    (s1, by_id), (s2, by_name) = _get(source, f"/api/meta?case={ident}",
                                      "/api/meta?case=hotRoom")
    assert (s1, s2) == (200, 200)
    assert by_id["case"] == "hotRoom" and by_id["caseId"] == ident
    assert by_name["caseId"] == ident and by_name["caseLabel"] == "hotRoom"


def test_added_root_is_listed_and_ids_stay(tmp_path):
    make_case(tmp_path / "a" / "one")
    make_case(tmp_path / "b" / "two")
    source = DirectorySource([tmp_path / "a"])
    before = {r.name: r.id for r in source.list()}
    assert source.add_root(tmp_path / "b")
    after = {r.name: r.id for r in source.list()}
    assert after == {**before, "two": after["two"]}


def test_parent_of_a_root_keeps_its_ids(tmp_path):
    make_case(tmp_path / "a" / "one")
    make_case(tmp_path / "c" / "three")
    source = DirectorySource([tmp_path / "a"])
    before = {r.name: r.id for r in source.list()}
    assert source.add_root(tmp_path)
    refs = source.list()
    assert sorted(r.name for r in refs) == ["one", "three"]
    assert {r.name: r.id for r in refs}["one"] == before["one"]


def test_present_or_nested_root_adds_nothing(tmp_path):
    make_case(tmp_path / "a" / "one")
    source = DirectorySource([tmp_path])
    roots = source.roots
    assert not source.add_root(tmp_path)
    assert not source.add_root(tmp_path / "a")
    assert source.roots is roots
    assert names(source) == ["one"]


# -- zipped IDA ICE cases (openspec ice-project-zips) ------------------------


def _zip_source(tmp_path, roots=None, depth=None):
    from equa.cfd_viewer.server.cache import CaseCache
    kwargs = {"cache": CaseCache(tmp_path / "cache")}
    if depth is not None:
        kwargs["depth"] = depth
    return DirectorySource(roots or [tmp_path / "projects"], **kwargs)


def test_project_zips_are_listed(tmp_path, caplog):
    project(tmp_path / "projects")
    (tmp_path / "projects" / "office" / "notcfd").mkdir()
    zip_tree(SERIAL, tmp_path / "projects" / "office" / "notcfd" / "x.zip")
    source = _zip_source(tmp_path)
    refs = {ref.name: ref for ref in source.list()}
    assert sorted(refs) == ["11111111-aaaa", "22222222-bbbb"]
    serial, par = refs["11111111-aaaa"], refs["22222222-bbbb"]
    assert serial.label == "case-1" and par.label == "case-2"
    assert serial.path == "office/cfd/11111111-aaaa.zip"
    assert serial.archive.name == "11111111-aaaa.zip"
    assert (serial.decomposed, par.decomposed) == (False, True)
    assert source.names() == ["11111111-aaaa", "22222222-bbbb"]
    assert sum("44444444-dddd.zip" in r.message for r in caplog.records) == 1
    source.list()
    assert sum("44444444-dddd.zip" in r.message for r in caplog.records) == 1


def test_zip_cells_from_header_processors_and_metadata(tmp_path):
    cfd = tmp_path / "projects" / "p" / "cfd"
    header = OWNER_HEADER.format(cells=431139).encode()
    proc = OWNER_HEADER.format(cells=10).encode()
    control = ("system/controlDict", b"")
    zip_tree(None, cfd / "a.zip", {}, extra=[control, ("constant/polyMesh/owner", header)])
    zip_tree(None, cfd / "b.zip", {}, extra=[
        control, ("processor0/constant/polyMesh/owner", proc), ("processor0/5/T", b""),
        ("processor1/constant/polyMesh/owner", proc), ("processor1/5/T", b""), ("0/T", b"")])
    zip_tree(None, cfd / "c.zip", {"case_info": {"ncells": 77}}, extra=[control])
    cells = {ref.name: (ref.cells, ref.decomposed) for ref in _zip_source(tmp_path).list()}
    assert cells == {"a": (431139, False), "b": (20, True), "c": (77, False)}


def test_zip_depth_rule_and_cfd_root(tmp_path):
    base = tmp_path / "projects"
    project(base, "office")
    project(base / "a", "deeper")
    shallow = _zip_source(tmp_path, depth=1).list()
    assert sorted(r.path for r in shallow) == ["office/cfd/11111111-aaaa.zip",
                                               "office/cfd/22222222-bbbb.zip"]
    deep = _zip_source(tmp_path, depth=2).list()
    assert len(deep) == 4
    cfd_root = _zip_source(tmp_path, roots=[base / "office" / "cfd"], depth=1).list()
    assert sorted(r.path for r in cfd_root) == ["11111111-aaaa.zip", "22222222-bbbb.zip"]


def test_upper_case_zip_and_cfd(tmp_path):
    zip_tree(SERIAL, tmp_path / "projects" / "p" / "CFD" / "u.ZIP", {"NAME": "upper"})
    [ref] = _zip_source(tmp_path).list()
    assert (ref.name, ref.label) == ("u", "upper")


def test_zip_beside_a_same_named_directory_is_ambiguous(tmp_path):
    zip_tree(SERIAL, tmp_path / "projects" / "p" / "cfd" / "abc.zip")
    make_case(tmp_path / "projects" / "p" / "cfd" / "abc")
    source = _zip_source(tmp_path)
    assert source.names() == ["abc", "abc"]
    with pytest.raises(AmbiguousCase):
        source.resolve("abc")
    for ref in source.list():
        assert source.resolve(ref.id).path == ref.path


def _http(source, *requests, root_path=""):
    """[(status, body), ...] for (method, path) pairs against one app."""

    async def run():
        app = make_app(source, root_path=root_path)
        async with TestClient(TestServer(app)) as client:
            out = []
            for method, path in requests:
                response = await client.request(method, path)
                body = (await response.json() if response.content_type == "application/json"
                        else await response.text())
                out.append((response.status, body))
            return out

    return asyncio.run(run())


def test_open_a_zipped_case_by_name_and_clear(tmp_path):
    project(tmp_path / "projects")
    source = _zip_source(tmp_path)
    (s0, c0), (s1, meta), (s2, c1), (s3, cleared), (s4, c2) = _http(
        source, ("GET", "/api/config"), ("GET", "/api/meta?case=11111111-aaaa"),
        ("GET", "/api/config"), ("POST", "/api/cache/clear"), ("GET", "/api/config"))
    assert (s0, s1, s2, s3, s4) == (200,) * 5
    assert c0["cacheBytes"] == 0
    assert meta["caseLabel"] == "case-1" and meta["case"]
    assert c1["cacheBytes"] > 0
    assert cleared == {"freed": 0, "failed": []}  # the open case is kept
    assert c2["cacheBytes"] == c1["cacheBytes"]


def test_clear_works_behind_root_path(tmp_path):
    source = _zip_source(tmp_path)
    [(status, body)] = _http(source, ("POST", "/viewer/api/cache/clear"), root_path="/viewer")
    assert status == 200 and body == {"freed": 0, "failed": []}


def test_an_unsafe_zip_is_422_and_keeps_the_open_case(tmp_path):
    project(tmp_path / "projects")
    unsafe(tmp_path / "projects" / "office" / "cfd" / "55555555-eeee.zip")
    source = _zip_source(tmp_path)
    (s1, _), (s2, text), (s3, scene_text), (s4, meta) = _http(
        source, ("GET", "/api/meta?case=11111111-aaaa"), ("GET", "/api/meta?case=55555555-eeee"),
        ("GET", "/api/scene?case=55555555-eeee"), ("GET", "/api/meta?case=11111111-aaaa"))
    assert (s1, s2, s3, s4) == (200, 422, 422, 200)
    assert "evil.txt" in text and "evil.txt" in scene_text
    assert meta["caseLabel"] == "case-1"


def test_a_zip_saved_again_while_open_is_unpacked_again(tmp_path):
    zips = project(tmp_path / "projects")
    source = _zip_source(tmp_path)
    scene = SceneSource(source)
    scene.open("11111111-aaaa")
    first = scene.ref.directory
    assert scene.is_open("11111111-aaaa")
    zip_tree(SERIAL, zips["serial"], {"NAME": "case-1 again"})
    os.utime(zips["serial"], ns=(time.time_ns(), time.time_ns() + 10**9))
    assert not scene.is_open("11111111-aaaa")
    scene.open("11111111-aaaa")
    assert scene.ref.directory != first and scene.ref.label == "case-1 again"


def test_the_decomposed_zip_opens(tmp_path):
    project(tmp_path / "projects")
    scene = SceneSource(_zip_source(tmp_path))
    case = scene.open("22222222-bbbb")
    assert case.decomposed and case.n_cells() > 0


def test_browse_marks_projects_without_opening_zips(tmp_path, monkeypatch):
    import zipfile

    from equa.cfd_viewer.server.local import browse
    project(tmp_path)
    (tmp_path / "plain").mkdir()

    def refuse(*_args, **_kwargs):
        raise AssertionError("browse opened a zip")

    monkeypatch.setattr(zipfile, "ZipFile", refuse)
    marks = {e["name"]: e["hasCases"] for e in browse(str(tmp_path))["entries"]}
    assert marks == {"office": True, "plain": False}
    inside = {e["name"]: e["hasCases"] for e in browse(str(tmp_path / "office"))["entries"]}
    assert inside == {"cfd": True}


def test_meta_names_the_zip_not_its_cache_entry(tmp_path):
    project(tmp_path / "projects")
    scene = SceneSource(_zip_source(tmp_path))
    scene.open("11111111-aaaa")
    assert scene.meta()["case"] == "11111111-aaaa"
