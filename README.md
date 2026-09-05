# Major Project — JARVIS

A "Hey Jarvis" personal voice assistant for Windows. Wakes on a custom hotword, understands Hindi + English (Hinglish), speaks back, and can open apps, search the web, send WhatsApp messages, and send Gmail emails (with subject, To, BCC, and AI-written content).

## Status

**Phase 4 — Complete.** The voice loop, wake word, LLM brain, and all four skills run fully. The assistant also supports a system tray icon for background operation.

### What works today
- "Hey Jarvis" wake word (local, OpenWakeWord)
- Speech-to-text (faster-whisper, Hindi + English)
- LLM brain (OpenRouter cloud API — `meta-llama/llama-3.1-8b-instruct` by default)
- Text-to-speech (Piper, offline)
- **Open-any-app skill** — say e.g. *"open chrome"*, *"open notepad"*, *"open youtube and play despacito"*, *"kholo calculator"*. Runs **offline** (no API key).
- **WhatsApp skill** — say e.g. *"send whatsapp to mom saying I will be late"*. Opens WhatsApp Web with a pre-filled message.
- **Gmail email skill** — say e.g. *"send an email to prof sharma about the project update"*. Drafts and sends via SMTP (requires Google App Password).
- **Web search skill** — say e.g. *"search for weather in mumbai"*, *"google latest python news"*, *"kya hai artificial intelligence"*. Fetches top results via DuckDuckGo and speaks them back.
- **System tray mode** — set `JARVIS_TRAY=1` to minimise to tray instead of console.
- Conversation memory (last 6 turns within a session).

## Quick start (developer)

```powershell
# Activate the virtual environment (do this every time you open a new terminal)
.\venv\Scripts\Activate.ps1

# Install dependencies (Phases 1–4)
pip install -r requirements.txt

# Download the wake-word model (one-time)
python -m jarvis.wakeword --download

# Set up your .env file (copy .env.example, fill in the values)

# ===================================================
# 🚀 LAUNCH THE NEURAL WEB DASHBOARD (NO TERMINAL NEEDED)
# ===================================================
# Double-click 'run_jarvis_ui.bat' or run:
python launch_ui.py
# (Automatically opens http://localhost:5000 in your browser)

# Run full project health check & test suite verification
python build_and_verify.py

# Or run unit tests directly (31 automated tests)
python -m unittest discover -s tests

# Build distribution packages (.whl and .tar.gz)
python -m build

# Or run in classic console mode
python main.py

# Or run in system-tray mode
$env:JARVIS_TRAY="1"; python main.py
```

## Tech stack

| Component | Technology |
|---|---|
| Wake word | OpenWakeWord (local, ONNX) |
| Speech-to-text | faster-whisper (local, Hindi + English) |
| LLM brain | OpenRouter cloud API (`meta-llama/llama-3.1-8b-instruct`) |
| Text-to-speech | Piper TTS (local, Hindi male voice) |
| WhatsApp | pywhatkit → WhatsApp Web |
| Email | smtplib → Gmail SMTP (App Password auth) |
| Web search | duckduckgo-search (local DDG API, no browser) |
| System tray | pystray + Pillow |

## Phases

0. Setup  (done)
1. Voice round-trip (mic + STT + TTS)  (done)
2. "Hey Jarvis" wake word + LLM brain  (done)
3. Skills
   - **Open-any-app**  (done — offline)
   - **WhatsApp messaging**  (done — pywhatkit)
   - **Gmail email**  (done — SMTP)
4. Web search  (done — DuckDuckGo)
5. (reserved)
6. System tray + polish  (done)

## Setup: Email (required for email skill)

1. Go to https://myaccount.google.com/apppasswords
2. Create a new App Password (select "Mail" / "Other")
3. Copy the 16-character password
4. Edit `.env`:
   ```
   EMAIL_USER=you@gmail.com
   EMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
   ```

## Setup: OpenRouter (required for LLM brain)

1. Sign up at https://openrouter.ai/
2. Create an API key
3. Edit `.env`:
   ```
   OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

## Contacts

Add yourself and frequent contacts to `resources/contacts.csv`:
```csv
name,whatsapp_id,email,relation,notes
Mom,,mom@example.com,Family,
Prof Sharma,prof_sharma,sharma@college.edu,Faculty,Project guide
```

The WhatsApp ID column stores the contact name as it appears in WhatsApp Web (used for lookup when no explicit phone number is stored).

## License

Personal/educational project.
