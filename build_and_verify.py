"""
build_and_verify.py — Comprehensive build and health verification runner for JARVIS.

Runs pre-flight checks on models, environment variables, dependencies,
executes the full test suite, and verifies the built distribution package.

Usage:
    python build_and_verify.py
"""

import sys
import os
import unittest
from pathlib import Path


def print_banner(title: str):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def check_models() -> bool:
    print_banner("1. Checking Required Models & Assets")
    root = Path(__file__).resolve().parent
    all_ok = True

    # 1. Wake word
    wakeword_path = root / "models" / "wakeword" / "hey_jarvis_v0.1.onnx"
    if wakeword_path.exists():
        size_mb = wakeword_path.stat().st_size / (1024 * 1024)
        print(f"  [OK] Wake-word model: {wakeword_path.name} ({size_mb:.2f} MB)")
    else:
        print(f"  [FAIL] Wake-word model missing at {wakeword_path}")
        all_ok = False

    # 2. TTS Voice
    tts_path = root / "models" / "tts" / "hi_IN-pratham-medium.onnx"
    tts_json = root / "models" / "tts" / "hi_IN-pratham-medium.onnx.json"
    if tts_path.exists() and tts_json.exists():
        size_mb = tts_path.stat().st_size / (1024 * 1024)
        print(f"  [OK] Piper TTS voice: {tts_path.name} ({size_mb:.2f} MB)")
    else:
        print(f"  [FAIL] TTS voice model missing at {tts_path}")
        all_ok = False

    # 3. Whisper STT cache
    hf_cache = Path(os.path.expanduser("~/.cache/huggingface/hub"))
    whisper_cached = False
    if hf_cache.exists():
        for d in hf_cache.glob("models--Systran--faster-whisper-*"):
            if (d / "snapshots").exists():
                print(f"  [OK] Whisper STT cached: {d.name}")
                whisper_cached = True
    if not whisper_cached:
        print("  [WARN] No cached Whisper model found in ~/.cache/huggingface/hub.")

    # 4. Contacts
    contacts_path = root / "resources" / "contacts.csv"
    if contacts_path.exists():
        print(f"  [OK] Contacts resource: {contacts_path.name}")
    else:
        print(f"  [FAIL] Contacts file missing at {contacts_path}")
        all_ok = False

    return all_ok


def check_environment() -> bool:
    print_banner("2. Checking Environment & API Credentials")
    root = Path(__file__).resolve().parent
    env_file = root / ".env"
    if not env_file.exists():
        print("  [WARN] No .env file found. Reading system environment.")
    else:
        print("  [OK] .env file present.")

    from jarvis import brain
    key = brain.load_api_key()
    if key and key.startswith("sk-"):
        print(f"  [OK] OpenRouter API Key configured ({key[:10]}...{key[-4:]})")
    else:
        print("  [WARN] OPENROUTER_API_KEY not set or invalid format.")

    email_user = os.environ.get("EMAIL_USER")
    email_pwd = os.environ.get("EMAIL_APP_PASSWORD")
    if email_user and email_pwd:
        print(f"  [OK] Email credentials configured ({email_user})")
    else:
        print("  [INFO] Email credentials optional: not configured in .env")

    return True


def run_test_suite() -> bool:
    print_banner("3. Running Automated Test Suite")
    root = Path(__file__).resolve().parent
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(root / "tests"), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


def check_build_distribution() -> bool:
    print_banner("4. Checking Build Distribution Artifacts")
    root = Path(__file__).resolve().parent
    dist_dir = root / "dist"
    if not dist_dir.exists():
        print("  [FAIL] dist/ folder does not exist. Run 'python -m build' to build.")
        return False

    wheels = list(dist_dir.glob("*.whl"))
    tarballs = list(dist_dir.glob("*.tar.gz"))

    if wheels and tarballs:
        for w in wheels:
            print(f"  [OK] Wheel package: {w.name} ({w.stat().st_size / (1024*1024):.2f} MB)")
        for t in tarballs:
            print(f"  [OK] Source archive: {t.name} ({t.stat().st_size / (1024*1024):.2f} MB)")
        return True
    else:
        print("  [FAIL] Missing .whl or .tar.gz in dist/")
        return False


def main():
    print_banner("JARVIS ASSISTANT — BUILD & HEALTH VERIFICATION")
    models_ok = check_models()
    env_ok = check_environment()
    tests_ok = run_test_suite()
    build_ok = check_build_distribution()

    print_banner("VERIFICATION SUMMARY")
    print(f"  Models & Assets:       {'PASS' if models_ok else 'FAIL'}")
    print(f"  Environment & Keys:    {'PASS' if env_ok else 'FAIL'}")
    print(f"  Automated Test Suite:  {'PASS' if tests_ok else 'FAIL'}")
    print(f"  Distribution Build:    {'PASS' if build_ok else 'FAIL'}")
    print("=" * 60)

    if models_ok and env_ok and tests_ok and build_ok:
        print("\n  >> ALL SYSTEMS OPERATIONAL: JARVIS IS FULLY BUILT & READY <<\n")
        sys.exit(0)
    else:
        print("\n  >> BUILD VERIFICATION FAILED: Review the logs above <<\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
