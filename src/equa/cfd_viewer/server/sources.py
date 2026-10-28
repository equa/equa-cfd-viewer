"""Where cases come from: one or more directories, scanned on demand.

A *case source* lists the cases it can see and turns a ``?case=`` key into a
directory VTK can read. Phase 1 has one kind, :class:`DirectorySource`; the
hosted viewer's uploads (openspec standalone-viewer, design D7) become a second
kind with the same two methods.

Listing is deliberately cheap -- it runs on every ``/api/cases`` and every
``?case=`` lookup, so a case written after start-up shows up without a restart
-- and never constructs a VTK reader: what it reports (label, cell count,
decomposed) comes from ``metadata.json`` and the mesh header alone.

Identity
--------
A case has an **id**, a short hash of its root and its path below that root:
stable across restarts and rescans, unique across roots, and free of host paths.
``?case=`` takes an id, or a directory **name** when exactly one listed case has
it -- which is what keeps the cfd-backend cockpit's ``/viz/?case=<uuid-dir>``
working. A name that matches several cases, or nothing, is an error the HTTP
layer turns into a 404; the old behaviour of opening the first case instead is
gone on purpose.

Discovery depth
---------------
Server mode finds cases the way cfd-backend does: its ``cfd_cases.find`` takes
every directory below ``CFD_HOME`` that has ``system/controlDict``, at any
depth (``rglob``), and the cockpit links a case by its directory name. So the
viewer searches every level too, bounded by ``depth`` -- directory levels below
a root, :data:`SERVER_SCAN_DEPTH` by default -- so a stray deep tree cannot
slow every request. Test-suite cases, for one, live in ``CFD_HOME/tests/<name>``,
which the old one-level scan never saw (found at the phase-1 gate, 2026-10-22).

A root is always scanned, and listed when it is itself a case (``find_cases``
did the same). Below it, a case directory is not descended into -- a case holds
no cases, and pruning there is what keeps the walk cheap -- and neither are
``processor*`` or numeric time directories. Hidden directories are searched,
as the backend searches them.

Names must be unique for the cockpit's links to work; the backend relies on
that as well (``/api/wd/ls/<name>`` takes the first match). Where they are not,
a name is ambiguous here and gets a 404 listing the ids, rather than the
backend's silent first match.

The backend also lists "bare" cases (``building.opf`` + ``geometry/building.obj``,
not yet meshed); there is nothing to view in those, so they are left out.

Zipped cases
------------
An IDA ICE project keeps its CFD cases as ``<project>/cfd/<case-id>.zip``
(openspec ice-project-zips, D1). The walk lists the zips of every ``cfd``
directory it meets -- the ``cfd`` level is free, so ``--scan-depth`` counts the
project, not its ``cfd`` -- when the zip holds ``system/controlDict``. Listing
reads the zip's central directory, ``metadata.json`` and the owner header; it
never unpacks. A zipped case's ``directory`` is its entry in the case cache
(:mod:`server.cache`), which need not exist until the case is opened.
"""

import gzip
import hashlib
import json
import logging
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from ..foamviz.case import is_decomposed
from .cache import CaseCache, default_root

log = logging.getLogger("cfdviewer.sources")

# Directory levels below a root searched in server mode. CFD_HOME/<case> and
# CFD_HOME/tests/<case> need 1 and 2; 4 leaves room for deeper grouping.
SERVER_SCAN_DEPTH = 4

# Enough to hold an OpenFOAM FoamFile header, note line included.
_HEADER_BYTES = 4096
_NCELLS = re.compile(rb"nCells:\s*(\d+)")


_warned = set()


def _warn_once(path, exc, archive=False):
    if str(path) not in _warned:
        _warned.add(str(path))
        reason = getattr(exc, "strerror", None) or exc  # BadZipFile has none
        if archive:
            log.warning("cannot read %s (%s); it is not listed", path, reason)
        else:
            log.warning("cannot search %s for cases (%s); cases below it are not listed",
                        path, reason)


class CaseNotFound(KeyError):
    """No listed case has this id or name."""


class AmbiguousCase(KeyError):
    """Several listed cases share this name; an id is needed."""


@dataclass(frozen=True)
class CaseRef:
    id: str
    name: str
    label: str
    path: str  # relative to its root, POSIX separators; "." for the root itself
    directory: Path | None  # a zipped case's cache entry; None without a cache
    decomposed: bool
    cells: int | None
    archive: Path | None = None  # the zip of a zipped case

    def to_json(self):
        return {"id": self.id, "name": self.name, "label": self.label,
                "path": self.path, "decomposed": self.decomposed, "cells": self.cells}


def is_case(directory):
    # On Python 3.12, Path.is_file() RAISES PermissionError for a path inside a
    # directory the server cannot search (it ignores only ENOENT-like errors);
    # 3.14 answers False, as os.path.isfile always has (both checked
    # 2026-10-22). The package supports 3.12, so guard: one locked directory
    # under CFD_HOME must not turn the listing into a 500 there.
    try:
        return (directory / "system" / "controlDict").is_file()
    except OSError as exc:
        _warn_once(directory, exc)
        return False


def case_id(root, relative):
    digest = hashlib.sha1(f"{Path(root).resolve()}\0{relative}".encode()).hexdigest()
    return digest[:12]


def _metadata(directory):
    """The IDA ICE backend's ``metadata.json``, or {} if absent or unreadable."""
    try:
        data = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _is_cfd(path):
    return path.name.lower() == "cfd"


def _is_zip(path):
    return path.suffix.lower() == ".zip"


def _case_name(path):
    return path.name[:-4] if _is_zip(path) else path.name


def _zip_case(path):
    """Whether *path* is a readable zip holding ``system/controlDict``."""
    try:
        with zipfile.ZipFile(path) as zf:
            return "system/controlDict" in zf.NameToInfo
    except (OSError, zipfile.BadZipFile) as exc:
        _warn_once(path, exc, archive=True)
        return False


def _zips(cfd_dir):
    """The zipped cases directly in a ``cfd`` directory, sorted."""
    try:
        files = sorted(p for p in cfd_dir.iterdir() if _is_zip(p) and p.is_file())
    except OSError as exc:
        _warn_once(cfd_dir, exc)
        return []
    return [p for p in files if _zip_case(p)]


def _cells_in(head):
    match = _NCELLS.search(head)
    return int(match.group(1)) if match else None


def _zip_header_cells(zf, mesh_dir):
    """``nCells`` from the owner header of a zip member, or None."""
    for name, gz in ((f"{mesh_dir}/owner", False), (f"{mesh_dir}/owner.gz", True)):
        if name not in zf.NameToInfo:
            continue
        with zf.open(name) as f:
            head = gzip.GzipFile(fileobj=f).read(_HEADER_BYTES) if gz else f.read(_HEADER_BYTES)
        return _cells_in(head)
    return None


def _latest(names):
    times = []
    for name in names:
        try:
            times.append(float(name))
        except ValueError:
            pass
    return max(times) if times else None


def _zip_facts(path):
    """``(metadata, decomposed, cells)`` of a zipped case, read from the zip
    alone, by the same rules as for a directory (D2)."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            try:
                metadata = json.loads(zf.read("metadata.json"))
            except (KeyError, ValueError):
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            top = {n.split("/", 1)[0] for n in names if "/" in n}
            proc0 = {n.split("/")[1] for n in names
                     if n.startswith("processor0/") and n.count("/") >= 2}
            proc_latest = _latest(proc0)
            root_latest = _latest(top)
            decomposed = proc_latest is not None and (
                root_latest is None or proc_latest > root_latest)
            cells = _zip_header_cells(zf, "constant/polyMesh")
            if cells is None and decomposed:
                procs = sorted(t for t in top if re.fullmatch(r"processor\d+", t))
                counts = [_zip_header_cells(zf, f"{p}/constant/polyMesh") for p in procs]
                if counts and None not in counts:
                    cells = sum(counts)
    except (OSError, zipfile.BadZipFile) as exc:
        _warn_once(path, exc, archive=True)
        return {}, False, None
    if cells is None:
        cells = _metadata_cells(metadata)
    return metadata, decomposed, cells


def _header_cells(owner_dir):
    """``nCells`` from the ``note`` in an ``owner`` header, or None.

    OpenFOAM writes ``note "nPoints:… nCells:… nFaces:…"`` into the header of
    ``polyMesh/owner``; reading the first few kB gives the cell count of a
    multi-GB mesh without parsing it. ASCII meshes written by some tools carry
    no note, hence None.
    """
    for name, opener in (("owner", open), ("owner.gz", gzip.open)):
        path = owner_dir / name
        try:
            if not path.is_file():
                continue
            with opener(path, "rb") as f:
                head = f.read(_HEADER_BYTES)
        except OSError:
            return None
        match = _NCELLS.search(head)
        return int(match.group(1)) if match else None
    return None


def _cells(directory, metadata, decomposed):
    """Cell count without loading the mesh, or None when it cannot be known.

    The mesh header first; for a decomposed case whose root has no mesh, the
    sum over ``processor*``. Then ``case_info.ncells`` from ``metadata.json``.
    ``N-CELLS`` is never used: it is observed stale (0) on real cases.
    """
    cells = _header_cells(directory / "constant" / "polyMesh")
    if cells is None and decomposed:
        counts = [_header_cells(p / "constant" / "polyMesh")
                  for p in sorted(directory.glob("processor*"))]
        if counts and None not in counts:
            cells = sum(counts)
    if cells is None:
        cells = _metadata_cells(metadata)
    return cells


def _metadata_cells(metadata):
    """``case_info.ncells``, never the stale ``N-CELLS``; None when absent."""
    info = metadata.get("case_info")
    value = info.get("ncells") if isinstance(info, dict) else None
    return value if isinstance(value, int) and value > 0 else None


def _skip(directory):
    name = directory.name
    if name.startswith("processor"):
        return True
    try:
        float(name)  # a time directory
        return True
    except ValueError:
        return False


class DirectorySource:
    """Cases under one or more directory roots, rescanned on every call."""

    def __init__(self, roots, depth=SERVER_SCAN_DEPTH, cache=None):
        self.roots = [Path(r) for r in roots]
        self.depth = depth
        self.cache = cache if cache is not None else CaseCache(default_root())

    def describe(self):
        return ", ".join(str(r) for r in self.roots)

    def add_root(self, path):
        """Add *path* as a root while the server runs; False when it adds nothing.

        A root already present, or inside one, is ignored. A parent of a present
        root is added, and its walk skips that root, so the cases there keep the
        ids they have under it. The list is replaced, not appended to:
        ``list()`` runs in a thread without the scene lock (openspec
        local-desktop-viewer, D2).
        """
        new = Path(path).resolve()
        if any(new == r or new.is_relative_to(r) for r in self._resolved()):
            return False
        self.roots = [*self.roots, new]
        return True

    def _resolved(self):
        return [r.resolve() for r in self.roots]

    def _walk(self, root, inner=frozenset()):
        """Case directories and zipped cases under *root*, root first, then
        sorted, depth-bounded. Directories in *inner* -- other roots inside this
        one -- are skipped."""
        if not root.is_dir():
            return
        if is_case(root):
            yield root
        if _is_cfd(root):
            yield from _zips(root)
        level = [root]
        for i in range(self.depth):
            below = []
            for parent in level:
                try:
                    children = sorted(p for p in parent.iterdir() if p.is_dir())
                except OSError as exc:
                    # Skip it and list the rest -- but say so: a directory the
                    # server's user cannot read looks exactly like "no cases"
                    # otherwise. Once per directory, not on every rescan.
                    _warn_once(parent, exc)
                    continue
                for child in children:
                    if _skip(child) or (inner and child.resolve() in inner):
                        continue
                    if is_case(child):
                        yield child
                        continue
                    if _is_cfd(child):
                        yield from _zips(child)
                    elif i == self.depth - 1:
                        # The last level: its cfd directories are not visited,
                        # but the cfd level is free (D1). A stat, not a listing;
                        # case-insensitive only where the filesystem is.
                        cfd = child / "cfd"
                        if cfd.is_dir():
                            yield from _zips(cfd)
                    below.append(child)
            level = below

    def _found(self):
        """``(root, path, relative, id, name)`` for every case, *path* a case
        directory or a zip: no I/O beyond the walk and each zip's file list."""
        roots = self.roots
        resolved = [r.resolve() for r in roots]
        for root, here in zip(roots, resolved):
            inner = frozenset(r for r in resolved if r != here and r.is_relative_to(here))
            for directory in self._walk(root, inner):
                relative = (directory.relative_to(root).as_posix()
                            if directory != root else ".")
                yield root, directory, relative, case_id(root, relative), _case_name(directory)

    def _ref(self, root, path, relative, ident, name):
        if _is_zip(path) and path.is_file():
            metadata, decomposed, cells = _zip_facts(path)
            try:
                directory = self.cache.entry_for(path)
            except OSError:  # the zip went away since the walk
                directory = None
            archive = path
        else:
            metadata = _metadata(path)
            decomposed = is_decomposed(path)
            cells = _cells(path, metadata, decomposed)
            directory, archive = path, None
        label = metadata.get("NAME")
        return CaseRef(
            id=ident,
            name=name,
            label=label if isinstance(label, str) and label.strip() else name,
            path=relative,
            directory=directory,
            decomposed=decomposed,
            cells=cells,
            archive=archive,
        )

    def list(self):
        """Every case, with its label, cell count and layout."""
        return [self._ref(*found) for found in self._found()]

    def names(self):
        """Directory names, in listing order (the original ``/api/cases``)."""
        return [entry[4] for entry in self._found()]

    def resolve(self, key):
        """The case an id or a unique name denotes.

        Only the matching case's metadata and mesh header are read, so a lookup
        costs a directory walk, not a full listing. Raises
        :class:`CaseNotFound` or :class:`AmbiguousCase`.
        """
        found = list(self._found())
        for entry in found:
            if entry[3] == key:
                return self._ref(*entry)
        named = [entry for entry in found if entry[4] == key]
        if len(named) == 1:
            return self._ref(*named[0])
        if named:
            raise AmbiguousCase(key, [entry[3] for entry in named])
        raise CaseNotFound(key)
