"""
main.py — Main entry point for the JARVIS voice assistant.

This is the full Phase 2 loop. It now does the complete round trip:

    1. SLEEP   — wait quietly until it hears the wake word "Hey Jarvis".
    2. LISTEN  — record a few seconds of your command.
    3. HEAR    — turn that audio into text with Whisper (STT).
    4. THINK   — send the text to the LLM brain and get a smart reply.
    5. SPEAK   — say the reply out loud with Piper (TTS).
    ...then go back to step 1 and wait for the next "Hey Jarvis".

How to run:
    python main.py

How to stop:
    Press Ctrl+C at any time.

One-time setup before the first run:
    python -m jarvis.wakeword --download     # fetch the wake-word model
    # and put your key in a .env file (see .env.example) for smart replies:
    #     OPENROUTER_API_KEY=sk-or-...

What's already built:
- Phase 1: mic capture + Whisper STT + Piper TTS   (jarvis/audio, stt, tts)
- Phase 2: wake word + LLM brain                    (jarvis/wakeword, brain)
- Phase 3: "open any app" skill                     (jarvis/skills/open_app)
           Runs OFFLINE (no API key) and is checked before the brain, so
           "open chrome" never wastes an LLM call.

What we'll add later:
- Phase 3: more skills (WhatsApp, Gmail email)
- Phase 4: web search + longer conversation memory
- Phase 6: system tray icon
"""

from jarvis import brain
from jarvis.audio import record
from jarvis.stt import transcribe
from jarvis.tts import speak
from jarvis.wakeword import listen_for_wakeword
from jarvis.skills.open_app import try_open_app

# How many seconds to record after the wake word fires. Long enough for a
# full command ("open chrome and search for cats"), short enough to feel
# responsive. Phase 4 will replace this with smarter voice-activity stop.
COMMAND_SECONDS = 5

# A short spoken acknowledgement so the user knows Jarvis woke up and is
# now listening for their command.
ACK_PHRASE = "Yes?"

# We keep a little conversation history so follow-up questions have context
# within one session. It resets when you restart the program. (Long-term
# memory across restarts is a Phase 4 feature.) Each entry is a dict like
# {"role": "user"/"assistant", "content": "..."}.
_history: list[dict] = []
MAX_HISTORY_TURNS = 6  # keep the last 6 messages (3 back-and-forths)


def handle_command(text: str) -> None:
    """Send one transcribed command to the right handler and speak back.

    Order matters: we try the offline "open any app" skill FIRST, because it
    is fast, free, and does not need an API key. Only if the command is not an
    app-launch do we fall through to the LLM brain.
    """
    global _history

    print(f"[main] you said: {text!r}")

    # 1. SKILL (offline): "open chrome", "open youtube and play ...", etc.
    #    try_open_app() returns (handled, message). If handled is True it
    #    already launched the app, so we just say the confirmation and stop.
    handled, skill_message = try_open_app(text)
    if handled:
        print(f"[main] skill: open-app -> {skill_message}")
        speak(skill_message)
        return

    # 2. BRAIN (needs API key): general questions / conversation.
    reply = brain.ask(text, history=_history)

    # brain.ask() returns a "[brain] ..." string when something went wrong
    # (no API key, or the network call failed). Detect that so we can say
    # something friendly out loud instead of reading the raw error.
    if reply.startswith("[brain]"):
        print(reply)  # full detail stays in the console for the developer
        speak("Sorry, my thinking brain is not connected right now.")
        return

    # Success: remember this turn and speak the reply.
    _history.append({"role": "user", "content": text})
    _history.append({"role": "assistant", "content": reply})
    # Trim history so the prompt does not grow forever.
    if len(_history) > MAX_HISTORY_TURNS:
        _history = _history[-MAX_HISTORY_TURNS:]

    speak(reply)


def main() -> None:
    print("=" * 50)
    print("JARVIS — Phase 2 (wake word + brain)")
    print("Say 'Hey Jarvis' to wake me. Press Ctrl+C to stop.")
    print("=" * 50)

    # Tell the developer up front whether smart replies will work, so a
    # missing API key is obvious immediately instead of only when speaking.
    if brain.load_api_key():
        print("[main] LLM brain: API key found — smart replies enabled.")
    else:
        print("[main] LLM brain: no OPENROUTER_API_KEY — replies will be "
              "limited. See .env.example to enable smart replies.")
    print()

    while True:
        try:
            # 1. SLEEP: wait quietly until we hear "Hey Jarvis".
            listen_for_wakeword()

            # 2. Acknowledge so the user knows we're now listening.
            speak(ACK_PHRASE)

            # 3. LISTEN: record the actual command.
            audio = record(seconds=COMMAND_SECONDS)

            # 4. HEAR: audio -> text.
            text = transcribe(audio)

            # 5. THINK + SPEAK: if we heard words, answer them.
            if text:
                handle_command(text)
            else:
                # Whisper returned empty (silence / unclear). Don't nag.
                print("[main] didn't catch that, going back to sleep.")
            print()

        except KeyboardInterrupt:
            print("\n[main] goodbye!")
            break


if __name__ == "__main__":
    main()
