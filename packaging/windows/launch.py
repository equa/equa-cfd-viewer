"""Entry script of the frozen Windows bundle (``cfd-viewer.spec``).

A double-click passes no arguments, so the bundle starts in local mode; a
folder dropped onto the .exe arrives as an argument (openspec
local-desktop-viewer, D1 and D4).
"""

import sys

from equa.cfd_viewer.__main__ import main

if __name__ == "__main__":
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetConsoleTitleW("CFD Viewer - close this window to stop")
    sys.exit(main(default_mode="local"))
