"""Keep every test's case cache out of the developer's own (ice-project-zips).

Patched, not set through ``XDG_CACHE_HOME``: Playwright finds its browsers
under that variable, and the browser suite runs in a child of this process."""

import pytest

from equa.cfd_viewer.server import sources


@pytest.fixture(autouse=True)
def _private_cache(tmp_path_factory, monkeypatch):
    root = tmp_path_factory.mktemp("case-cache")
    monkeypatch.setattr(sources, "default_root", lambda: root)
