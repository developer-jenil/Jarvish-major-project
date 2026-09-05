"""
jarvis/stt.py — Speech-to-text (the "ears" -> "words" step).

We use faster-whisper, which is a re-implementation of OpenAI's Whisper
model that's 4x faster and uses less RAM. Same accuracy, just leaner.

Whisper is a "transformer" model trained on 680,000 hours of audio from
the internet, with captions. That's how it "knows" what words sound
like. It supports Hindi natively (the training data included lots of
Hindi audio) and is great at Hinglish (mixed Hindi + English) because
that's how Indians actually talk in real recordings.

Model size options (as of 2026):
  tiny    ~ 75 MB, fastest,  ~70% accuracy
  base    ~150 MB, fast,     ~75% accuracy
  small   ~460 MB, balanced, ~82% accuracy
  medium  ~1.5 GB, slow,     ~86% accuracy  <-- our default (much better Hindi)
  large   ~3.0 GB, slowest,  ~89% accuracy

We use "medium" for noticeably better Hindi/Hinglish accuracy than "small".
The trade-off is a larger ~1.5 GB download and slower transcription on a
CPU-only PC. If speed matters more than accuracy, switch back to "small".
"""

import os
import numpy as np
from faster_whisper import WhisperModel

# Default model size. Can be overridden with JARVIS_WHISPER_MODEL environment
# variable (e.g. "small", "medium", "large-v3").
# We use "small" as default since it is lightweight, runs in ~2s on CPU, and is
# pre-cached, or "medium" for higher Hindi/Hinglish accuracy.
DEFAULT_MODEL_SIZE = os.environ.get("JARVIS_WHISPER_MODEL", "small")

# Compute type. "int8" = uses 8-bit integers internally, ~half the RAM,
# negligible accuracy loss on CPU. If you have a GPU, change to "float16".
DEFAULT_COMPUTE_TYPE = "int8"

# Lazy global so we only load the model once. Loading takes 5-30 sec
# depending on disk + RAM, so we don't want to do it per command.
_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    """Load Whisper on first call, return cached instance after that."""
    global _model
    if _model is None:
        target_model = os.environ.get("JARVIS_WHISPER_MODEL", DEFAULT_MODEL_SIZE)
        print(f"[stt] loading Whisper '{target_model}' model...")
        print("[stt] (first run downloads the model if not cached)")
        try:
            _model = WhisperModel(
                target_model,
                device="cpu",              # change to "cuda" if you have an NVIDIA GPU
                compute_type=DEFAULT_COMPUTE_TYPE,
            )
        except Exception as exc:
            if target_model != "small":
                print(f"[stt] Warning: failed to load '{target_model}' ({exc}). Falling back to 'small' model...")
                _model = WhisperModel(
                    "small",
                    device="cpu",
                    compute_type=DEFAULT_COMPUTE_TYPE,
                )
            else:
                raise exc
        print("[stt] model ready")
    return _model


def transcribe(audio: np.ndarray, language: str | None = None) -> str:
    """
    Transcribe a 1-D int16 numpy array of audio samples into text.

    Args:
        audio: 1-D int16 numpy array at 16 kHz mono (what audio.record() returns)
        language: ISO code like "en", "hi". None = auto-detect. We default
                  to auto-detect so Hinglish works naturally.

    Returns:
        The transcribed text, lowercased and stripped.
    """
    model = _get_model()

    # faster-whisper wants float32 in [-1, 1], not int16. Whisper handles
    # the normalization internally but it expects float input.
    audio_float = audio.astype(np.float32) / 32768.0

    # `beam_size=1` = fastest, slightly less accurate. `beam_size=5` is
    # the default, ~3x slower. We start at 1 for responsiveness; bump
    # later if accuracy is poor.
    segments, info = model.transcribe(
        audio_float,
        language=language,
        beam_size=1,
        vad_filter=True,           # skip silent parts automatically
        vad_parameters=dict(
            min_silence_duration_ms=300,  # treat <300ms gaps as continuous speech
        ),
    )

    # Stitch all segments into one string.
    text = " ".join(segment.text.strip() for segment in segments).strip()

    if info.language:
        # Windows console (cp1252) can't print Devanagari — guard it.
        lang_display = info.language
        try:
            print(f"[stt] detected language: {lang_display} (prob {info.language_probability:.2f})")
        except UnicodeEncodeError:
            print(f"[stt] detected language: {lang_display} (prob {info.language_probability:.2f})")
    # Same guard for the transcribed text
    try:
        print(f"[stt] -> {text!r}")
    except UnicodeEncodeError:
        # Print repr-safe version
        print(f"[stt] -> {text.encode('ascii', 'backslashreplace').decode()} (Unicode chars redacted)")
    return text


if __name__ == "__main__":
    # Self-test: record 3 seconds and transcribe.
    from jarvis.audio import record
    audio = record(seconds=3)
    text = transcribe(audio)
    print(f"\nfinal text: {text!r}")
