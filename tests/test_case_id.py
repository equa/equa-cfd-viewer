"""The case id is the key saved views are stored under (openspec
saved-views-train C3, R2): the same across sources over the same root, new
after the case moves."""

from test_sources import make_case
from zipcases import SERIAL, zip_tree

from equa.cfd_viewer.server.sources import DirectorySource


def ids(root):
    return {ref.name: ref.id for ref in DirectorySource([root]).list()}


def test_case_id_is_stable_and_follows_the_path(tmp_path):
    make_case(tmp_path / "runs" / "office")
    zip_tree(SERIAL, tmp_path / "project" / "cfd" / "11111111-aaaa.zip", {"NAME": "case-1"})

    first = ids(tmp_path)
    assert set(first) == {"office", "11111111-aaaa"}
    assert ids(tmp_path) == first

    (tmp_path / "runs" / "office").rename(tmp_path / "runs" / "office-2")
    moved = ids(tmp_path)
    assert moved["11111111-aaaa"] == first["11111111-aaaa"]
    assert moved["office-2"] != first["office"]
