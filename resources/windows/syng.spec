a = Analysis(
    ["syng/main.py"],
    pathex=[],
    binaries=[("deno.exe", "."), ("libmpv-2.dll", "."), ("ffmpeg.exe", ".")],
    datas=[
        (
            "syng.ico",
            ".",
            ("background.mp3", "static"),
            ("background.png", "static", ("background20perc.png", "static")),
        )
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="main",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['syng.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="syng",
)
