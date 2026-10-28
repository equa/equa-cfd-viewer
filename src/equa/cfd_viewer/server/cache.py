"""The case cache: zipped cases unpacked on first open (openspec ice-project-zips).

IDA ICE saves each CFD case of a project as ``<project>/cfd/<case-id>.zip``.
VTK's reader needs a directory, so the first open unpacks the whole zip into an
entry here; later opens reuse it while the zip's size and mtime are unchanged,
since both are in the entry's key (D3, D4). Nothing is ever written next to the
zip.

Each entry holds ``.cfd-viewer.json`` -- the zip, its size and mtime, the
unpacked bytes, when it was last used and by which viewer process -- written
before the entry is renamed into place, so an entry without it is incomplete.
Entries go after 48 h unused, or when their zip changed or is gone; the open
case stays, and so does anything another viewer sharing the cache used in the
last 10 minutes, as it may be open there (D5).
"""

import hashlib
import json
import logging
import os
import re
import shutil
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from .paths import user_dir

log = logging.getLogger("cfdviewer.cache")

RETENTION = 48 * 3600
# Another viewer's entry used this recently may be open there (D5).
GRACE = 10 * 60
# Which viewer process last used an entry; its own entries need no grace.
VIEWER = uuid.uuid4().hex
META = ".cfd-viewer.json"
PARTIAL = ".partial"
# A fresh file may be held by an antivirus scanner for a moment (Windows).
RENAME_TRIES = 50
RENAME_WAIT = 0.1

# Characters Windows refuses in a file name; zipfile would silently rewrite them.
_FORBIDDEN = re.compile(r'[<>:"|?*\x00-\x1f]')


class UnsafeArchive(Exception):
    """A zip that cannot be unpacked safely: corrupt, or a member name that
    would land outside its entry or is not a valid file name."""


class NoSpace(Exception):
    """Not enough free disk for the unpack, or no cache directory at all."""


def default_root():
    """The per-user cache directory, or None when it cannot be resolved (a
    container with an arbitrary UID and no home): the server must still start."""
    try:
        return user_dir("LOCALAPPDATA", "XDG_CACHE_HOME", ".cache") / "cases"
    except (RuntimeError, KeyError, OSError):
        return None


def _key(archive, stat):
    raw = f"{Path(archive).resolve()}\0{stat.st_size}\0{stat.st_mtime_ns}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def check_member(name):
    """Raise UnsafeArchive unless *name* stays inside the entry and is a valid
    file name on every platform."""
    posix = name.replace("\\", "/")
    parts = PurePosixPath(posix).parts
    if (posix.startswith("/") or re.match(r"[A-Za-z]:", posix)
            or ".." in parts or any(_FORBIDDEN.search(p) for p in parts)):
        raise UnsafeArchive(f"unsafe member name {name!r}")


def _read_meta(entry):
    try:
        data = json.loads((entry / META).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_meta(entry, data):
    # Replaced, not rewritten: /api/config reads it without the scene lock.
    tmp = entry / (META + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, entry / META)


def _nearest_existing(path):
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return path.anchor


def _rename(src, dst):
    for attempt in range(RENAME_TRIES):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if os.name != "nt" or attempt == RENAME_TRIES - 1:
                raise
            time.sleep(RENAME_WAIT)


def _zip_matches(meta):
    try:
        stat = Path(meta["zip"]).stat()
    except (OSError, KeyError, TypeError):
        return False
    return stat.st_size == meta.get("size") and stat.st_mtime_ns == meta.get("mtime_ns")


class CaseCache:
    """Unpacked zips under *root*; *root* None means there is no cache, and
    every unpack fails with NoSpace."""

    def __init__(self, root):
        self.root = Path(root) if root is not None else None

    def entry_for(self, archive):
        """The entry *archive* unpacks to as it is now; None without a cache."""
        if self.root is None:
            return None
        return self.root / _key(archive, Path(archive).stat())

    def ensure(self, archive, entry, keep=()):
        """Unpack *archive* into *entry* unless it is there; mark it used."""
        if entry is None:
            raise NoSpace("no cache directory: set XDG_CACHE_HOME or HOME")
        meta = _read_meta(entry)
        if meta is not None:
            meta.update(last_used=time.time(), viewer=VIEWER)
            _write_meta(entry, meta)
            return entry
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise NoSpace(f"cannot create the case cache {self.root}: {exc}") from exc
        self.prune(keep=keep)
        try:
            with zipfile.ZipFile(archive) as zf:
                infos = zf.infolist()
                for info in infos:
                    check_member(info.filename)
                needed = sum(info.file_size for info in infos)
                free = shutil.disk_usage(_nearest_existing(self.root)).free
                if needed > free:
                    raise NoSpace(f"unpacking {Path(archive).name} needs {needed / 1e6:.0f} MB, "
                                  f"{free / 1e6:.0f} MB free: use Clear case cache")
                partial = entry.with_name(entry.name + PARTIAL)
                shutil.rmtree(partial, ignore_errors=True)
                zf.extractall(partial)
        except zipfile.BadZipFile as exc:
            raise UnsafeArchive(f"{Path(archive).name} is not a readable zip: {exc}") from exc
        stat = Path(archive).stat()
        _write_meta(partial, {"zip": str(Path(archive).resolve()), "size": stat.st_size,
                              "mtime_ns": stat.st_mtime_ns, "unpacked_bytes": needed,
                              "last_used": time.time(), "viewer": VIEWER})
        _rename(partial, entry)
        log.info("unpacked %s to %s (%d MB)", archive, entry, needed // 1_000_000)
        return entry

    def _entries(self):
        try:
            return sorted(p for p in self.root.iterdir() if p.is_dir())
        except (OSError, AttributeError):  # no root, or not created yet
            return []

    def _delete(self, entry):
        try:
            shutil.rmtree(entry)
            return True
        except OSError as exc:
            # Windows cannot delete a file another process holds; next prune.
            log.warning("cannot delete cache entry %s (%s)", entry, exc)
            return False

    def _recent(self, entry, meta, now):
        """Another viewer's entry used, or a ``.partial`` begun, in the grace
        time: ours are only ever unpacked under the scene lock."""
        if meta is not None:
            return meta.get("viewer") != VIEWER and now - meta.get("last_used", 0) < GRACE
        try:
            return now - entry.stat().st_mtime < GRACE
        except OSError:
            return False

    def prune(self, keep=(), now=None):
        """Delete entries unused for 48 h, whose zip changed or is gone, and
        incomplete ones; never one in *keep* or recent in another viewer."""
        now = time.time() if now is None else now
        keep = set(keep)
        for entry in self._entries():
            if entry in keep:
                continue
            meta = None if entry.name.endswith(PARTIAL) else _read_meta(entry)
            if self._recent(entry, meta, now):
                continue
            if (meta is None or now - meta.get("last_used", 0) > RETENTION
                    or not _zip_matches(meta)):
                self._delete(entry)

    def clear(self, keep=(), now=None):
        """Delete every entry but those in *keep* and another viewer's recent ones.
        Returns the bytes freed and the entries that could not be deleted."""
        now = time.time() if now is None else now
        keep = set(keep)
        freed, failed = 0, []
        for entry in self._entries():
            meta = None if entry.name.endswith(PARTIAL) else _read_meta(entry)
            if entry in keep or self._recent(entry, meta, now):
                continue
            if self._delete(entry):
                freed += (meta or {}).get("unpacked_bytes", 0)
            else:
                failed.append(entry.name)
        return {"freed": freed, "failed": failed}

    def size(self):
        """Unpacked bytes of all complete entries, as recorded; no walk."""
        total = 0
        for entry in self._entries():
            meta = _read_meta(entry)
            if meta is not None:
                total += meta.get("unpacked_bytes", 0)
        return total
