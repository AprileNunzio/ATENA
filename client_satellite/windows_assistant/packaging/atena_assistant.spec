from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = Path(SPECPATH).parent
datas, binaries, hiddenimports = collect_data_files("customtkinter"), [], []
for package in ("uiautomation", "comtypes"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

analysis = Analysis(
    [str(ROOT / "atena_assistant.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tests", "pytest", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="ATENA",
    console=False,
    icon=str(ROOT / "build" / "atena.ico"),
    version=None,
)
COLLECT(exe, analysis.binaries, analysis.datas, name="ATENA")
