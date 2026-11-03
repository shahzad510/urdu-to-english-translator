# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the later standalone Windows build.

Run this on Windows from the project root after the dependencies are installed:

    pyinstaller packaging\\urdu_translator.spec

The build is one folder. The models directory sits beside UrduTranslator.exe
so a local model can be added without another build. This spec does not
download a model and does not bundle one. The Gemma GGUF and llama-server
binary stay outside the program, at the absolute paths in
models/gemma-4-e4b/engine.json. Do not pack either file into the program.

When the Windows build includes translation, install requirements-translate.txt
on the build machine first. PyTorch and Transformers then need to be collected
with the executable. The weight files still stay in the models folder beside
the executable. A contextual IndicTrans2 build also needs IndicTransToolkit
installed on that machine. Do not bundle the 11.8 GB MADLAD weights.
"""

from pathlib import Path

root = Path(SPECPATH).resolve().parent
block_cipher = None

a = Analysis(
    [str(root / "run.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (
            str(root / "urdu_translator" / "resources" / "fonts"),
            "urdu_translator/resources/fonts",
        ),
        (str(root / "models" / "MODEL_PACKAGE.txt"), "models"),
    ],
    hiddenimports=["urdu_translator.translation.backends"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="UrduTranslator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="UrduTranslator",
)
