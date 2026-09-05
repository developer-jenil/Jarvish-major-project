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

    # piper-tts 1.4.x (the modern API) made synthesize() a GENERATOR that
    # yields one AudioChunk per sentence. Each chunk carries its audio as a
    # float32 array already scaled to [-1, 1] and a matching sample_rate.
    #
    # (The old piper 1.x API instead took a wave-file object and wrote
    # straight into it. Passing a file here would be ignored by the new
    # API, producing zero frames of audio — i.e. silence.) We consume the
    # generator and stitch the chunks together.
    chunks = list(voice.synthesize(text))
    if not chunks:
        # No speech produced (empty input). Return silence so callers
        # (sd.play) don't choke on an empty array.
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
