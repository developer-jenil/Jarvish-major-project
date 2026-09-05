"""
jarvis/tts.py — Text-to-speech (the "mouth" of the assistant).

We use Piper, a fast local neural TTS engine. The voice is the
"hi_IN-pratham-medium" model — a Hindi male speaker that does OK on
English too. It runs entirely offline once the model is on disk.

Piper is a "VITS" model — a single-pass neural network that converts
text directly to audio waveform. No intermediate spectrogram step.
That's why it's fast (~real-time on CPU) and sounds natural.

A note on Hindi + English:
- This voice is trained primarily on Hindi. It pronounces English words
  with a Hindi accent, which actually sounds pretty good for Hinglish
  responses ("namaste, I am Jarvis").
- If you want pure-English pronunciation, switch VOICE_PATH to an
  English voice (en_US-lessac-medium is a good one).
"""

import asyncio
import re
from pathlib import Path

import numpy as np
import sounddevice as sd

# Path to the onnx voice model + its json config. We use Path so this
# works on Windows (backslashes) AND Linux/macOS (forward slashes) without
# any code changes.
VOICE_PATH = Path(__file__).resolve().parent.parent / "models" / "tts" / "hi_IN-pratham-medium.onnx"
VOICE_CONFIG = VOICE_PATH.with_suffix(".onnx.json")

# Default natural studio voices for Hinglish / Indian English
DEFAULT_EDGE_VOICE = "hi-IN-MadhurNeural"
AVAILABLE_EDGE_VOICES = {
    "hi-IN-MadhurNeural": "Madhur (Hindi / Hinglish Male - Natural)",
    "hi-IN-SwaraNeural": "Swara (Hindi / Hinglish Female - Natural)",
    "en-IN-NeerjaNeural": "Neerja (Indian English Female - Natural)",
    "en-IN-PrabhatNeural": "Prabhat (Indian English Male - Natural)",
}

# Lazy global — Piper loads in ~2-3 sec. We don't want to do that on
# every command, so cache the synthesizer.
_voice = None


def clean_text_for_speech(text: str) -> str:
    """
    Sanitize text for natural speech synthesis.
    Strips parenthetical translations e.g. '(Hello! I am Jarvis)',
    markdown formatting symbols (*, #, _, `, etc.), and collapses whitespace.
    """
    if not text:
        return ""
    # 1. Remove parenthetical translations or remarks: (text) and [text]
    cleaned = re.sub(r"\([^)]*\)", "", text)
    cleaned = re.sub(r"\[[^\]]*\]", "", cleaned)
    # 2. Remove markdown symbols like bold/italic asterisks, hashes, backticks, tildes
    cleaned = re.sub(r"[*#_~`]", "", cleaned)
    # 3. Remove list bullets at start of lines or segments
    cleaned = re.sub(r"^[\s*+-]+", "", cleaned, flags=re.MULTILINE)
    # 4. Normalize multiple whitespace and newlines into single spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _get_voice():
    """Load the Piper voice on first call."""
    global _voice
    if _voice is None:
        if not VOICE_PATH.exists():
            raise FileNotFoundError(
                f"voice model not found at {VOICE_PATH}. "
                "Run the download step in the README or Phase 1 task 1.4."
            )
        from piper import PiperVoice
        print(f"[tts] loading voice from {VOICE_PATH.name}...")
        _voice = PiperVoice.load(str(VOICE_PATH), config_path=str(VOICE_CONFIG))
        print("[tts] voice ready")
    return _voice


async def _edge_synthesize_async(text: str, voice: str = DEFAULT_EDGE_VOICE) -> bytes:
    """Internal helper to stream audio from edge-tts."""
    import edge_tts
    comm = edge_tts.Communicate(text, voice)
    chunks = []
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)


def synthesize_edge(text: str, voice: str = DEFAULT_EDGE_VOICE) -> bytes:
    """
    Synthesize natural human-like speech using Microsoft Edge neural voices.
    Returns raw MP3 audio bytes.
    """
    cleaned = clean_text_for_speech(text)
    if not cleaned:
        return b""
    try:
        # Run in new or current asyncio event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In an already running loop (e.g. some web servers), run via separate thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(lambda: asyncio.run(_edge_synthesize_async(cleaned, voice))).result()
            else:
                return loop.run_until_complete(_edge_synthesize_async(cleaned, voice))
        except RuntimeError:
            return asyncio.run(_edge_synthesize_async(cleaned, voice))
    except Exception as exc:
        print(f"[tts] edge-tts error: {exc}")
        return b""


def synthesize(text: str) -> tuple[np.ndarray, int]:
    """
    Convert text to audio via local Piper. Returns (samples, sample_rate).

    samples is a 1-D float32 numpy array in [-1, 1].
    sample_rate is typically 22050 for this voice.
    """
    cleaned = clean_text_for_speech(text)
    if not cleaned:
        return np.zeros(0, dtype=np.float32), 22050

    voice = _get_voice()
    chunks = list(voice.synthesize(cleaned))
    if not chunks:
        return np.zeros(0, dtype=np.float32), voice.config.sample_rate

    sample_rate = chunks[0].sample_rate
    audio = np.concatenate([c.audio_float_array for c in chunks]).astype(np.float32)
    return audio, sample_rate


def speak(text: str, blocking: bool = True) -> None:
    """
    Speak `text` out loud through the default speakers.

    Args:
        text: what to say. Can be Hindi, English, or Hinglish.
        blocking: if True, wait until playback finishes. If False, return
                  immediately and let it play in the background.
    """
    cleaned = clean_text_for_speech(text)
    if not cleaned:
        return
    print(f"[tts] speaking: {cleaned!r}")
    audio, sample_rate = synthesize(cleaned)
    sd.play(audio, samplerate=sample_rate)
    if blocking:
        sd.wait()


if __name__ == "__main__":
    # Self-test: speak three different phrases.
    speak("Hello, I am Jarvis. Namaste.")
    speak("मैं आपकी कैसे मदद कर सकता हूँ?")
    speak("The time is now twelve thirty PM.")
