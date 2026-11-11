# Urdu → English Translator

Offline desktop translator for Urdu conversation transcripts. It runs entirely on this computer: translation and summaries talk only to a local process on `127.0.0.1`. Nothing is sent to a website.

The window has three panels:

- **Urdu Text** — right to left
- **English Translation** — editable translation of the conversation
- **Gist / Contextual Summary** — a read-only summary written after the English text is complete

Speaker labels, blank lines, and lines that are already English stay as they are. You can Open documents, Translate, Clear, Copy, Save TXT, Export DOCX, Export Complete Document, and use History. History is a local SQLite file.

Gemma 4 E4B is the only active translation engine. The Gemma model file is **not** part of the Windows installer.

Exact model filename:

`gemma-4-E4B_q4_0-it.gguf`

---

## Windows end users (Windows 10 / 11 x64)

### Requirements

- Windows 10 or Windows 11, 64-bit
- About 5 GB free disk space for a local copy of the model (optional if you keep the file on USB)
- Several GB of free RAM while translating (the model weights alone are about 4.5–4.9 GB)
- No internet connection is required to install or use the application

### Install from the Windows installer

1. Copy `UrduTranslator-Setup-1.0.0-x64.exe` to the computer on a USB drive.
2. Run the installer.
3. Accept the folder under Program Files, or choose another folder.
4. Optionally create a desktop shortcut.
5. Finish. Windows is not asked to download Python, a runtime, or a model.

The Start menu will contain **Urdu Translator**. The installer does **not** contain `gemma-4-E4B_q4_0-it.gguf`.

### First launch

1. Start **Urdu Translator**.
2. A **Gemma Model Installation** help screen explains that the model arrives separately on USB. You can open the recommended model folder from that screen, choose **Don't show this again**, then **Get Started** or **Close**.
3. If the model is not configured yet, **Gemma AI Model Setup** opens so you can browse to the GGUF file and verify it.
4. You can reopen the instructions later from **Help → Gemma Model Installation**.

### Install the Gemma model from USB

On a computer that is allowed to obtain the file:

1. Obtain `gemma-4-E4B_q4_0-it.gguf`.
2. Copy it onto a USB drive. Keep the `.gguf` ending.

On the offline computer:

1. Plug in the USB drive and start **Urdu Translator**.
2. In **Gemma AI Model Setup**, click **Browse for Model** and select `gemma-4-E4B_q4_0-it.gguf`.
3. Choose one option:
   - **Keep model at its current location** if the USB drive will stay connected while you translate.
   - **Copy model to the recommended local model directory** for a copy on this computer.
4. Click **Verify Model**. Nothing is downloaded.
5. When the status says **AI Model Ready — Offline Mode**, you can translate.

Recommended folder after a local copy:

`%LOCALAPPDATA%\UrduTranslator\Models\`

Example:

`C:\Users\Admin\AppData\Local\UrduTranslator\Models\gemma-4-E4B_q4_0-it.gguf`

The application remembers the chosen path in `%LOCALAPPDATA%\UrduTranslator\Configuration\model.json`. It does not download, rename, move, or delete the model unless you ask it to copy into that folder.

### Offline operation

Translation and summaries start a local `llama-server` process that listens on `127.0.0.1` only. History, configuration, logs, and an optional local model copy stay under `%LOCALAPPDATA%\UrduTranslator\`.

### Replace or update the model

1. Copy the new `gemma-4-E4B_q4_0-it.gguf` onto this computer or a USB drive.
2. Open **Help → Gemma Model Installation**, or click the model status pill when the model is unavailable.
3. Browse to the new file and click **Verify Model**.
4. The previous path is replaced in configuration. Files you did not ask to overwrite are left alone.

### Troubleshooting

| Problem | What to try |
| --- | --- |
| Setup says the file is unavailable | Reconnect the USB drive, or browse to another copy of `gemma-4-E4B_q4_0-it.gguf`. |
| File is empty or not a GGUF | Copy the model again. Do not use a shortcut or a partial download. |
| llama-server cannot start | Reinstall from an installer that includes `llama-server.exe` and its DLLs. Do not download those on the offline PC. |
| Port 8080 is already in use | Another program is listening there. Urdu Translator leaves it running. Close the other program, then try again. A previous Urdu Translator `llama-server` for the **same** model file is reused. |
| Uninstall | Removing the app deletes the Program Files copy only. History and a copied model under `%LOCALAPPDATA%\UrduTranslator\` remain until you delete that folder yourself. |

More detail for offline PCs: `packaging/windows/OFFLINE_INSTALLATION_GUIDE.md`.

---

## Features (all platforms)

- Offline Urdu → English translation with a local Gemma 4 E4B GGUF
- Contextual summary (Brief / Detailed / Expanded) using the same local server
- RTL Urdu editing, LTR English editing
- Open TXT/DOCX, save TXT/DOCX, export a complete document
- Local translation history
- Terminology hints from `models/terminology.json` when present

---

## Developers

### Run on Linux

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py
```

`requirements.txt` opens the window. Gemma does not add a Python package. The GGUF and `llama-server` stay outside the project at the paths in `models/gemma-4-e4b/engine.json` on Linux. Translation talks only to `127.0.0.1`.

Tests:

```bash
.venv/bin/python -m pytest -q
```

On Windows (PowerShell), from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

### Models

| Role | Model | Licence | Notes |
| --- | --- | --- | --- |
| Active | Google Gemma 4 E4B, official Q4_0 GGUF | Apache 2.0 on the Gemma 4 model card | Windows: path chosen in setup, usually under `%LOCALAPPDATA%\UrduTranslator\Models\`. Linux: paths in `models/gemma-4-e4b/engine.json`. |
| Unused | Helsinki-NLP OPUS-MT urd-eng | CC-BY 4.0 | Left on disk. Not selected by the app. |
| Unused | AI4Bharat IndicTrans2 indic-en | MIT | Left on disk. Not selected by the app. |

Read `docs/gemma.md` before copying weights. Checking configuration does not download anything:

```bash
python scripts/fetch_gemma.py
```

### Windows build

Build documentation: `packaging/windows/README.md`.

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build_windows.ps1
```

The build uses the project virtual environment at `.venv\Scripts\python.exe`, packs `llama-server.exe` from `packaging\windows\runtime`, embeds `packaging\windows\assets\UrduTranslator.ico` (generated from root `icon.png`), and refuses to include any `.gguf` file. Inno Setup produces `UrduTranslator-Setup-1.0.0-x64.exe` when `ISCC` is available.

Application version and installer version are **1.0.0**.

### Editors and terminology

The Urdu panel is right to left and the English panel is left to right. The gist section is read only. Copy / Save / Export for translation apply only to English; the matching gist actions apply only to the summary. `models/terminology.json` is listed in the Gemma prompt when present.
