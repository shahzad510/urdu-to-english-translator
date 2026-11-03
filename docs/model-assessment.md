# Offline Urdu-to-English model assessment

The active engine is now Gemma 4 E4B, official Q4_0 GGUF, CPU only, 8192 tokens of context. See `docs/gemma.md`. OPUS-MT and IndicTrans2 remain on disk and are not selected. This file keeps the earlier comparison. It does not say that Gemma is more accurate: the weights have not been run.

This note was written before a backend was connected. It compares models that can run on this machine, then records the one selected at that time.

The app translates line by line, keeps speaker labels outside the model, and copies lines that contain no Urdu. The model only sees utterance text. Conversation transcripts mix colloquial Urdu, names, numbers, and short English tokens such as `N/H`.

## Quality considerations for Urdu

Urdu is written in a Perso-Arabic script, right to left, and is morphologically rich. Conversation adds further difficulty:

- Greetings and short turns (`السلام علیکم`, `ٹھیک ہے`) are common and should stay natural in English.
- The same word can be formal or colloquial. A model trained mostly on general parallel text will miss local usage.
- Speakers mix English tokens, frequencies, and abbreviations into Urdu sentences. Those tokens should be copied, not translated.
- Person names and place names are often transliterated inconsistently.
- A single BLEU score on a news or Tatoeba test set does not measure this transcript style.

A terminology file is therefore part of the backend. It forces preferred English for listed Urdu phrases and does not require retraining.

## Models considered

| Model | Licence and commercial use | Size | RAM, roughly | CPU / GPU | Why it was or was not selected |
| --- | --- | --- | --- | --- | --- |
| Helsinki-NLP OPUS-MT `urd-eng` (2020-06-17) | Upstream OPUS-MT release is CC-BY 4.0. Commercial use is allowed when attribution is kept. Some copies are also tagged Apache-2.0; both allow commercial use. | About 77 million parameters, about 300 MB of weights | About 1–2 GB including the runtime | Comfortable on CPU. A few utterances per second on a desktop CPU with beam size 2. A CUDA GPU is optional and faster. | Selected. Dedicated Urdu-to-English pair, small enough for a Windows desktop, standard Marian loader, no remote code. |
| AI4Bharat IndicTrans2 Indic-to-English distilled 200M | MIT. Commercial use is allowed. Model checkpoints are MIT; some training corpora use CC-BY 4.0 or CC0. | About 200–275 million parameters, about 0.8–1 GB of weights | About 2–4 GB | Usable on CPU, slower than OPUS-MT. Authors recommend a GPU. Needs the IndicTrans preprocessor and trusted local model code. | Not selected for this version. Stronger on Indic benchmarks, including conversational sets, but heavier to install and ship. |
| AI4Bharat IndicTrans2 1B | MIT | About 4.5 GB of weights | About 6 GB or more | Poor fit for a CPU-only desktop | Rejected for size. |
| Meta NLLB-200 distilled 600M and larger | CC-BY-NC 4.0. Non-commercial research use only. Meta describes it as not released for production. | About 2.5 GB for the 600M checkpoint; multi-GB for 1.3B and above | About 4 GB and up | CPU is possible for 600M but slow | Rejected because the licence does not allow commercial or general production use. |
| Google MADLAD-400 3B MT | Apache-2.0. Commercial use is allowed. | About 3 billion parameters. Full weights about 12 GB; 4-bit builds are smaller. | About 8 GB or more for a practical build | CPU is possible only with a quantized build and is still slow | Rejected as the default. Too large for the Windows CPU target. Urdu is one of 400 languages, not a dedicated pair. |

Published OPUS-MT score for this Urdu-English checkpoint: BLEU 23.2 and chrF 0.435 on Tatoeba-test. That is usable general-domain quality, not certified translation. IndicTrans2 is the stronger open model for scheduled Indian languages, including Urdu, and remains a possible later backend under its MIT licence.

## Dual-mode decision

The application now has two modes. The GUI does not name either model. Each model folder sets `"role"` to `literal` or `contextual`.

| Question | OPUS-MT urd-eng | NLLB-200 distilled 600M | MADLAD-400 3B MT | IndicTrans2 indic-en distilled 200M |
| --- | --- | --- | --- | --- |
| Urdu quality | Dedicated Urdu-English bitext. BLEU 23.2 on Tatoeba Urdu-English. Closer to the source, weaker on colloquial wording. | Strong multilingual model. A 2024 English-to-Urdu study found it ahead of OPUS-MT on most sets and slightly ahead of IndicTrans2 on TED. That study is not a Urdu-to-English score. | 400-language T5 model. Competitive in the paper with much larger systems. Urdu is one language among hundreds, not a dedicated pair. | Built for the 22 scheduled Indian languages, including Urdu. The same English-to-Urdu study found it ahead of OPUS-MT and ahead of NLLB on four of five sets. MIT release, commercial use allowed. |
| Context | One sentence. No document context. | Model card: single-sentence research model, not for document translation. | Target tag `<2en>` plus a longer input, so a previous sentence can be included. | Sentence model. A short previous turn can be included and split back out. |
| Size on disk | About 300 MB | About 2.5 GB for the 600M checkpoint. 1.3B and 3.3B are larger. | **11.8 GB** float32 `model.safetensors`. Q4 GGUF builds are about 1.7 GB but are not the transformers checkpoint this app loads. | About 1 GB for the distilled 200–275M checkpoint. The 1B teacher is about 4.5 GB. |
| RAM | About 1–2 GB | About 4 GB and up | About **12–16 GB** to load the float32 weights on CPU. Float16 is about 5 GB of GPU memory before overhead. | About 3–4 GB with the runtime |
| CPU / GPU | Comfortable on CPU. CUDA optional. | CPU is possible and slow. CUDA optional. | CPU decoding with a 256k vocabulary is too slow for a long transcript. GPU wants a card that can hold the weights. | Usable on CPU, slower than OPUS-MT. CUDA optional. |
| Licence | CC-BY 4.0. Commercial use with attribution. | **CC-BY-NC 4.0.** Non-commercial research only. The model card says it is not released for production. | Apache-2.0. Commercial use allowed. The card says it was not assessed for production. | MIT. Commercial use allowed with the copyright notice. |

NLLB-200 is not used. The licence does not allow this desktop application, and the model card excludes production and document translation. That is independent of its size.

MADLAD-400 3B is not downloaded. Apache-2.0 would allow it, and its longer input is relevant to contextual translation, so size is not the only reason. The published transformers file is 11.8 GB of float32 weights and needs about 12–16 GB of RAM on CPU. The 256k vocabulary makes long transcripts impractical on a Windows CPU, Urdu is not a dedicated pair, and the card says the model was not assessed for production. Those weights are not copied into `models/`.

Literal mode stays on the existing OPUS-MT Marian backend. It is not removed.

Contextual mode is wired to IndicTrans2 indic-to-English distilled 200M (`indictrans2` backend, `"role": "contextual"`). Proposed install, which has **not** been downloaded:

- Model: AI4Bharat IndicTrans2 indic-en distilled 200M
- Licence: MIT, commercial use allowed if `models/indictrans2-indic-en/NOTICE.txt` stays with the weights
- Disk: about 1 GB of weights, plus the existing 300 MB OPUS-MT files
- RAM: about 3–4 GB once loaded, on top of the normal application
- CPU: supported. GPU: optional CUDA, same `device` setting as OPUS-MT

Until those weights and IndicTransToolkit are present, contextual English uses the OPUS-MT model. Short replies (up to eight words) are translated again with the previous Urdu line, and the last English sentence is kept only when that combined output splits cleanly. The status line says when this fallback is active. The application still does not download anything.

## Selected models

Literal: OPUS-MT Urdu to English, Marian checkpoint `urd-eng`, trained 2020-06-17. Attribution: University of Helsinki / Helsinki-NLP, OPUS-MT, Tatoeba Challenge Urdu-English model, licence CC-BY 4.0.

Contextual, when installed: IndicTrans2 distilled indic-en, AI4Bharat, MIT. Copy it with `python scripts/fetch_indictrans2.py` on a machine that is online, then install IndicTransToolkit in the same environment. Do not point the application at a hub id.

## Runtime expectations

- Device selection is `auto`, `cpu`, or `cuda`. `auto` uses a CUDA GPU when one is present and otherwise stays on CPU.
- CPU is the supported path for Windows 10 and 11 machines without an NVIDIA GPU.
- GPU acceleration is optional. It needs an NVIDIA driver and a PyTorch build with CUDA. The application does not download that build.
- Beam size defaults to 2 so a long transcript stays practical on CPU. It can be raised in the model folder’s `engine.json`.
- Lines are translated in batches. The Marian engine asks for 8 lines at a time unless `batch_size` is set. The existing progress text reports each batch.
- Weights are read only from the model folder. Loader calls use local files only, and hub access is switched off before the libraries are imported.

## Windows deployment

- The GUI dependencies stay in `requirements.txt`. Translation libraries are in `requirements-translate.txt` (PyTorch, Transformers, SentencePiece). A machine that only opens the window does not need them.
- Install a CPU PyTorch wheel unless the target PC has a CUDA GPU.
- Copy the model folder next to the packaged executable, under `models/`. Do not bake multi-hundred-megabyte weights into the program file. The existing PyInstaller spec already keeps `models` beside the executable.
- Packaging PyTorch into a Windows folder needs those libraries installed on the build machine and extra hidden imports. That packaging step is still separate from this backend.
- Literal translation needs the OPUS-MT folder beside the executable. Contextual translation needs the IndicTrans2 folder and IndicTransToolkit on the build machine. Leave the IndicTrans2 folder in place without weights if it is not installed: the window keeps working and uses the literal model for the contextual panel.
- Do not ship NLLB weights. Do not ship the 11.8 GB MADLAD float32 file.
- The running application must not be given a network path or a model id. If the literal weight files are absent, startup reports that the folder is incomplete.

## What this does not claim

Neither mode certifies names, numbers, or domain wording. English lines are left unchanged. Names, places, and technical terms in `models/terminology.json` are copied through. Ordinary expressions are applied in literal mode only when the phrase is bounded, and in contextual mode only when the line is exactly that phrase, so a word is not replaced when its sense depends on the sentence. Latin tokens and numbers are copied. The English next to a code such as `N/H` can be less fluent. Times of day are unreliable: OPUS-MT can render صبح as "p.m." A person should still read both English panels before saving.
