"""Keep every test's case cache out of the developer's own (ice-project-zips)."""

import pytest


@pytest.fixture(autouse=True)
def _private_cache(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("xdg-cache")))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path_factory.mktemp("localappdata")))
