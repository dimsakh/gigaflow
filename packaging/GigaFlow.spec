# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all


datas = []
binaries = []
hiddenimports = []
for package in ("onnx_asr", "sounddevice"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

datas += [("src/gigaflow/assets", "gigaflow/assets")]

a = Analysis(
    ["src/gigaflow/__main__.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "unittest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GigaFlow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="src/gigaflow/assets/gigaflow.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="GigaFlow",
)
