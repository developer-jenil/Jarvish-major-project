"""
jarvis/audio.py — Microphone capture utilities.

This is the "ears" of the assistant. We use sounddevice (a wrapper around
PortAudio) to grab raw audio samples from the default input device.

Audio basics you should know:
- Sample rate = how many snapshots of the sound wave we take per second.
  16,000 Hz (16 kHz) is the standard for speech recognition. Human voice
  only goes up to ~8 kHz, so 16 kHz captures everything we need.
- Mono = 1 channel. Stereo = 2. We use mono — speech doesn't need stereo.
- dtype=int16 = each sample is a 16-bit signed integer. Range: -32768 to +32767.
  Whisper expects this exact format, so we keep it simple.
"""

import numpy as np
import sounddevice as sd

# Standard speech-recognition sample rate. Don't change this unless you
# know what you're doing — Whisper was trained on 16 kHz audio.
SAMPLE_RATE = 16000

# We record in one-shot chunks of this many seconds. Long enough to capture
# a full command ("hey jarvis, open chrome and search for cats"), short
# enough to feel responsive.
DEFAULT_DURATION = 5


def record(seconds: int = DEFAULT_DURATION, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """
    Record `seconds` of audio from the default microphone.

    Returns a 1-D numpy array of int16 samples, shape (seconds * sample_rate,).

    Note: this BLOCKS for `seconds` seconds. The caller is expected to
    sit in silence (or noise) while we record. Later in Phase 2 we'll
    add voice-activity-detection so we only record when you're actually
    talking.
    """
    # sounddevice wants (frames, channels) for the callback / 1-D for input.
    # We use dtype='int16' so the bytes match what Whisper expects.
    frames = int(seconds * sample_rate)
    print(f"[audio] recording {seconds}s... speak now")
    audio = sd.rec(
        frames,
        samplerate=sample_rate,
        channels=1,            # mono
        dtype="int16",         # Whisper's preferred format
    )
    sd.wait()                 # block until recording is finished
    print("[audio] done recording")

    # sd.rec returns shape (frames, 1) when channels=1. We flatten to 1-D
    # so callers can pass it straight to faster-whisper.
    return audio.flatten()


def save_wav(audio: np.ndarray, path: str, sample_rate: int = SAMPLE_RATE) -> None:
    """
    Save a 1-D int16 numpy array to a .wav file. Useful for debugging —
    you can listen back to what the mic captured.
    """
    # stdlib `wave` is the simplest path: no extra dependency, writes a
    # proper 16-bit PCM WAV that any player understands.
    import wave

    # Wave wants raw bytes in little-endian. numpy's .tobytes() gives that
    # for int16 on x86/ARM. For multi-channel we'd interleave here, but
    # we always pass mono, so no reshuffle needed.
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)              # mono
        wf.setsampwidth(2)              # 16-bit = 2 bytes per sample
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    print(f"[audio] saved to {path}")


def list_input_devices() -> None:
    """Print all available input devices. Helpful for picking the right mic."""
    print(sd.query_devices())


if __name__ == "__main__":
    # Quick self-test: record 3 seconds, save to test.wav, report level.
    import sys
    audio = record(seconds=3)
    print(f"shape: {audio.shape}, dtype: {audio.dtype}")
    print(f"peak amplitude: {np.abs(audio).max()} (max possible: 32767)")
    save_wav(audio, "test.wav")
    print("wrote test.wav — open it in your music player to verify")
