"""
jarvis/stt.py — Speech-to-text (the "ears" -> "words" step).

Provides dual-engine STT:
1. PRIMARY (Ultra-Fast): Groq Whisper Cloud (whisper-large-v3-turbo)
   - Transcribes 5s of speech in ~0.2-0.3s on Groq LPUs.
   - Uses the full 3.0 GB large-v3 architecture with 0 MB RAM / disk on PC.
   - Requires GROQ_API_KEY in .env (free at console.groq.com).

2. LOCAL FALLBACK (Offline): faster-whisper (CTranslate2)
   - Runs locally on CPU without internet.
   - Default model: "small" (~460 MB, ~3-4x faster than "medium" on CPU).
   - Automatically used when offline or if GROQ_API_KEY is not set.
"""

import io
import os
import time
import wave
import numpy as np
import requests
from faster_whisper import WhisperModel

# Default local model size. Can be overridden with JARVIS_WHISPER_MODEL environment
# variable (e.g. "small", "base", "medium").
DEFAULT_MODEL_SIZE = os.environ.get("JARVIS_WHISPER_MODEL", "small")

# Groq endpoint and model
GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_GROQ_MODEL = os.environ.get("JARVIS_GROQ_STT_MODEL", "whisper-large-v3-turbo")

# Compute type for local faster-whisper. "int8" = 8-bit integers, half RAM.
DEFAULT_COMPUTE_TYPE = "int8"

# Lazy global so local Whisper is only loaded if needed
_local_model: WhisperModel | None = None


def load_groq_api_key() -> str | None:
    """Read the Groq API key from the environment or .env file."""
    key = os.environ.get("GROQ_API_KEY")
    if key:
        return key
    try:
        from dotenv import load_dotenv
        load_dotenv()
        return os.environ.get("GROQ_API_KEY")
    except ImportError:
        return None


def get_stt_backend() -> str:
    """Return description of currently active STT backend."""
    if load_groq_api_key():
        return f"Groq Cloud Whisper ({DEFAULT_GROQ_MODEL})"
    target = os.environ.get("JARVIS_WHISPER_MODEL", DEFAULT_MODEL_SIZE)
    return f"faster-whisper local ({target})"


def _get_local_model() -> WhisperModel:
    """Load local Whisper on first call, return cached instance after that."""
    global _local_model
    if _local_model is None:
        target_model = os.environ.get("JARVIS_WHISPER_MODEL", DEFAULT_MODEL_SIZE)
        print(f"[stt] loading local Whisper '{target_model}' model...")
        try:
            _local_model = WhisperModel(
                target_model,
                device="cpu",
                compute_type=DEFAULT_COMPUTE_TYPE,
            )
        except Exception as exc:
            if target_model != "small":
                print(f"[stt] Warning: failed to load '{target_model}' ({exc}). Falling back to 'small'...")
                _local_model = WhisperModel(
                    "small",
                    device="cpu",
                    compute_type=DEFAULT_COMPUTE_TYPE,
                )
            else:
                raise exc
        print("[stt] local model ready")
    return _local_model


def _audio_to_wav_bytes(audio: np.ndarray, sample_rate: int = 16000) -> bytes:
    """Convert 1-D int16 audio array to in-memory WAV byte stream."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


_groq_session: requests.Session | None = None


def _get_groq_session() -> requests.Session:
    global _groq_session
    if _groq_session is None:
        _groq_session = requests.Session()
    return _groq_session


def transcribe_groq(audio: np.ndarray, language: str | None = None) -> str | None:
    """
    Transcribe audio via Groq Whisper Cloud API in ~0.2 seconds.
    Returns transcribed string, or None if request fails.
    """
    api_key = load_groq_api_key()
    if not api_key:
        return None

    # Quick silence check: if audio is pure silence/noise floor, return empty immediately
    if np.max(np.abs(audio)) < 250:
        return ""

    try:
        t0 = time.perf_counter()
        wav_bytes = _audio_to_wav_bytes(audio, sample_rate=16000)

        headers = {
            "Authorization": f"Bearer {api_key}",
        }
        files = {
            "file": ("audio.wav", wav_bytes, "audio/wav"),
        }
        data = {
            "model": DEFAULT_GROQ_MODEL,
            "response_format": "json",
            "temperature": 0.0,
            "prompt": "JARVIS voice assistant, English, Hindi, Hinglish conversational commands.",
        }
        if language:
            data["language"] = language

        session = _get_groq_session()
        resp = session.post(GROQ_API_URL, headers=headers, files=files, data=data, timeout=12)
        if resp.status_code == 200:
            result = resp.json()
            text = result.get("text", "").strip()
            elapsed = time.perf_counter() - t0
            print(f"[stt:groq] ({elapsed:.2f}s) -> {text!r}")
            return text
        else:
            print(f"[stt:groq] HTTP {resp.status_code}: {resp.text}")
            return None
    except Exception as exc:
        print(f"[stt:groq] request failed: {exc}")
        return None


def transcribe_local(audio: np.ndarray, language: str | None = None) -> str:
    """Transcribe audio using local faster-whisper model on CPU."""
    model = _get_local_model()

    audio_float = audio.astype(np.float32) / 32768.0
    segments, info = model.transcribe(
        audio_float,
        language=language,
        beam_size=1,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=300),
    )
    text = " ".join(segment.text.strip() for segment in segments).strip()

    if info.language:
        try:
            print(f"[stt:local] detected {info.language} (prob {info.language_probability:.2f})")
        except UnicodeEncodeError:
            pass
    try:
        print(f"[stt:local] -> {text!r}")
    except UnicodeEncodeError:
        print(f"[stt:local] -> {text.encode('ascii', 'backslashreplace').decode()} (Unicode redacted)")
    return text


def transcribe(audio: np.ndarray, language: str | None = None) -> str:
    """
    Transcribe a 1-D int16 numpy array of audio samples into text.
    Tries Groq Whisper Cloud first for ~0.2s speed; seamlessly falls back
    to local faster-whisper if Groq key is unset or network fails.
    """
    # 1. Try ultra-fast Groq Cloud Whisper if API key is present
    groq_result = transcribe_groq(audio, language=language)
    if groq_result is not None:
        return groq_result

    # 2. Fall back to local faster-whisper (small model, ~460 MB)
    return transcribe_local(audio, language=language)


if __name__ == "__main__":
    from jarvis.audio import record
    print(f"[stt] active backend: {get_stt_backend()}")
    audio = record(seconds=3)
    text = transcribe(audio)
    print(f"\nfinal text: {text!r}")

