# Models Manifest (External Resources)

**Maintained by:** Member 3 — External Resources
**Purpose:** This file documents every ML model / external resource the
assistant depends on, where it lives, and how it is managed. It is the
single source of truth for "what models do we use and where did they come
from". Member 3 owns downloading, versioning, and swapping these.

---

## 1. Speech-to-Text (STT) — Whisper

- **Engine:** `faster-whisper` (a faster re-implementation of OpenAI Whisper)
- **Model size:** `small` (≈460 MB download on first run)
- **Languages:** Hindi + English (auto-detected; works well for Hinglish)
- **Compute:** CPU, `int8` (8-bit) — about half the RAM, runs offline
- **Where it lives:** downloaded automatically into the HuggingFace cache
  (`~/.cache/huggingface/`) on first use; no file is committed to the repo
- **Loaded by:** `jarvis/stt.py`
- **Managed by:** Member 3 (chooses model size, triggers download, documents
  upgrade path to `medium`/`large-v3` for better Hindi)

## 2. Text-to-Speech (TTS) — Piper

- **Engine:** `piper-tts` (a VITS neural TTS)
- **Voice:** `hi_IN-pratham-medium` (Hindi male speaker; OK on English too)
- **Model files (committed, see .gitignore exception):**
  - `models/tts/hi_IN-pratham-medium.onnx`
  - `models/tts/hi_IN-pratham-medium.onnx.json`
- **Sample rate:** 22050 Hz, mono
- **Runs:** fully offline once the `.onnx` is on disk
- **Loaded by:** `jarvis/tts.py`
- **Managed by:** Member 3 (picks/adds voices; to switch to pure-English
  use `en_US-lessac-medium`)

## 3. LLM Brain (cloud)

- **Engine:** OpenRouter Chat Completions API (OpenAI-compatible)
- **Default model:** `openai/gpt-4o-mini` (swappable — see `jarvis/brain.py`)
- **Requires:** internet + an API key in `.env` (`OPENROUTER_API_KEY`)
- **Integrated by:** `jarvis/brain.py` (Member 2's module)
- **Managed by:** Member 3 tracks which model is active and its limits/cost

## How to add a new resource

1. Download / note the source URL and license.
2. Add an entry to this file with size, purpose, and owner.
3. If it is a binary model, place it under `models/` and allow-list it in
   `.gitignore` (large files are NOT committed by default).
4. Update `requirements.txt` if a new Python package is needed.
