# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ["DECIMER", "pystow", "cairosvg", "cairocffi"]

for pkg in ("DECIMER", "cairosvg", "cairocffi", "pystow"):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    ["../main.py"],
    pathex=[".."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=["hooks/rthook_cairo.py"],
    excludes=[],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="chem4all",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="chem4all")
app = BUNDLE(
    coll,
    name="chem4all.app",
    icon=None,
    bundle_identifier="com.mpfilbin.chem4all",
    info_plist={
        "CFBundleShortVersionString": "0.1.0",
        "NSHighResolutionCapable": True,
    },
)
