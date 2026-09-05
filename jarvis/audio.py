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

from __future__ import annotations

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


# --- Voice-activity detection ------------------------------------------------
# The old Phase-1 loop recorded a FIXED number of seconds after the wake word.
# That forces the user to keep talking for the whole window and cuts them off
# at the end of it. VAD lets JARVIS stop recording as soon as you go quiet.
#
# Algorithm: stream 20 ms frames; keep a sliding ring buffer of recent RMS
# energy; decide "speech" vs "silence" with a simple adaptive threshold. Once
# we have SOME speech and then a sustained run of silence, we stop. A fixed
# max_seconds cap still bounds the worst case.

# Frame size for the VAD loop: 20 ms at 16 kHz = 320 samples. Small enough to
# react quickly to the end of a sentence.
_VAD_BLOCKSIZE = int(0.020 * SAMPLE_RATE)  # 320

# RMS energy below this counts as silence for typical desktop mics. The value
# is deliberately conservative (low) so quiet but real speech is not dropped.
_SILENCE_RMS = 400.0

# How long the user must stay quiet before we consider the utterance over.
_SILENCE_TAIL_SECONDS = 0.6

# Minimum speech we require before a silence can stop us (avoids stopping on
# a cough or the tail of the wake word).
_MIN_SPEECH_SECONDS = 0.3


def _rms(frame: np.ndarray) -> float:
    """Root-mean-square energy of one int16 frame."""
    f = frame.astype(np.float32)
    return float(np.sqrt(np.mean(f * f)))


def record_until_silence(
    max_seconds: int = DEFAULT_DURATION,
    sample_rate: int = SAMPLE_RATE,
    silence_rms: float = _SILENCE_RMS,
) -> np.ndarray:
    """Record speech, stopping after the user goes quiet.

    Streams audio in 20 ms frames. Stops when:
      - `max_seconds` is reached (worst case), OR
      - the user has spoken for at least `_MIN_SPEECH_SECONDS` AND has been
        quiet for `_SILENCE_TAIL_SECONDS`.

    Returns a 1-D int16 numpy array, clipped to the speech (leading and
    trailing silence removed). If nothing audible was said, returns an empty
    array — callers should handle that (retry or go back to sleep).

    Note: this exists precisely to replace the fixed-duration `record()`
    that used to be called in the main loop. `record()` is kept for tests,
    one-off self-tests, and explicit duration needs.
    """
    frames_per_blocksize = _VAD_BLOCKSIZE
    print(f"[audio] listening until silence (max {max_seconds}s)... speak now")

    # We collect raw frames, then trim silence at the end ourselves.
    collected: list[np.ndarray] = []
    speech_frames = 0
    silence_frames = 0

    target_frames = int(max_seconds * sample_rate)
    max_collected_frames = target_frames // frames_per_blocksize

    with sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        blocksize=frames_per_blocksize,
    ) as stream:
        while len(collected) < max_collected_frames:
            data, _overflowed = stream.read(frames_per_blocksize)
            frame = data.flatten()
            collected.append(frame)

            if _rms(frame) >= silence_rms:
                speech_frames += 1
                silence_frames = 0
            else:
                silence_frames += 1

            # Stop when we have real speech and then a quiet tail.
            if silence_frames >= int(_SILENCE_TAIL_SECONDS * sample_rate / frames_per_blocksize) \
                    and speech_frames >= int(_MIN_SPEECH_SECONDS * sample_rate / frames_per_blocksize):
                print("[audio] end of speech detected.")
                break

    if not collected:
        return np.zeros(0, dtype=np.int16)

    audio = np.concatenate(collected).astype(np.int16)

    # Trim leading + trailing silence so Whisper doesn't spend time on empty
    # audio (and so the "didn't catch that" fallback triggers sensibly).
    frame_sz = frames_per_blocksize
    starts, ends = [], []
    for i in range(0, len(audio) - frame_sz, frame_sz):
        if _rms(audio[i:i + frame_sz]) >= silence_rms:
            starts.append(i)
            break
    for i in range(len(audio) - frame_sz, 0, -frame_sz):
        if _rms(audio[i:i + frame_sz]) >= silence_rms:
            ends.append(i + frame_sz)
            break
    if starts and ends and ends[0] > starts[0]:
        audio = audio[starts[0]:ends[0]]

    # If nothing above the energy threshold was actually found, return empty.
    if len(audio) == 0 or _rms(audio) < silence_rms:
        print("[audio] nothing audible recorded.")
        return np.zeros(0, dtype=np.int16)

    secs = len(audio) / sample_rate
    print(f"[audio] recorded {secs:.2f}s.")
    return audio


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
    # Quick self-test: listen until silence and report what we captured.
    import sys
    if "--until-silence" in sys.argv:
        audio = record_until_silence(max_seconds=5)
        print(f"captured {len(audio)} samples ({len(audio) / SAMPLE_RATE:.2f}s)")
        if len(audio):
            save_wav(audio, "vad_test.wav")
            print("wrote vad_test.wav — open it to verify")
    else:
        audio = record(seconds=3)
        print(f"shape: {audio.shape}, dtype: {audio.dtype}")
        print(f"peak amplitude: {np.abs(audio).max()} (max possible: 32767)")
        save_wav(audio, "test.wav")
        print("wrote test.wav — open it in your music player to verify")
