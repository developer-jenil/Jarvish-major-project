"""
jarvis/brain.py — The "brain" of the assistant (LLM integration).

This module connects the assistant to a cloud Large Language Model (LLM)
through the OpenRouter API. OpenRouter is a single gateway that can talk to
many models (OpenAI, Anthropic, Meta Llama, etc.) using one common format
called the "OpenAI-compatible Chat Completions API".

WHAT IS AN LLM?
- An LLM is an AI model that takes text in and produces text out.
- We send it a list of "messages" (a conversation) and it replies with the
  next message. That reply is what the assistant "says".

WHAT IS AN API?
- API = Application Programming Interface. It's just a way for our Python
  program to ask another computer (OpenRouter's server) to do work for us
  over the internet.
- We send an HTTP request (like a web page request) with JSON data, and we
  get a JSON response back. This file uses only the Python standard library
  (urllib) so it runs with NO extra packages installed.

WHY IS THIS MEMBER 2's PART?
- Member 2 owns "API and AI model integration". This file IS that integration:
  it loads the API key, builds the request, calls the model, and returns the
  text. Member 2 should be able to explain every function below.

HOW TO RUN THE SELF-TEST:
    python -m jarvis.brain
(It will either call the real model if OPENROUTER_API_KEY is set, or print a
safe offline message so the code can still be shown without a key.)
"""

import json
import os
import urllib.request
import urllib.error

# --- Configuration -------------------------------------------------------

# OpenRouter's Chat Completions endpoint (OpenAI-compatible format).
API_URL = "https://openrouter.ai/api/v1/chat/completions"

# The model to use. OpenRouter lets you swap this freely. Examples:
#   "openai/gpt-4o-mini"                 (cheap, fast, strong — paid)
#   "anthropic/claude-3.5-haiku"         (fast, cheap — paid)
#   "meta-llama/llama-3.1-8b-instruct"   (paid, free tier elsewhere)
#   "tencent/hy3:free"                   (FREE, fast, good Hinglish — our default)
#
# DEFAULT: tencent/hy3:free
#   Chosen for this project because it is 100% free (no credit limit), very
#   fast (~2s first-token on a short reply), and handles Hindi+English
#   (Hinglish) naturally — exactly what a spoken assistant needs. Swap the
#   line below to change models; nothing else needs editing.
DEFAULT_MODEL = "tencent/hy3:free"

# The "system prompt" tells the model who it is and how to behave.
SYSTEM_PROMPT = (
    "You are JARVIS, a helpful Hindi + English (Hinglish) voice assistant "
    "running on a Windows PC. Keep replies short and spoken-friendly so they "
    "sound natural when read aloud by text-to-speech."
)


def load_api_key() -> str | None:
    """Read the OpenRouter key from the environment or a .env file.

    The key must NEVER be committed to git. It lives in a .env file
    (gitignored) or in your system environment. We try python-dotenv only
    if it happens to be installed; otherwise we just read the environment.
    """
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    # Try to load .env if the helper library is available.
    try:
        from dotenv import load_dotenv
        load_dotenv()
        return os.environ.get("OPENROUTER_API_KEY")
    except ImportError:
        return None


def ask(user_text: str, model: str = DEFAULT_MODEL, history=None) -> str:
    """Send one user message to the LLM and return its reply as text.

    Args:
        user_text: what the user said (already transcribed by STT).
        model:     which model to call (see DEFAULT_MODEL for options).
        history:   optional list of previous {role, content} messages, so the
                   assistant can remember context within a conversation.

    Returns:
        The assistant's reply text, or an error message string.
    """
    api_key = load_api_key()
    if not api_key:
        return "[brain] No OPENROUTER_API_KEY set — cannot call the model."

    # Build the conversation: system prompt first, then any history, then
    # the new user message.
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    # The body we send, encoded as JSON bytes (HTTP requires bytes).
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.7,   # 0 = very strict, 1 = more creative
        "max_tokens": 200,    # keep replies short for spoken output
    }).encode("utf-8")

    # HTTP headers: who we are + our API key (the "Bearer" token).
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost",   # OpenRouter wants a referer
        "X-Title": "JARVIS Major Project",
    }

    req = urllib.request.Request(API_URL, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # The reply text lives at choices[0].message.content.
            return data["choices"][0]["message"]["content"].strip()
    except urllib.error.URLError as e:
        return f"[brain] API call failed: {e}"


if __name__ == "__main__":
    # Self-test: either call the real model or show the offline message.
    test_question = "Hey Jarvis, what time is it?"
    print(f"[brain] asking: {test_question!r}")
    reply = ask(test_question)
    print(f"[brain] reply : {reply}")
