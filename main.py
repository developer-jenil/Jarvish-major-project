"""
main.py — Main entry point for the JARVIS voice assistant.

This runs the full Phase 4 loop:

    1. SLEEP   — wait quietly until it hears the wake word "Hey Jarvis".
    2. LISTEN  — record a few seconds of your command.
    3. HEAR    — turn that audio into text with Whisper (STT).
    4. ROUTE   — check skills first (offline apps, WhatsApp, email,
                 web search), then fall through to the LLM brain.
    5. SPEAK   — say the reply out loud with Piper (TTS).
    ...then go back to step 1 and wait for the next "Hey Jarvis".

How to run:
    python main.py                     # normal (console) mode
    JARVIS_TRAY=1 python main.py       # minimise to system tray

How to stop:
    Press Ctrl+C   (console mode)
    Click Stop in the tray menu        (tray mode)

One-time setup before the first run:
    python -m jarvis.wakeword --download     # fetch the wake-word model
    # and put your keys in a .env file (see .env.example):
    #     OPENROUTER_API_KEY=sk-or-...
    #     EMAIL_USER=you@gmail.com
    #     EMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

What's built:
- Phase 1: mic capture + Whisper STT + Piper TTS        (jarvis/audio, stt, tts)
- Phase 2: wake word + LLM brain                        (jarvis/wakeword, brain)
- Phase 3: skills
   - "open any app"         (DONE — offline, jarvis/skills/open_app)
   - WhatsApp messages      (DONE — opens WA Web, jarvis/skills/whatsapp)
   - Gmail email            (DONE — SMTP send, jarvis/skills/email)
- Phase 4: web search                                     (jarvis/skills/web_search)
- Phase 6: system tray icon                               (jarvis/tray)
"""

import os
import sys

from jarvis import brain
from jarvis.audio import record
from jarvis.stt import transcribe
from jarvis.tts import speak
from jarvis.skills import (
    try_open_app,
    try_datetime,
    try_whatsapp,
    try_send_email,
    try_edit_email_draft,
    try_web_search,
    try_browser_control,
)

# How many seconds to record after the wake word fires. Long enough for a
# full command ("open chrome and search for cats"), short enough to feel
# responsive. Future: replace with smarter voice-activity stop.
COMMAND_SECONDS = 5

# A short spoken acknowledgement so the user knows Jarvis woke up and is
# now listening for their command.
# What the assistant says right after waking up to let the user know it is
# listening. Short and friendly.
ACK_PHRASE = "Yes, boss?"

# Rolling conversation history so the LLM remembers previous turns.
# Each entry is {"role": "user"|"assistant", "content": "..."}.
# We cap this to the last N turns so we don't blow past the model's context
# window or inflate API token cost.
_history: list[dict[str, str]] = []
MAX_HISTORY_TURNS = 10


def handle_command(text: str) -> None:
    """Route a single transcribed command to a skill or the LLM brain.

    Separated out so tests can call it with raw strings without needing a mic.
    """
    global _history
    try:
        print(f"[main] you said: {text!r}")
    except UnicodeEncodeError:
        safe = text.encode("ascii", "backslashreplace").decode("ascii")
        print(f"[main] you said: {safe!r}")

    # 1. SKILLS (offline-first where possible): try each in order.
    for skill_name, try_fn in (
        ("browser-control", try_browser_control),
        ("open-app",  try_open_app),
        ("datetime",  try_datetime),
        ("whatsapp",  try_whatsapp),
        ("email-edit", try_edit_email_draft),
        ("email",     try_send_email),
        ("web-search", try_web_search),
    ):
        handled, skill_message = try_fn(text)
        if handled:
            print(f"[main] skill: {skill_name} -> {skill_message}")
            speak(skill_message)
            return

    # 2. BRAIN (needs API key): general questions / conversation.
    reply = brain.ask(text, history=_history)

    # brain.ask() returns a "[brain] ..." string when something went wrong
    # (no API key, or the network call failed). Detect that so we can say
    # something friendly out loud instead of reading the raw error.
    if reply.startswith("[brain]"):
        print(reply)
        speak("Sorry, my thinking brain is not connected right now.")
        return

    # Success: remember this turn and speak the reply.
    _history.append({"role": "user", "content": text})
    _history.append({"role": "assistant", "content": reply})
    if len(_history) > MAX_HISTORY_TURNS:
        _history = _history[-MAX_HISTORY_TURNS:]

    speak(reply)


def _main_loop() -> None:
    """The core while-True loop. Called directly or from the tray thread."""
    while True:
        try:
            # 1. SLEEP: wait until we hear "Hey Jarvis".
            listen_for_wakeword()

            # 2. Acknowledge.
            speak(ACK_PHRASE)

            # 3. LISTEN: record the actual command.
            audio = record(seconds=COMMAND_SECONDS)

            # 4. HEAR: audio -> text.
            text = transcribe(audio)

            # 5. ROUTE + SPEAK.
            if text:
                handle_command(text)
            else:
                print("[main] didn't catch that, going back to sleep.")
            print()

        except KeyboardInterrupt:
            print("\n[main] goodbye!")
            break


def main() -> None:
    print("=" * 50)
    print("JARVIS — Phase 4 (wake word + brain + skills + search + tray)")
    print("Say 'Hey Jarvis' to wake me. Press Ctrl+C to stop.")
    print("=" * 50)

    # Tell the developer up front whether smart replies will work.
    if brain.load_api_key():
        print("[main] LLM brain: API key found — smart replies enabled.")
    else:
        print("[main] LLM brain: no OPENROUTER_API_KEY — replies will be "
              "limited. See .env.example to enable smart replies.")

    # Check email credentials (don't fail loudly; just inform).
    email_user = os.environ.get("EMAIL_USER")
    email_pw = os.environ.get("EMAIL_APP_PASSWORD")
    if email_user and email_pw:
        print("[main] Email: credentials found — SMTP sending enabled.")
    else:
        print("[main] Email: no EMAIL_USER/EMAIL_APP_PASSWORD in .env — "
              "email skill will ask you to configure it.")
    print()

    # Pick the input device.
    import sounddevice as sd
    chosen_device = os.environ.get("JARVIS_INPUT_DEVICE")
    if chosen_device is not None:
        try:
            chosen_device = int(chosen_device)
            sd.default.device[0] = chosen_device
            devices = sd.query_devices(kind="input")
            print(f"[main] Using input device {chosen_device}: "
                  f"{devices['name']}")
        except (ValueError, OSError) as e:
            print(f"[main] Could not set device {chosen_device!r}: {e}")
    print()

    # Tray mode? (set JARVIS_TRAY=1 to enable)
    if os.environ.get("JARVIS_TRAY", "").lower() in ("1", "true", "yes"):
        print("[main] Running in system-tray mode (JARVIS_TRAY=1).")
        from jarvis.tray import run_tray
        run_tray(_main_loop)
    else:
        _main_loop()


if __name__ == "__main__":
    main()
