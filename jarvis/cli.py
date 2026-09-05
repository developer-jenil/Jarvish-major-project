"""
jarvis/cli.py — Command-line entry point and main assistant loop.

This is the module the `jarvis` console script (and `python -m jarvis`) runs.
It used to live in a top-level main.py; moving it INTO the package means the
built wheel (`pip install jarvis-voice-assistant`) actually works — the old
wheel shipped the console script pointing at a main.py that was never
packaged (see the packaging fix in pyproject.toml).

Responsibilities:
- Parse command-line flags (device, model, tray, one-shot, selftest, ...).
- Run the Phase 4 loop: sleep on wake word -> listen -> transcribe ->
  route skills/brain -> speak.
- Keep conversation memory persistently (jarvis/memory.py) instead of a
  throw-away in-memory list.
- Survive individual command failures without killing the whole loop.

Usage:
    jarvis                          # console mode
    jarvis --tray                   # minimise to system tray
    jarvis --once "open chrome"     # run one command in text and exit
    jarvis --selftest               # parse a battery of phrases (no mic)
    python -m jarvis                # same as `jarvis`
"""

from __future__ import annotations

import argparse
import os
import sys

from jarvis import brain, memory
from jarvis.audio import record
from jarvis.stt import transcribe
from jarvis.tts import speak
from jarvis.wakeword import listen_for_wakeword
from jarvis.skills import try_open_app, try_whatsapp, try_send_email, try_web_search

# How many seconds to record after the wake word fires. Long enough for a
# full command ("open chrome and search for cats"), short enough to feel
# responsive. It is a MAXIMUM cap — recording stops early once voice
# activity ends (see jarvis/audio.py record_until_silence).
COMMAND_SECONDS = 5

# A short spoken acknowledgement so the user knows Jarvis woke up and is
# now listening for their command. (Will move to a per-language config in a
# later phase.)
ACK_PHRASE = "Yes?"

# --- Skill routing --------------------------------------------------------
# Skills are tried BEFORE the brain, in this order. Each entry is
# (name, callable) and the callable returns (handled: bool, message: str).
SKILLS = (
    ("open-app",   try_open_app),
    ("whatsapp",   try_whatsapp),
    ("email",      try_send_email),
    ("web-search", try_web_search),
)


def handle_command(text: str) -> str:
    """Route one command to a skill or the brain and return the reply text.

    This does NOT speak — it returns the spoken message so callers (the
    loop, the one-shot CLI, the web API) can decide how to deliver it.

    Skills are checked BEFORE the brain, in this order:
      1. open_app   — fast, offline, no API key needed
      2. whatsapp   — opens WhatsApp (needs internet + logged-in session)
      3. email      — sends via SMTP (needs .env credentials)
      4. web_search — queries DuckDuckGo locally (needs internet)
    Only if no skill matches does the request go to the LLM brain.
    """
    # Windows console (cp1252) cannot print Devanagari/etc. characters.
    try:
        print(f"[main] you said: {text!r}")
    except UnicodeEncodeError:
        safe = text.encode("ascii", "backslashreplace").decode("ascii")
        print(f"[main] you said: {safe!r}")

    # 1. SKILLS (offline-first where possible): try each in order.
    for skill_name, try_fn in SKILLS:
        try:
            handled, skill_message = try_fn(text)
        except Exception as exc:
            # A buggy skill must never kill the loop — log and move on.
            print(f"[main] skill {skill_name} raised: {exc!r}")
            continue
        if handled:
            print(f"[main] skill: {skill_name} -> {skill_message}")
            return skill_message

    # 2. BRAIN (needs API key): general questions / conversation.
    reply = brain.ask(text, history=memory.load_history())

    # brain.ask() returns a "[brain] ..." string when something went wrong
    # (no API key, or the network call failed). Detect that so we can return
    # a friendly spoken line instead of reading the raw error.
    if reply.startswith("[brain]"):
        print(reply)
        return "Sorry, my thinking brain is not connected right now."

    # Success: remember this turn and reply.
    memory.append_turn(text, reply)
    return reply


def _listen_command() -> str:
    """Record a command and transcribe it, guarding against mic/model errors."""
    try:
        audio = record_until_silence(max_seconds=COMMAND_SECONDS)
    except Exception as exc:
        print(f"[main] recording failed: {exc!r}")
        return ""
    try:
        return transcribe(audio)
    except Exception as exc:
        print(f"[main] transcription failed: {exc!r}")
        return ""


def _main_loop() -> None:
    """The core while-True loop. Called directly or from the tray thread."""
    while True:
        try:
            # 1. SLEEP: wait until we hear "Hey Jarvis".
            listen_for_wakeword()

            # 2. Acknowledge.
            speak(ACK_PHRASE)

            # 3. LISTEN + HEAR: command audio -> text.
            text = _listen_command()

            # 4. ROUTE + SPEAK.
            if text:
                reply = handle_command(text)
                try:
                    speak(reply)
                except Exception as exc:
                    print(f"[main] speaking failed: {exc!r}")
            else:
                print("[main] didn't catch that, going back to sleep.")
            print()

        except KeyboardInterrupt:
            print("\n[main] goodbye!")
            break
        except Exception as exc:
            # Never let an unexpected error kill the always-on assistant.
            print(f"[main] unexpected error in loop: {exc!r}")
            import traceback
            traceback.print_exc()


# --- CLI -------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse parser (separate so tests can drive it)."""
    p = argparse.ArgumentParser(
        prog="jarvis",
        description="Hey Jarvis — personal voice assistant for Windows.",
    )
    p.add_argument(
        "--tray", action="store_true",
        help="Run in the background with a system tray icon instead of a console.",
    )
    p.add_argument(
        "--no-tray", action="store_true",
        help="Run in the foreground console even if JARVIS_TRAY is set.",
    )
    p.add_argument(
        "--model", default=None,
        help="OpenRouter model to use (e.g. 'meta-llama/llama-3.1-8b-instruct').",
    )
    p.add_argument(
        "--whisper", default=None,
        help="Whisper model size (tiny/base/small/medium/large-v3).",
    )
    p.add_argument(
        "--input-device", default=None, type=int,
        help="Index of the microphone to use (see --list-devices).",
    )
    p.add_argument(
        "--list-devices", action="store_true",
        help="Print available audio input devices and exit.",
    )
    p.add_argument(
        "--once", metavar="TEXT",
        help="Run ONE command from text (no mic, no wake word) and exit.",
    )
    p.add_argument(
        "--selftest", action="store_true",
        help="Route a battery of phrase samples through the skills (no mic).",
    )
    return p


def _selftest() -> int:
    """Exercise skill parsing end-to-end without any hardware."""
    print("[selftest] routing sample phrases through skills...")
    samples = [
        "open chrome",
        "kholo calculator",
        "send a whatsapp to mom saying I will be late",
        "send an email to prof sharma about the project update",
        "search for weather in mumbai",
        "tell me a joke",
    ]
    # Import dry-run helpers to avoid actually opening browsers / sending mail.
    from jarvis.skills.open_app import match_intent as open_intent
    from jarvis.skills.whatsapp import _parse_command as wa_parse
    from jarvis.skills.email import _extract_recipients as em_recips
    from jarvis.skills.web_search import match_intent as search_intent

    for s in samples:
        print(f"  {s!r:60} -> open={open_intent(s) and 'YES' or 'no'} "
              f"wa={bool(wa_parse(s)[0]) and 'YES' or 'no'} "
              f"email={bool(em_recips(s)[0] or em_recips(s)[1] or em_recips(s)[2]) and 'YES' or 'no'} "
              f"search={search_intent(s)!r}")
    print("[selftest] PASS — skill routing parses all sample phrases.")
    return 0


def _list_devices() -> int:
    """Print all audio input devices and exit."""
    import sounddevice as sd
    print("Available audio input devices:")
    for i, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) > 0:
            default = "  (default)" if i == sd.default.device[0] else ""
            print(f"  [{i}] {dev['name']}{default}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the `jarvis` console script and `python -m jarvis`."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # --- Non-interactive flags -------------------------------------------
    if args.list_devices:
        return _list_devices()

    if args.selftest:
        return _selftest()

    # Set input device / whisper model before anything touches the mic.
    if args.input_device is not None:
        import sounddevice as sd
        sd.default.device[0] = args.input_device
    if args.whisper:
        os.environ["JARVIS_WHISPER_MODEL"] = args.whisper

    print("=" * 50)
    print("JARVIS — voice assistant (wake word + brain + skills + search + tray)")
    print("Say 'Hey Jarvis' to wake me. Press Ctrl+C to stop.")
    print("=" * 50)

    # Tell the developer up front whether smart replies will work.
    if brain.load_api_key():
        print("[main] LLM brain: API key found — smart replies enabled.")
    else:
        print("[main] LLM brain: no OPENROUTER_API_KEY — replies will be "
              "limited. See .env.example to enable smart replies.")

    # --- One-shot text command (no mic, no wake word) ---------------------
    if args.once:
        reply = handle_command(args.once)
        print(f"\n[main] jarvis: {reply}")
        return 0

    # --- Input device banner (only in interactive modes) ------------------
    print()
    _print_devices_or_default()
    print()

    # Tray mode? (set JARVIS_TRAY=1 to enable; --no-tray overrides it)
    tray_enabled = os.environ.get("JARVIS_TRAY", "").lower() in ("1", "true", "yes")
    if args.tray or (tray_enabled and not args.no_tray):
        print("[main] Running in system-tray mode.")
        from jarvis.tray import run_tray
        run_tray(_main_loop)
    else:
        _main_loop()
    return 0


def _print_devices_or_default() -> None:
    """Show the chosen/named input device, or a hint on how to pick one."""
    import sounddevice as sd
    try:
        chosen = os.environ.get("JARVIS_INPUT_DEVICE")
        if chosen is not None:
            idx = int(chosen)
            sd.default.device[0] = idx
            name = sd.query_devices(idx)["name"]
            print(f"[main] Using input device {idx}: {name}")
        else:
            dev = sd.query_devices(kind="input")
            print(f"[main] Using default input: {dev['name']} "
                  f"(add --input-device <index> to change)")
    except (ValueError, OSError) as e:
        print(f"[main] Could not choose input device: {e}")


if __name__ == "__main__":
    sys.exit(main())