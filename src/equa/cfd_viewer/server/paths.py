"""Per-user directories, shared by local mode and the case cache."""

import os
from pathlib import Path


def user_dir(windows_var, xdg_var, xdg_default):
    """``%<windows_var>%`` on Windows, else ``$<xdg_var>`` or ``~/<xdg_default>``,
    then ``equa/cfd-viewer``. Raises RuntimeError when neither the variable nor a
    home directory can be found."""
    base = os.environ.get(windows_var) if os.name == "nt" else None
    if not base:
        base = os.environ.get(xdg_var) or str(Path.home() / xdg_default)
    return Path(base) / "equa" / "cfd-viewer"
