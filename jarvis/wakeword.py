"""
jarvis/wakeword.py — Wake-word detection (the "always-listening ear").

This is the part that lets the assistant sleep quietly until you say the
magic phrase "Hey Jarvis". Only THEN does it wake up, record your command,
and think about a reply. Without this, the assistant would try to answer
every random noise in the room — annoying and wasteful.

WHAT IS A WAKE WORD?
- A wake word (or "hotword") is a short phrase a device constantly listens
  for, e.g. "Alexa", "Hey Google", "Hey Siri". Detecting it runs on a tiny,
  fast model so it can run all the time using almost no CPU.

HOW DOES openWakeWord WORK? (three small models, chained)
1. melspectrogram  — turns raw audio into a "picture" of its frequencies.
2. embedding       — turns that picture into a compact list of numbers.
3. "hey jarvis"    — a tiny classifier that outputs a score 0.0–1.0 for
                     "how much did that sound like 'hey jarvis'?".
We feed audio in small 80 ms frames. When the score crosses a threshold
(default 0.5), we say the wake word was heard.

WHY IS THIS LOCAL AND FREE?
- All three models are small ONNX files that run on the CPU with
  onnxruntime (already installed for Whisper). No internet, no API key,
  no cost. This is a strong point to mention in the project review.

WHO OWNS THIS?
- The detection *code* here is core assistant logic.
- The model *files* are an external resource (Member 3) — see
  resources/models_manifest.md. They are gitignored (large binaries) and
  fetched once with:  python -m jarvis.wakeword --download

HOW TO TEST:
    python -m jarvis.wakeword --download   # one-time: fetch model files
    python -m jarvis.wakeword              # live mic test — say "Hey Jarvis"
    python -m jarvis.wakeword --selftest   # no mic needed (CI-safe)
"""

from pathlib import Path

import numpy as np

# --- Configuration -------------------------------------------------------

# openWakeWord processes audio in fixed 80 ms frames. At 16 kHz that is
# exactly 1280 samples. Do not change this — the models were trained on it.
SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280  # 80 ms * 16000 Hz

# The score (0.0–1.0) above which we declare "wake word heard". 0.5 is the
# openWakeWord default. Raise it (e.g. 0.6) if you get false triggers;
# lower it (e.g. 0.4) if it is not catching your voice.
DEFAULT_THRESHOLD = 0.5

# The prebuilt model we use. openWakeWord ships this exact one for free.
WAKEWORD_NAME = "hey jarvis"

# Project-local copy of the model file (Member 3's external resource).
# If present we load it by path so the project is self-contained; if not,
# we fall back to openWakeWord's bundled copy inside the venv.
PROJECT_MODEL_PATH = (
    Path(__file__).resolve().parent.parent
    / "models" / "wakeword" / "hey_jarvis_v0.1.onnx"
)

# Lazy global so we load the model only once (loading takes ~1 sec).
_model = None


def download() -> None:
    """Download the wake-word model files (one-time setup).

    Fetches the melspectrogram, embedding, VAD, and "hey jarvis" models
    from the official openWakeWord GitHub release into the venv package,
    then copies the "hey jarvis" model into the project's models/wakeword/
    folder so the project owns its own copy.
    """
    import shutil
    import openwakeword.utils as u

    print("[wakeword] downloading model files (a few MB, one time)...")
    u.download_models(["hey_jarvis"])

    # Copy the wakeword model into the project so it is self-contained.
    import openwakeword
    pkg_models = Path(openwakeword.__file__).parent / "resources" / "models"
    src = pkg_models / "hey_jarvis_v0.1.onnx"
    if src.exists():
        PROJECT_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, PROJECT_MODEL_PATH)
        print(f"[wakeword] copied model to {PROJECT_MODEL_PATH}")
    print("[wakeword] download complete.")


def _get_model():
    """Load the openWakeWord model on first call; cache it after that."""
    global _model
    if _model is None:
        from openwakeword.model import Model

        # Prefer the project-local model file; else use the bundled name.
        if PROJECT_MODEL_PATH.exists():
            model_arg = str(PROJECT_MODEL_PATH)
            print(f"[wakeword] loading model from {PROJECT_MODEL_PATH.name}")
        else:
            model_arg = WAKEWORD_NAME
            print(f"[wakeword] loading bundled '{WAKEWORD_NAME}' model")
            print("[wakeword] (if this fails, run: python -m jarvis.wakeword --download)")

        try:
            _model = Model(wakeword_models=[model_arg], inference_framework="onnx")
        except Exception as e:
            raise RuntimeError(
                "Could not load the wake-word model. Run this once to fetch "
                "the model files:\n    python -m jarvis.wakeword --download\n"
                f"(original error: {e})"
            ) from e
        print("[wakeword] ready")
    return _model


def _score(preds: dict) -> float:
    """Pull the single wake-word score out of a predict() result dict.

    The dict key depends on how the model was loaded ('hey jarvis' vs
    'hey_jarvis_v0.1'), so we just take the highest score present — there
    is only one model loaded, so this is unambiguous.
    """
    return max((float(v) for v in preds.values()), default=0.0)


def detect(frame: np.ndarray) -> float:
    """Feed ONE 80 ms audio frame to the model, return the wake-word score.

    Args:
        frame: 1-D int16 numpy array of length FRAME_SAMPLES (1280).

    Returns:
        A score 0.0–1.0. Compare against DEFAULT_THRESHOLD to decide
        whether the wake word was heard.

    This is the low-level building block. Most callers want
    listen_for_wakeword() below, which handles the microphone for you.
    """
    model = _get_model()
    preds = model.predict(frame)
    return _score(preds)


def listen_for_wakeword(threshold: float = DEFAULT_THRESHOLD) -> bool:
    """Block until the user says "Hey Jarvis", then return True.

    Opens the microphone and streams 80 ms frames through the model until
    one crosses `threshold`. This is what main.py calls to "sleep" until
    the user wants attention.

    Returns:
        True when the wake word is detected. (It only returns on success;
        press Ctrl+C to stop waiting.)
    """
    import sounddevice as sd

    # Warm up the model BEFORE we open the mic, so the first frames are not
    # delayed by the ~1 sec load time.
    model = _get_model()
    model.reset()  # clear any leftover state from a previous wake

    print(f"[wakeword] listening for '{WAKEWORD_NAME}'... (Ctrl+C to quit)")

    # A blocking input stream: we pull frames ourselves in a simple loop.
    # blocksize=FRAME_SAMPLES means each read() gives us exactly one frame.
    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=FRAME_SAMPLES,
    ) as stream:
        while True:
            # read() returns (data, overflowed). data is shape (1280, 1).
            data, _overflowed = stream.read(FRAME_SAMPLES)
            frame = data.flatten()  # -> shape (1280,)
            score = _score(model.predict(frame))
            if score >= threshold:
                print(f"[wakeword] detected! (score {score:.2f})")
                return True


if __name__ == "__main__":
    import sys

    args = set(sys.argv[1:])

    if "--download" in args:
        # One-time setup: fetch the model files.
        download()

    elif "--selftest" in args:
        # CI-safe test: no microphone needed. Feed synthetic audio and
        # confirm the model loads and returns a sane (low) score.
        print("[selftest] loading model and scoring silence...")
        silence = np.zeros(FRAME_SAMPLES, dtype=np.int16)
        score = detect(silence)
        print(f"[selftest] silence score = {score:.4f} (should be near 0.0)")
        noise = (np.random.randn(FRAME_SAMPLES) * 500).astype(np.int16)
        score2 = detect(noise)
        print(f"[selftest] noise score   = {score2:.4f} (should be low)")
        assert 0.0 <= score <= 1.0, "score out of range"
        print("[selftest] PASS — wake-word model works.")

    else:
        # Live microphone test: say "Hey Jarvis" and watch it trigger.
        try:
            listen_for_wakeword()
            print("Wake word heard — in the real app, Jarvis would now listen "
                  "for your command.")
        except KeyboardInterrupt:
            print("\n[wakeword] stopped.")
