"""The case cache: unpack, reuse, safety, retention and clear (openspec
ice-project-zips, D3-D6). Zips are built at test time (``zipcases``)."""

import json
import os
import shutil
import subprocess
import sys
import time
from collections import namedtuple

import pytest
from zipcases import SERIAL, project, unsafe, zip_tree

from equa.cfd_viewer.server import cache as cache_mod
from equa.cfd_viewer.server.cache import CaseCache, NoSpace, UnsafeArchive, check_member
from equa.cfd_viewer.server.sources import DirectorySource


@pytest.fixture
def cache(tmp_path):
    return CaseCache(tmp_path / "cache")


def _meta(entry):
    return json.loads((entry / cache_mod.META).read_text())


def _set_last_used(entry, when, viewer=None):
    meta = _meta(entry)
    meta["last_used"] = when
    if viewer is not None:
        meta["viewer"] = viewer
    (entry / cache_mod.META).write_text(json.dumps(meta))


def _unpack(cache, archive, keep=()):
    return cache.ensure(archive, cache.entry_for(archive), keep=keep)


# -- unpack and reuse ----------------------------------------------------------


def test_first_open_unpacks_then_reuses(tmp_path, cache):
    archive = project(tmp_path)["serial"]
    entry = _unpack(cache, archive)
    assert (entry / "system" / "controlDict").is_file()
    assert (entry / "740" / "T").is_file()
    marker = entry / "marker"
    marker.write_text("still here")
    assert _unpack(cache, archive) == entry
    assert marker.is_file()  # reused, not unpacked again
    assert sorted(p.name for p in archive.parent.iterdir()) == sorted(
        ["11111111-aaaa.zip", "22222222-bbbb.zip", "33333333-cccc.zip", "44444444-dddd.zip"])


def test_a_replaced_zip_gets_a_new_entry(tmp_path, cache):
    archive = project(tmp_path)["serial"]
    old = _unpack(cache, archive)
    zip_tree(SERIAL, archive, {"NAME": "case-1 again"})
    os.utime(archive, ns=(time.time_ns(), time.time_ns() + 10**9))
    new = _unpack(cache, archive)
    assert new != old
    assert json.loads((new / "metadata.json").read_text())["NAME"] == "case-1 again"


def test_meta_records_the_unpack(tmp_path, cache):
    archive = project(tmp_path)["serial"]
    entry = _unpack(cache, archive)
    meta = _meta(entry)
    assert meta["zip"] == str(archive.resolve())
    assert meta["size"] == archive.stat().st_size
    assert meta["unpacked_bytes"] == sum(
        p.stat().st_size for p in entry.rglob("*") if p.is_file() and p.name != cache_mod.META)
    assert cache.size() == meta["unpacked_bytes"]


def test_the_server_imports_without_a_cycle():
    subprocess.run([sys.executable, "-c", "import equa.cfd_viewer.server.app"], check=True)


# -- safety ----------------------------------------------------------------------


def test_an_escaping_member_is_refused(tmp_path, cache):
    archive = unsafe(tmp_path / "p" / "cfd" / "evil.zip")
    with pytest.raises(UnsafeArchive, match="evil.txt"):
        _unpack(cache, archive)
    assert not (tmp_path / "evil.txt").exists()
    assert not (cache.root / "evil.txt").exists()
    assert list(cache.root.iterdir()) == []


@pytest.mark.parametrize("name", ["/etc/passwd", "C:/x", "a/../../b", "con?.txt", 'a"b', "x\x01"])
def test_unsafe_names(name):
    with pytest.raises(UnsafeArchive):
        check_member(name)


@pytest.mark.parametrize("name", ["system/controlDict", "processor0/900/U", "0_org/T", ".last"])
def test_safe_names(name):
    check_member(name)


def test_a_corrupt_zip_is_unsafe(tmp_path, cache):
    archive = tmp_path / "cfd" / "x.zip"
    archive.parent.mkdir()
    archive.write_bytes(b"not a zip")
    with pytest.raises(UnsafeArchive, match="not a readable zip"):
        _unpack(cache, archive)


def test_too_little_disk_is_no_space(tmp_path, cache, monkeypatch):
    archive = project(tmp_path)["serial"]
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(cache_mod.shutil, "disk_usage", lambda _p: usage(10, 9, 1))
    with pytest.raises(NoSpace, match="Clear case cache"):
        _unpack(cache, archive)


def test_no_cache_directory_is_no_space(tmp_path):
    archive = project(tmp_path)["serial"]
    cache = CaseCache(None)
    assert cache.entry_for(archive) is None
    assert cache.size() == 0
    cache.prune()
    with pytest.raises(NoSpace, match="no cache directory"):
        cache.ensure(archive, None)


def test_no_home_resolves_no_root(monkeypatch):
    for var in ("XDG_CACHE_HOME", "LOCALAPPDATA", "HOME"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(cache_mod, "user_dir", _raise_runtime)
    assert cache_mod.default_root() is None


def _raise_runtime(*_args):
    raise RuntimeError("Could not determine home directory.")


# -- retention -------------------------------------------------------------------


def test_prune_by_age_zip_and_partial(tmp_path, cache):
    zips = project(tmp_path)
    old = _unpack(cache, zips["serial"])
    gone = _unpack(cache, zips["decomposed"])
    _set_last_used(old, time.time() - 49 * 3600)
    _set_last_used(gone, time.time() - 3600)
    zips["decomposed"].unlink()
    stale_partial = cache.root / ("abc" + cache_mod.PARTIAL)
    fresh_partial = cache.root / ("def" + cache_mod.PARTIAL)
    stale_partial.mkdir()
    fresh_partial.mkdir()
    an_hour_ago = time.time() - 3600
    os.utime(stale_partial, (an_hour_ago, an_hour_ago))
    cache.prune()
    assert sorted(p.name for p in cache.root.iterdir()) == [fresh_partial.name]


def test_prune_keeps_open_and_recent(tmp_path, cache):
    zips = project(tmp_path)
    open_entry = _unpack(cache, zips["serial"])
    recent = _unpack(cache, zips["decomposed"])
    _set_last_used(open_entry, time.time() - 49 * 3600)
    _set_last_used(recent, time.time() - 5 * 60, viewer="another viewer")
    cache.prune(keep={open_entry})
    assert open_entry.is_dir() and recent.is_dir()


def test_an_undeletable_entry_is_skipped(tmp_path, cache, monkeypatch):
    zips = project(tmp_path)
    a = _unpack(cache, zips["serial"])
    b = _unpack(cache, zips["decomposed"])
    for entry in (a, b):
        _set_last_used(entry, time.time() - 49 * 3600)
    real = shutil.rmtree

    def rmtree(path, *args, **kwargs):
        if path == a:
            raise PermissionError(13, "in use")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(cache_mod.shutil, "rmtree", rmtree)
    cache.prune()
    assert a.is_dir() and not b.exists()


def test_unpack_prunes_first(tmp_path, cache):
    zips = project(tmp_path)
    old = _unpack(cache, zips["serial"])
    _set_last_used(old, time.time() - 49 * 3600)
    _unpack(cache, zips["decomposed"])
    assert not old.exists()


# -- clear -----------------------------------------------------------------------


def test_clear_keeps_open_and_recent(tmp_path, cache):
    zips = project(tmp_path)
    open_entry = _unpack(cache, zips["serial"])
    other = _unpack(cache, zips["decomposed"])
    _set_last_used(other, time.time() - 3600)
    expected = _meta(other)["unpacked_bytes"]
    answer = cache.clear(keep={open_entry})
    assert answer == {"freed": expected, "failed": []}
    assert open_entry.is_dir() and not other.exists()
    assert cache.size() == _meta(open_entry)["unpacked_bytes"]


def test_clear_keeps_another_viewers_recent_entry_only(tmp_path, cache):
    zips = project(tmp_path)
    ours = _unpack(cache, zips["serial"])
    theirs = _unpack(cache, zips["decomposed"])
    _set_last_used(theirs, time.time() - 5 * 60, viewer="another viewer")
    cache.clear()
    assert not ours.exists() and theirs.is_dir()


def test_listing_writes_nothing(tmp_path, cache):
    project(tmp_path)
    refs = DirectorySource([tmp_path], cache=cache).list()
    assert len(refs) == 2
    assert not cache.root.exists()
