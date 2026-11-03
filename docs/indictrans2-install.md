# IndicTrans2 installation

The desktop application does not download IndicTrans2, and it no longer loads this folder. Gemma is the only active engine. Keep this folder on disk as an unused rollback copy. The notes below describe the earlier install check.

## What is already in the tree

`models/indictrans2-indic-en/` contains:

- `engine.json` with `"backend": "indictrans2"` and `"role": "contextual"`
- `NOTICE.txt` for the MIT licence

Weight files are not included. The backend reads only that folder, with local files only, and turns hub access off before the libraries are imported. `trust_remote_code` is enabled because the checkpoint may include its own local loader. Copy the official weights only. Do not point the application at a model id.

## Check without downloading

From the project root:

```bash
python scripts/fetch_indictrans2.py
```

That command prints the folder, the MIT licence, the missing weight names, and whether PyTorch, Transformers, SentencePiece, and IndicTransToolkit are installed. It does not contact the network.

## Optional copy of the weights

Do this once, on a machine that is online, after you accept the model terms on the hub if that repository asks for them.

- Model: `ai4bharat/indictrans2-indic-en-dist-200M`
- Licence: MIT. Commercial use is allowed when `NOTICE.txt` stays with the weights.
- Disk: about 1 GB
- RAM: about 3–4 GB after it loads
- Device: `auto`, `cpu`, or `cuda` in `engine.json`. CPU is supported. A CUDA GPU is optional and is not downloaded by this project.

```bash
.venv/bin/pip install -r requirements.txt -r requirements-translate.txt -r requirements-contextual.txt
.venv/bin/python scripts/fetch_indictrans2.py --download
```

`--download` is required. A plain run of the script does not copy the model.

Then start the application. The model pill stays on the literal OPUS-MT name. Its details should say that contextual English uses IndicTrans2. If the toolkit or a weight file is missing, the message says what is missing and contextual English stays on OPUS-MT.

## Windows

Use the same folder beside the executable: `models/indictrans2-indic-en/`. Install `requirements-translate.txt` and `requirements-contextual.txt` on the build machine before packaging. Leave the folder without weights if IndicTrans2 is not part of that build. Do not pack the weights into the program file.

NLLB-200 is CC-BY-NC and is not an acceptable substitute. MADLAD-400 3B is about 11.8 GB of float32 weights and is not the model this folder expects.
