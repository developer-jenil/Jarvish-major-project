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
  small   ~460 MB, balanced, ~82% accuracy  <-- our default
  medium  ~1.5 GB, slow,     ~86% accuracy
  large   ~3.0 GB, slowest,  ~89% accuracy

For a CPU-only PC with 16 GB RAM, "small" is the sweet spot. We can
upgrade to "medium" in Phase 7 if you want better Hindi.
"""

import numpy as np
from faster_whisper import WhisperModel

# Default model size. Change to "medium" or "large-v3" if you want more
# accuracy and don't mind the extra load time.
DEFAULT_MODEL_SIZE = "small"

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
        print(f"[stt] loading Whisper '{DEFAULT_MODEL_SIZE}' model...")
        print("[stt] (first run downloads the model — ~460 MB, may take a few minutes)")
        _model = WhisperModel(
            DEFAULT_MODEL_SIZE,
            device="cpu",              # change to "cuda" if you have an NVIDIA GPU
            compute_type=DEFAULT_COMPUTE_TYPE,
        )
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
        print(f"[stt] detected language: {info.language} (prob {info.language_probability:.2f})")
    print(f"[stt] -> {text!r}")
    return text


if __name__ == "__main__":
    # Self-test: record 3 seconds and transcribe.
    from jarvis.audio import record
    audio = record(seconds=3)
    text = transcribe(audio)
    print(f"\nfinal text: {text!r}")
