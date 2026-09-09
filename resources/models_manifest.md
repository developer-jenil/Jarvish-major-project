# Models Manifest (External Resources)

**Maintained by:** Member 3 — External Resources
**Purpose:** This file documents every ML model / external resource the
assistant depends on, where it lives, and how it is managed. It is the
single source of truth for "what models do we use and where did they come
from". Member 3 owns downloading, versioning, and swapping these.

---

## 1. Speech-to-Text (STT) — Dual Engine (Groq Cloud + Local Whisper)

- **Primary Engine (Ultra-Fast):** Groq Cloud Whisper API (`whisper-large-v3-turbo`)
  - **Latency:** ~0.2s on Groq LPUs
  - **Size:** 0 MB local disk / RAM; runs large-v3 architecture on cloud
  - **Requires:** `GROQ_API_KEY` in `.env` (free at console.groq.com)
- **Local Fallback Engine (Offline):** `faster-whisper` (CTranslate2)
  - **Model size:** `small` (≈460 MB pre-cached in `~/.cache/huggingface/`)
  - **Compute:** CPU, `int8` (8-bit)
  - **Languages:** Hindi + English (auto-detected; works well for Hinglish)
- **Loaded by:** `jarvis/stt.py`
- **Managed by:** Member 3

## 2. Text-to-Speech (TTS) — Piper + Edge-TTS

- **Engine:** `edge-tts` (natural neural voices) + `piper-tts` (local VITS offline fallback)
- **Voice:** `hi-IN-MadhurNeural` (Edge) / `hi_IN-pratham-medium` (Piper)
- **Model files (Piper):**
  - `models/tts/hi_IN-pratham-medium.onnx`
  - `models/tts/hi_IN-pratham-medium.onnx.json`
- **Sample rate:** 22050 Hz / 24000 Hz, mono
- **Loaded by:** `jarvis/tts.py`
- **Managed by:** Member 3

## 3. LLM Brain (cloud)

- **Engine:** OpenRouter Chat Completions API (OpenAI-compatible)
- **Default model:** `google/gemini-2.5-flash` (ultra-low latency <300ms, excellent reasoning, native Hindi/Hinglish)
- **Fallback models:** `meta-llama/llama-3.1-8b-instruct`, `openai/gpt-4o-mini`, `google/gemma-7b-it`
- **Requires:** internet + an API key in `.env` (`OPENROUTER_API_KEY`)
- **Integrated by:** `jarvis/brain.py` (Member 2's module)
- **Managed by:** Member 3 tracks active models and limits

## How to add a new resource

1. Download / note the source URL and license.
2. Add an entry to this file with size, purpose, and owner.
3. If it is a binary model, place it under `models/` and allow-list it in
   `.gitignore` (large files are NOT committed by default).
4. Update `requirements.txt` if a new Python package is needed.
