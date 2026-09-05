"""
main.py — Main entry point for the JARVIS voice assistant.

This is the "hello world" of the whole project. It does the bare minimum:
listen, transcribe, echo back. No brain, no skills, no wake word yet —
those come in later phases.

How to run:
    python main.py

How to stop:
    Press Ctrl+C. (Windows will print "KeyboardInterrupt" and exit.)

What's in here:
- A simple infinite loop
- 5-second audio chunks
- Print what we heard, then speak it back

What we'll add later:
- Phase 2: wake word detection (sleep until "Hey Jarvis")
- Phase 3: LLM brain (smart replies + skills)
- Phase 4: web search + conversation memory
- Phase 5: WhatsApp messaging
- Phase 6: system tray icon
"""

from jarvis.audio import record
from jarvis.stt import transcribe
from jarvis.tts import speak


def main() -> None:
    print("=" * 50)
    print("JARVIS — Phase 1 (voice loop)")
    print("Press Ctrl+C to stop")
    print("=" * 50)
    print()

    while True:
        try:
            # 1. Listen: grab 5 seconds of audio from the mic.
            audio = record(seconds=5)

            # 2. Transcribe: audio -> text using Whisper.
            text = transcribe(audio)

            # 3. Respond: if we heard something, echo it back.
            if text:
                response = f"I heard you say: {text}"
                speak(response)
            else:
                # Whisper returned empty (silence or unclear audio).
                # No need to speak — that would be annoying.
                print("[main] silence detected, skipping response")
                print()
        except KeyboardInterrupt:
            # User pressed Ctrl+C. Exit cleanly.
            print("\n[main] goodbye!")
            break


if __name__ == "__main__":
    main()
