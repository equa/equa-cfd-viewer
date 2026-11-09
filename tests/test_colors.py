from pathlib import Path

from equa.cfd_viewer.foamviz import colors

STATE_JS = Path(__file__).parents[1] / "web/src/scene/state.js"


def test_web_default_preset_matches_server():
    assert f"preset: '{colors.DEFAULT_PRESET}'" in STATE_JS.read_text()


def test_every_preset_is_labelled():
    assert list(colors.PRESET_LABELS) == colors.PRESET_NAMES
