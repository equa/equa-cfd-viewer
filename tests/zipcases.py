"""Zipped IDA ICE cases for tests, built from the committed fixtures
(openspec ice-project-zips, D9). No zip is committed."""

import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERIAL = ROOT / "data" / "hotRoom"
DECOMPOSED = ROOT / "tests" / "data" / "hotRoomPar"


def zip_tree(case_dir, target, metadata=None, extra=()):
    """Zip *case_dir* into *target* as cfd-backend's pack() does: paths
    relative to the case, plus ``metadata.json`` and *extra* ``(name, bytes)``."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        if case_dir is not None:
            for path in sorted(Path(case_dir).rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(case_dir).as_posix())
        if metadata is not None:
            zf.writestr("metadata.json", json.dumps(metadata))
        for name, data in extra:
            zf.writestr(name, data)
    return target


def project(base, name="office"):
    """An IDA ICE project under *base*: a serial and a decomposed solved case,
    a bare one and a corrupt file. Returns ``{key: zip path}``."""
    cfd = base / name / "cfd"
    zips = {
        "serial": zip_tree(SERIAL, cfd / "11111111-aaaa.zip", {"NAME": "case-1"}),
        "decomposed": zip_tree(DECOMPOSED, cfd / "22222222-bbbb.zip", {"NAME": "case-2"}),
        "bare": zip_tree(None, cfd / "33333333-cccc.zip", {"NAME": "case-3"},
                         extra=[("building.opf", b""), ("geometry/building.obj", b"")]),
    }
    zips["corrupt"] = cfd / "44444444-dddd.zip"
    zips["corrupt"].write_bytes(b"not a zip")
    return zips


def unsafe(target):
    """A zip that looks like a case but holds a member escaping its entry."""
    return zip_tree(None, target, {"NAME": "evil"},
                    extra=[("system/controlDict", b"FoamFile {}\n"), ("../evil.txt", b"x")])
