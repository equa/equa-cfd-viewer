"""The browser's views document and local store, run under Node.

The web app has no JavaScript test runner; ``tests/views_document_check.mjs``
asserts with ``node:assert`` and this runs it. Node is part of the build, so a
missing one fails rather than skips (openspec scenes-and-cameras, task 1.1).
"""

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_views_document():
    node = shutil.which("node")
    assert node, "node is required for this test"
    result = subprocess.run(
        [node, str(ROOT / "tests" / "views_document_check.mjs")],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "views document: ok" in result.stdout
