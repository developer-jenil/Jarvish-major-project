"""
server.py — Flask Web API and Dashboard Server for JARVIS.

Bridges the web frontend to JARVIS skills, LLM brain, TTS, STT, and wake-word.
"""

from __future__ import annotations

import csv
import io
import os
import queue
import threading
import time
import urllib.parse
import wave
from pathlib import Path

import numpy as np
from flask import Flask, jsonify, render_template, request, Response, send_file

from jarvis import brain
from jarvis.tts import synthesize, speak
from jarvis.skills.open_app import try_open_app
from jarvis.skills.whatsapp import try_whatsapp, find_contact
from jarvis.skills.email import try_send_email, find_emails
from jarvis.skills.web_search import try_web_search, search_web

# --- Project Paths ---
ROOT_DIR = Path(__file__).resolve().parent
CONTACTS_PATH = ROOT_DIR / "resources" / "contacts.csv"

app = Flask(
    __name__,
    template_folder=str(ROOT_DIR / "templates"),
    static_folder=str(ROOT_DIR / "static"),
)
app.json.sort_keys = False

# Shared in-memory conversation history for web session
_conversation_history: list[dict[str, str]] = []
MAX_HISTORY_TURNS = 10

# Threading state for background wakeword
_wakeword_running = False
_wakeword_thread: threading.Thread | None = None
_event_queue: queue.Queue[dict] = queue.Queue(maxsize=100)


def _load_contacts_list() -> list[dict[str, str]]:
    if not CONTACTS_PATH.exists():
        return []
    contacts = []
    with open(CONTACTS_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            clean_row = {}
            for k, v in row.items():
                key_str = str(k).strip() if k is not None else ""
                if key_str:
                    clean_row[key_str] = v.strip() if v is not None else ""
            if clean_row.get("name"):
                contacts.append(clean_row)
    return contacts


def _save_contacts_list(contacts: list[dict[str, str]]) -> None:
    fieldnames = ["name", "phone", "whatsapp_id", "email", "relation", "notes"]
    with open(CONTACTS_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(contacts)


# --- Background Wake-word Worker ---
def _wakeword_worker():
    global _wakeword_running
    try:
        from jarvis.wakeword import listen_for_wakeword
    except Exception as exc:
        print(f"[server] wakeword import failed: {exc}")
        _wakeword_running = False
        return

    print("[server] background wake-word listener active")
    while _wakeword_running:
        try:
            detected = listen_for_wakeword()
            if detected and _wakeword_running:
                _event_queue.put({"type": "wakeword", "message": "Hey Jarvis detected!"})
        except Exception as e:
            time.sleep(1)
    print("[server] background wake-word listener stopped")


# --- Routes ---

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status", methods=["GET"])
def get_status():
    api_key = brain.load_api_key()
    has_brain = bool(api_key and api_key.startswith("sk-"))
    has_email = bool(os.environ.get("EMAIL_USER") and os.environ.get("EMAIL_APP_PASSWORD"))

    return jsonify({
        "online": True,
        "brain_connected": has_brain,
        "email_configured": has_email,
        "wakeword_active": _wakeword_running,
        "models": {
            "wakeword": "hey_jarvis_v0.1.onnx",
            "tts": "hi_IN-pratham-medium.onnx",
            "stt": f"faster-whisper ({os.environ.get('JARVIS_WHISPER_MODEL', 'small')})",
            "brain": brain.DEFAULT_MODEL,
        }
    })


@app.route("/api/command", methods=["POST"])
def execute_command():
    global _conversation_history
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    should_speak = bool(data.get("speak", False))

    if not text:
        return jsonify({"success": False, "error": "No command text provided"}), 400

    # 1. Check Skills in priority order
    for skill_name, try_fn in (
        ("open-app", try_open_app),
        ("whatsapp", try_whatsapp),
        ("email", try_send_email),
        ("web-search", try_web_search),
    ):
        handled, skill_msg = try_fn(text)
        if handled:
            _conversation_history.append({"role": "user", "content": text})
            _conversation_history.append({"role": "assistant", "content": skill_msg})
            if len(_conversation_history) > MAX_HISTORY_TURNS:
                _conversation_history = _conversation_history[-MAX_HISTORY_TURNS:]

            if should_speak:
                try:
                    speak(skill_msg, blocking=False)
                except Exception as e:
                    print(f"[server] tts playback warning: {e}")

            return jsonify({
                "success": True,
                "skill": skill_name,
                "user_text": text,
                "reply": skill_msg,
                "audio_url": f"/api/tts?text={urllib.parse.quote(skill_msg)}"
            })

    # 2. LLM Brain
    reply = brain.ask(text, history=_conversation_history)
    if reply.startswith("[brain]"):
        friendly_reply = "Sorry, my thinking brain is currently offline or unreachable."
    else:
        friendly_reply = reply

    _conversation_history.append({"role": "user", "content": text})
    _conversation_history.append({"role": "assistant", "content": friendly_reply})
    if len(_conversation_history) > MAX_HISTORY_TURNS:
        _conversation_history = _conversation_history[-MAX_HISTORY_TURNS:]

    if should_speak:
        try:
            speak(friendly_reply, blocking=False)
        except Exception as e:
            print(f"[server] tts playback warning: {e}")

    return jsonify({
        "success": True,
        "skill": "brain",
        "user_text": text,
        "reply": friendly_reply,
        "audio_url": f"/api/tts?text={urllib.parse.quote(friendly_reply)}"
    })


@app.route("/api/skills/open-app", methods=["POST"])
def skill_open_app():
    data = request.get_json(force=True) or {}
    app_name = data.get("app", "").strip()
    query = data.get("query")
    dry_run = bool(data.get("dry_run", False))

    if not app_name:
        return jsonify({"success": False, "error": "App name required"}), 400

    cmd = f"open {app_name}"
    if query:
        cmd += f" and search for {query}"

    handled, msg = try_open_app(cmd, dry_run=dry_run)
    return jsonify({"success": handled, "message": msg})


@app.route("/api/skills/whatsapp", methods=["POST"])
def skill_whatsapp():
    data = request.get_json(force=True) or {}
    recipient = data.get("recipient", "").strip()
    message = data.get("message", "").strip()
    dry_run = bool(data.get("dry_run", False))

    if not recipient:
        return jsonify({"success": False, "error": "Recipient required"}), 400

    cmd = f"send whatsapp to {recipient}"
    if message:
        cmd += f" saying {message}"

    handled, msg = try_whatsapp(cmd, dry_run=dry_run)
    return jsonify({"success": handled, "message": msg})


@app.route("/api/skills/email", methods=["POST"])
def skill_email():
    data = request.get_json(force=True) or {}
    to = data.get("to", "").strip()
    topic = data.get("topic", "").strip()
    dry_run = bool(data.get("dry_run", False))

    if not to:
        return jsonify({"success": False, "error": "Recipient required"}), 400

    cmd = f"send email to {to}"
    if topic:
        cmd += f" about {topic}"

    handled, msg = try_send_email(cmd, dry_run=dry_run)
    return jsonify({"success": handled, "message": msg})


@app.route("/api/skills/search", methods=["POST"])
def skill_search():
    data = request.get_json(force=True) or {}
    query = data.get("query", "").strip()
    max_res = int(data.get("max_results", 4))

    if not query:
        return jsonify({"success": False, "error": "Query required"}), 400

    results = search_web(query, max_results=max_res)
    return jsonify({
        "success": True,
        "query": query,
        "results": results,
    })


@app.route("/api/contacts", methods=["GET", "POST"])
def handle_contacts():
    if request.method == "GET":
        return jsonify({"contacts": _load_contacts_list()})

    data = request.get_json(force=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"success": False, "error": "Name required"}), 400

    contacts = _load_contacts_list()
    # Check if contact already exists
    for row in contacts:
        if row.get("name", "").lower() == name.lower():
            row["whatsapp_id"] = data.get("whatsapp_id", row.get("whatsapp_id", ""))
            row["email"] = data.get("email", row.get("email", ""))
            row["relation"] = data.get("relation", row.get("relation", ""))
            row["notes"] = data.get("notes", row.get("notes", ""))
            _save_contacts_list(contacts)
            return jsonify({"success": True, "message": f"Updated contact {name}", "contacts": contacts})

    contacts.append({
        "name": name,
        "whatsapp_id": data.get("whatsapp_id", "").strip(),
        "email": data.get("email", "").strip(),
        "relation": data.get("relation", "").strip(),
        "notes": data.get("notes", "").strip(),
    })
    _save_contacts_list(contacts)
    return jsonify({"success": True, "message": f"Added contact {name}", "contacts": contacts})


@app.route("/api/tts", methods=["GET", "POST"])
def get_tts_audio():
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        text = data.get("text", "")
    else:
        text = request.args.get("text", "")

    if not text or not text.strip():
        return jsonify({"error": "No text provided"}), 400

    try:
        audio, sample_rate = synthesize(text)
        if len(audio) == 0:
            return jsonify({"error": "Empty audio generated"}), 400

        # Scale float32 [-1, 1] to int16 PCM
        int16_samples = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(int16_samples.tobytes())

        wav_buffer.seek(0)
        return send_file(
            wav_buffer,
            mimetype="audio/wav",
            as_attachment=False,
            download_name="speech.wav"
        )
    except Exception as exc:
        print(f"[server] TTS error: {exc}")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/wakeword/toggle", methods=["POST"])
def toggle_wakeword():
    global _wakeword_running, _wakeword_thread
    data = request.get_json(force=True) or {}
    enable = data.get("enable")

    if enable is None:
        _wakeword_running = not _wakeword_running
    else:
        _wakeword_running = bool(enable)

    if _wakeword_running:
        if _wakeword_thread is None or not _wakeword_thread.is_alive():
            _wakeword_thread = threading.Thread(target=_wakeword_worker, daemon=True)
            _wakeword_thread.start()
    return jsonify({"wakeword_active": _wakeword_running})


@app.route("/api/events")
def events():
    def event_stream():
        while True:
            try:
                event = _event_queue.get(timeout=20)
                yield f"data: {json.dumps(event)}\n\n"
            except queue.Empty:
                # Keep-alive heartbeat
                yield ": keepalive\n\n"

    import json
    return Response(event_stream(), mimetype="text/event-stream")


def run_server(host="127.0.0.1", port=5000, debug=False):
    print(f"\n==================================================")
    print(f"  JARVIS Web Dashboard Server")
    print(f"  Access UI at: http://localhost:{port}")
    print(f"==================================================\n")
    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    run_server()
