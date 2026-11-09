# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir spec for the offline Windows build.

The GGUF model is not a data file. llama-server.exe and its DLLs are taken
from packaging/windows/runtime when that folder has been filled in on the
build machine. This spec does not download anything.
"""

from pathlib import Path

root = Path(SPECPATH).resolve().parents[1]
runtime = Path(SPECPATH) / "runtime"
template = Path(SPECPATH) / "engine.template.json"
notice = root / "models" / "gemma-4-e4b" / "NOTICE.txt"

datas = [
    (str(template), "models/gemma-4-e4b"),
]
if notice.is_file():
    datas.append((str(notice), "models/gemma-4-e4b"))
fonts = root / "urdu_translator" / "resources"
if fonts.is_dir():
    datas.append((str(fonts), "urdu_translator/resources"))

binaries = []
if runtime.is_dir():
    for path in sorted(runtime.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".gguf":
            raise SystemExit("Refusing to bundle a GGUF model into the application.")
        if path.suffix.lower() in {".exe", ".dll"}:
            binaries.append((str(path), "."))

hidden = [
    "urdu_translator.translation.backends",
    "urdu_translator.translation.backends.gemma",
    "urdu_translator.translation.backends.marian",
    "urdu_translator.translation.backends.indictrans2",
    "urdu_translator.gui.model_setup_dialog",
    "urdu_translator.gui.flow_layout",
]

a = Analysis(
    [str(root / "run.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "transformers", "llama_cpp"],
    noarchive=False,
)
pyz = PYZ(a.pure)

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
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="UrduTranslator",
)
