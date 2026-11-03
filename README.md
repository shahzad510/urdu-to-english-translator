# Urdu → English

Offline desktop translator for Urdu conversation transcripts. It runs on Ubuntu with Python 3 and is laid out so a later Windows build can ship the same folder.

The window has two panels:

- Urdu, right to left
- English, the translation of the conversation

Gemma 4 E4B is the only active translation engine. The older OPUS-MT and IndicTrans2 folders stay on disk and are not used. If the Gemma weight file is missing, translation stops. It does not switch to another model.

Speaker labels, blank lines, and lines that are already English stay as they are. Translate, Clear, Copy, Save TXT, Export DOCX, Open, and History are unchanged in role. History is a local SQLite file. New translations are stored in `translated_text`. Older rows that also have a contextual copy stay readable in the one English panel.

## Run on Linux

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py
```

`requirements.txt` opens the window. Gemma does not add a Python package. `requirements-gemma.txt` records that the GGUF and the `llama-server` binary stay outside this project, at the paths in `models/gemma-4-e4b/engine.json`. The application does not install packages. Translation talks only to `127.0.0.1`.

Tests:

```bash
.venv/bin/python -m pytest -q
```

The live OPUS-MT test still loads that folder directly when `models/opus-mt-ur-en/pytorch_model.bin` is present. The application itself does not select it.

## Models

Gemma is the active engine. Read `docs/gemma.md` before copying its weights. The older comparison remains in `docs/model-assessment.md`.

| Role | Model | Licence | Disk | RAM | Status |
| --- | --- | --- | --- | --- | --- |
| Active | Google Gemma 4 E4B, official Q4_0 GGUF | Apache 2.0 on the Gemma 4 model card. Keep the official notices. | About 4.5 GB for the weights, on the external drive | More than 4.5 GB once the runtime and 8192-token cache are included. Not measured here. | `engine.json` points at the external GGUF and llama-server. The server starts on the first translation. |
| Unused | Helsinki-NLP OPUS-MT urd-eng | CC-BY 4.0 | About 300 MB | About 1–2 GB | Left on disk. Not selected. |
| Unused | AI4Bharat IndicTrans2 indic-en distilled 200M | MIT | About 1 GB | About 3–4 GB | Left on disk. Weights were not installed. Not selected. |

### Install Gemma

The running app uses the external files named in `models/gemma-4-e4b/engine.json`. It starts `llama-server` on `127.0.0.1:8080` at the first translation, with context 8192, 4 CPU threads, and reasoning off. Closing the window stops that process. If the drive is unplugged, the model pill names `gemma-4-E4B_q4_0-it.gguf` and translation does not start. See `docs/gemma.md`.

Checking the configuration does not download anything and does not start the server:

```bash
python scripts/fetch_gemma.py
```

The folders below are unused rollback copies. Do not delete them. The application does not load them while `models/gemma-4-e4b/engine.json` is present.

Gemma starts on CPU. Its context length is set in `models/gemma-4-e4b/engine.json` and begins at 8192.

### Install OPUS-MT

The literal weights are local files in `models/opus-mt-ur-en/`. To copy them once while online:

```bash
.venv/bin/python scripts/fetch_opus_mt.py
```

Keep `NOTICE.txt` with the weights.

### Install the contextual model

Checking the folder does not download anything:

```bash
python scripts/fetch_indictrans2.py
```

The copy is optional. It is about 1 GB, MIT licensed, and needs about 3–4 GB of RAM. See `docs/indictrans2-install.md`.

```bash
.venv/bin/pip install -r requirements-contextual.txt
.venv/bin/python scripts/fetch_indictrans2.py --download
```

Leave both unused folders as they are. The application does not load them.

Do not download NLLB. Do not download the 11.8 GB MADLAD float32 weights for this application.

## Terminology

`models/terminology.json` is listed in the Gemma prompt. A model folder may also contain its own file. Each entry has a source, a target, and a kind: `name`, `place`, `technical`, `expression`, or `user`. Gemma is asked to use those wordings. The older Marian and IndicTrans2 code, which is not selected by the window, still applies the same file when that code is loaded directly.

## Compare translations

`evaluation/datasets/conversations.json` holds invented Urdu, reference English, empty output fields, and human notes. The runner records Gemma output and time when the weights can be loaded. OPUS-MT and IndicTrans2 are reported as not run, and their columns are not filled from Gemma.

```bash
python scripts/evaluate_translations.py
```

The report is written to `evaluation/results/comparison.md`. It does not claim an accuracy improvement.

## Text colours

The Urdu and English panels each have a Colour button. The appearance dialog still stores a third colour slot from the earlier layout. Text and background are chosen in that dialog, a readable draft is shown on the window while it is open, and a pair below 4.5:1 contrast cannot be saved. Reset to default restores white backgrounds (`#FFFFFF`) and `#202020` text. Borders stay `#D0D0D0`, buttons `#34495E`, and the accent `#C9A45C`.

The choice is stored with Qt settings: the registry on Windows, and a config file on Ubuntu. Restarting the application keeps it. Urdu remains right to left.

## Windows

The GUI dependencies stay in `requirements.txt`. Build with PyInstaller from `packaging/urdu_translator.spec` on Windows after those packages are installed. The GGUF and `llama-server` stay outside the program file. `models/gemma-4-e4b/engine.json` holds their absolute paths.

Copy `models/gemma-4-e4b/engine.json` and `NOTICE.txt` beside the executable. Leave the weight file on its drive. The OPUS-MT and IndicTrans2 folders may stay beside the app. They are not loaded.
