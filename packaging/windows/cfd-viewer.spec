# PyInstaller spec of the Windows bundle: one folder, client inside
# (openspec local-desktop-viewer, design D4). Build from the checkout root:
#     uv sync --frozen --no-dev --group freeze --no-editable
#     uv run --no-sync pyinstaller --noconfirm packaging/windows/cfd-viewer.spec
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

# VTK imports its Python array overrides from compiled code, out of
# PyInstaller's sight; without them an implicit array (vtkAffineArray) exposes
# no buffer and every scene fails.
hidden = collect_submodules("vtkmodules.numpy_interface") + collect_submodules("vtkmodules.util")

a = Analysis(
    [os.path.join(SPECPATH, "launch.py")],  # noqa: F821 -- SPECPATH comes from PyInstaller
    datas=collect_data_files("equa.cfd_viewer") + copy_metadata("equa-cfd-viewer"),
    hiddenimports=hidden,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="cfd-viewer", console=True)  # noqa: F821
coll = COLLECT(exe, a.binaries, a.datas, name="cfd-viewer")  # noqa: F821
