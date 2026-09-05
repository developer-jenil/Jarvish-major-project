# Major Project — JARVIS

A "Hey Jarvis" personal voice assistant for Windows. Wakes on a custom hotword, understands Hindi + English (Hinglish), speaks back, and can open apps, search the web, send WhatsApp messages, and send Gmail emails (with subject, To, BCC, and AI-written content).

## Status

**Phase 3 — Skills (in progress).** The voice loop, wake word, and LLM brain are done and run locally, and the first skill — **"open any app"** — is implemented. The full development plan and team roles are tracked in the project discussion notes (`19 july major project discussion.md` on the Desktop).

### What works today
- "Hey Jarvis" wake word (local, OpenWakeWord)
- Speech-to-text (faster-whisper, Hindi + English)
- LLM brain (OpenRouter cloud API — `tencent/hy3:free` by default)
- Text-to-speech (Piper, offline)
- **Open-any-app skill** — say e.g. *"open chrome"*, *"open notepad"*, *"open youtube and play despacito"*, *"open google and search for weather in mumbai"*, *"kholo calculator"*. Runs **offline** (no API key) and is checked before the brain.

## Quick start (developer)

```powershell
# Activate the virtual environment (do this every time you open a new terminal)
.\venv\Scripts\Activate.ps1

# Install dependencies (empty for now, will fill in Phase 1)
pip install -r requirements.txt

# Run the assistant (only works after Phase 1)
python main.py
```

## Tech stack

- Wake word: OpenWakeWord (local)
- Speech-to-text: faster-whisper (local, Hindi + English)
- LLM brain: cloud (OpenAI / Anthropic / OpenRouter)
- Text-to-speech: Piper (local)
- WhatsApp: pywhatkit (v1) → Meta Cloud API (v2)
- Gmail email: Gmail API (OAuth) / SMTP with app password

## Phases

1. Setup
2. Voice round-trip  (done — mic + STT + TTS)
3. "Hey Jarvis" wake word  (done)
4. LLM brain  (done)
5. Skills
   - **Open-any-app**  (done — offline, see `jarvis/skills/open_app.py`)
   - WhatsApp messaging  (to do)
   - Gmail email (subject / To / BCC + AI-written content)  (to do)
6. Web search + memory  (to do)
7. Polish + system tray  (to do)

## Open-any-app skill

`jarvis/skills/open_app.py` is a self-contained, offline skill. It recognises
"open/launch/start/run" commands (plus Hinglish verbs like *kholo* / *chalao*),
resolves the spoken name to a known app, website, or search, and launches it via
the Windows shell. Optional "and search for / play ..." queries open a site
search or a Google search.

Test it without launching anything:

```powershell
python -m jarvis.skills.open_app --selftest
python -m jarvis.skills.open_app --dry-run "open youtube and play despacito"
```

## License

Personal/educational project.
