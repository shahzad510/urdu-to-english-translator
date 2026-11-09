# Windows build

This folder describes how to produce `UrduTranslator-Setup-1.0.0-x64.exe` on a **Windows 10 or Windows 11 x64 computer that has internet**, or on a Windows computer that already has the tools copied onto it.

The computer where the translator will be **used** does not need any of these tools and does not need internet. See `OFFLINE_INSTALLATION_GUIDE.md` for that computer.

The Gemma file `gemma-4-E4B_q4_0-it.gguf` (about 4.9 GB) is **not** part of the installer and must not be committed or copied into `runtime`, `dist`, or `output`.

Nothing in this repository has produced that installer yet. A Windows build has to be run on Windows before the installer exists.

## Build machine

- Windows 10 or later, 64-bit.
- Python 3.11 or 3.12, 64-bit, already installed. The build script does not download Python.
- These packages already installed in that Python, from a local wheelhouse if the build machine itself is offline:
  - PySide6 (the same major line as `requirements.txt`, 6.6 up to but not including 6.11)
  - python-docx
  - PyInstaller 6
- Inno Setup 6, if you want the script to compile the installer. If `ISCC` is not on `PATH`, the script still leaves the application folder and tells you the installer was not built.
- A **Windows x64 CPU** build of `llama-server.exe` and every DLL that build needs. Do not copy the Linux `llama-server` binary. Do not choose a CUDA build unless you also intend to require an NVIDIA driver; the supported build for this installer is CPU-only.

PyTorch is not required. Translation goes through the bundled `llama-server.exe`.

## llama-server

On a computer that may download files, build or obtain a CPU-only Windows x64 `llama-server` from the llama.cpp project (CMake, Visual Studio Build Tools, or a published CPU zip built for x64). Copy into `packaging/windows/runtime/`:

- `llama-server.exe`
- every DLL next to that executable, including `llama.dll`, `ggml*.dll`, and any `vcruntime` / `msvcp` DLLs that the build does not already find in the Windows system directory

Those DLLs are the app-local runtime. The target computer is not asked to install a Visual C++ redistributable separately, and this script will not download one. Confirm the licence of the llama.cpp build and of any Microsoft runtime libraries you copy before you redistribute them.

Do not commit `runtime\`, `*.exe`, or `*.dll`.

Check the binary on the build machine, with the network disconnected if you want to be sure it does not phone home:

```text
runtime\llama-server.exe --help
```

It must print its help without trying to download a model.

## Build

From PowerShell, in this repository:

```text
powershell -ExecutionPolicy Bypass -File packaging\windows\build_windows.ps1
```

The script:

1. Checks that Windows is 64-bit and that Python 3.11 or 3.12 x64 is already available.
2. Checks that PySide6, python-docx, and PyInstaller are already importable. It does not run pip.
3. Stops if `runtime\llama-server.exe` is missing, if a Linux binary was left there, or if any `.gguf` file is in `runtime`.
4. Runs PyInstaller with `UrduTranslator.spec` (onedir, windowed, name `UrduTranslator.exe`).
5. Refuses the result if `UrduTranslator.exe` or `llama-server.exe` is missing, or if a `.gguf` file was packed.
6. Runs `ISCC` on `installer.iss` only when Inno Setup is already installed.

Outputs:

- `packaging\windows\dist\UrduTranslator\` — the application directory
- `packaging\windows\output\UrduTranslator-Setup-1.0.0-x64.exe` — only after Inno Setup has actually compiled it

`engine.template.json` is the Windows `engine.json`. It has no Linux paths. The model path is chosen in the application and stored under `%LOCALAPPDATA%\UrduTranslator\Configuration\`. The Ubuntu `models/gemma-4-e4b/engine.json` is left unchanged so the Linux install keeps its external paths.

## What the installer contains

- The Python runtime collected by PyInstaller
- PySide6, Qt platform plugins, and the Qt DLLs PyInstaller collects
- python-docx and the standard-library `sqlite3` module
- `llama-server.exe` and the DLLs you placed in `runtime`
- The Gemma `engine.json` template and its NOTICE file

It does not contain the GGUF weights.

## Installer behaviour

- Installs under Program Files (`{autopf}\Urdu Translator`)
- Start Menu shortcut
- Optional desktop shortcut
- Uninstaller
- Does not delete `%LOCALAPPDATA%\UrduTranslator\` (history, configuration, logs, a copied model)
- Does not need a network connection

## After you have an installer

Install it on a clean Windows 10 x64 virtual machine with the network adapter disabled. Confirm:

- Setup finishes without asking Windows to download a runtime
- `UrduTranslator.exe` opens
- The Gemma setup dialog appears because the model is absent
- Translation stays unavailable until a real `.gguf` file is selected
- With the model present, llama-server listens on `127.0.0.1` only
- Minimize, maximize, restore, and mouse resizing still work
- Urdu is right to left, English is left to right
- History, TXT, and DOCX still work

Until that run has been done, do not describe the Windows package as tested.

## Troubleshooting

- **PyInstaller is missing.** Install it on the build machine from a local copy. Do not point the offline target at the internet.
- **The application opens and immediately says llama-server is unavailable.** A DLL is missing from `runtime`. On the build machine, start `llama-server.exe --help` in a clean folder until it runs, and copy every DLL it loads.
- **Port 8080 is already in use.** The application leaves the other program running and reports the conflict. It does not terminate an unrelated process.
- **The model was on a USB drive that is now unplugged.** The setup dialog says the file is unavailable and lets the user reconnect the drive or browse for another copy. It does not download a replacement.
