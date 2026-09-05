# Major Project — JARVIS

A "Hey Jarvis" personal voice assistant for Windows. Wakes on a custom hotword, understands Hindi + English (Hinglish), speaks back, and can open apps, search the web, and send WhatsApp messages.

## Status

Currently in **Phase 0 — Setup**. See `.hermes/plans/2026-07-07_120000-jarvis-personal-assistant.md` for the full development plan.

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

## Phases

1. Setup (current)
2. Voice round-trip
3. "Hey Jarvis" wake word
4. LLM brain + open-app skill
5. Web search + memory
6. WhatsApp messaging
7. Polish + system tray

## License

Personal/educational project.
