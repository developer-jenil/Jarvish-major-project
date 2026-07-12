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

import io
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

# Path to the onnx voice model + its json config. We use Path so this
# works on Windows (backslashes) AND Linux/macOS (forward slashes) without
# any code changes.
VOICE_PATH = Path(__file__).resolve().parent.parent / "models" / "tts" / "hi_IN-pratham-medium.onnx"
VOICE_CONFIG = VOICE_PATH.with_suffix(".onnx.json")

# Lazy global — Piper loads in ~2-3 sec. We don't want to do that on
# every command, so cache the synthesizer.
_voice = None


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


def synthesize(text: str) -> tuple[np.ndarray, int]:
    """
    Convert text to audio. Returns (samples, sample_rate).

    samples is a 1-D float32 numpy array in [-1, 1].
    sample_rate is typically 22050 for this voice.
    """
    voice = _get_voice()

    # Piper can write straight to a file or stream chunks. We use a
    # BytesIO buffer so we never touch disk for short responses.
    #
    # IMPORTANT: Piper's synthesize() does NOT set the wave file's
    # channel count or sample rate — you have to do that yourself
    # BEFORE calling synthesize. The model knows its own sample rate
    # (we read it from voice.config.sample_rate below) and Piper
    # always outputs mono.
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)                   # Piper outputs 16-bit PCM
        wf.setframerate(voice.config.sample_rate)
        voice.synthesize(text, wf)

    # Re-parse the WAV we just wrote into raw samples.
    buf.seek(0)
    with wave.open(buf, "rb") as wf:
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    # Convert 16-bit PCM bytes to float32 in [-1, 1] for sounddevice.
    audio_int16 = np.frombuffer(raw, dtype=np.int16)
    audio_float = audio_int16.astype(np.float32) / 32768.0
    return audio_float, sample_rate


def speak(text: str, blocking: bool = True) -> None:
    """
    Speak `text` out loud through the default speakers.

    Args:
        text: what to say. Can be Hindi, English, or Hinglish.
        blocking: if True, wait until playback finishes. If False, return
                  immediately and let it play in the background.
    """
    if not text or not text.strip():
        return
    print(f"[tts] speaking: {text!r}")
    audio, sample_rate = synthesize(text)
    sd.play(audio, samplerate=sample_rate)
    if blocking:
        sd.wait()


if __name__ == "__main__":
    # Self-test: speak three different phrases.
    speak("Hello, I am Jarvis. Namaste.")
    speak("मैं आपकी कैसे मदद कर सकता हूँ?")
    speak("The time is now twelve thirty PM.")
