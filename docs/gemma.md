# Gemma 4 E4B

Gemma is the only translation engine the application loads. It translates through a local llama.cpp server. The window does not download the model, and a missing weight file does not switch to OPUS-MT or IndicTrans2.

## External files

`models/gemma-4-e4b/engine.json` names both files with absolute paths:

- Binary: the `llama-server` built under the Gemma `llama.cpp` directory
- Model: `gemma-4-E4B_q4_0-it.gguf`

Those files stay on their drive. They are not copied into this project and they are not packed into the program. No Python HTTP library is required. `requirements-gemma.txt` does not install `llama-cpp-python`; that in-process loader is no longer used.

Licence: the Gemma 4 model card identifies Apache 2.0. Keep the official licence and notices that came with the checkpoint beside the GGUF. Read https://ai.google.dev/gemma/docs/gemma_4_license before commercial use.

The Q4_0 weights are about 4.5 GB. Loading them also needs RAM for the runtime and the context cache. That extra use has not been measured. The context length stays at 8192 tokens until it is measured.

## How the server runs

The window opens without starting the server. The first translation starts:

```text
llama-server -m MODEL -c 8192 -t 4 --reasoning off --host 127.0.0.1 --port 8080
```

The process is reused for later translations. The app waits until `GET /health` succeeds, then posts to `/v1/chat/completions`. It reads `choices[0].message.content`, drops `reasoning_content`, and removes any `<think>` span. Closing the window sends SIGTERM to the child this app started, then SIGKILL if that same child is still running. A server the app did not start is left alone. Cancelling a translation closes the current request and does not reload the model.

If port 8080 is already taken by this same binary and model, the app reuses it. If another program has the port, translation stops and that program is not killed.

## Missing drive

If the drive is unplugged, the model pill and the translation error name `gemma-4-E4B_q4_0-it.gguf` and say the external drive or model file is unavailable. Connect the drive and translate again. Nothing is downloaded.

Check the paths without starting the server:

```bash
python scripts/fetch_gemma.py
```

## Optional live test

The ordinary test suite does not launch `llama-server` or read the GGUF. To translate one invented Urdu line through the real server:

```bash
URDU_TRANSLATOR_LIVE_GEMMA=1 .venv/bin/python -m pytest -q tests/test_llama_server.py::test_live_gemma_translates_one_synthetic_line
```

That test stops the server child it started. It does not score the English.

## What the translation does

Urdu lines that belong to the same paragraph are translated together. A long paragraph is split so the source chunk stays within the 8192-token context, and the previous lines stay in the prompt so they are not translated twice. The model is asked to return one line per source line, keep speaker labels, and leave English words, abbreviations, codes, numbers, and identifiers unchanged.

If the reply does not have the same number of lines, the application reports an error and does not rebuild the document. Speaker labels from the source are put back when the model drops them. Lines with no Urdu are copied. Terms in `models/terminology.json` are listed in the prompt.

No accuracy figure is claimed.
