# Major Project — JARVIS

A "Hey Jarvis" personal voice assistant for Windows. Wakes on a custom hotword, understands Hindi + English (Hinglish), speaks back, and can open apps, search the web, send WhatsApp messages, and send Gmail emails (with subject, To, BCC, and AI-written content).

## Status

Currently in **Phase 1 — Voice loop** (microphone capture, speech-to-text, and text-to-speech are implemented and run locally). The full development plan and team roles are tracked in the project discussion notes (`19 july major project discussion.md` on the Desktop).

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
3. "Hey Jarvis" wake word
4. LLM brain + open-app skill
5. Web search + memory
6. WhatsApp messaging
7. Gmail email (subject / To / BCC + AI-written content)
8. Polish + system tray

## License

Personal/educational project.
