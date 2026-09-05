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
#   "openai/gpt-4o-mini"                      (cheap, fast, strong — paid)
#   "anthropic/claude-3.5-haiku"              (fast, cheap — paid)
#   "meta-llama/llama-3.1-8b-instruct"        (paid, free tier elsewhere)
#   "google/gemma-2-9b-it:free"               (FREE, good Hindi+English)
#   "meta-llama/llama-3.1-8b-instruct:free"   (FREE, decent Hinglish)
#   "mistralai/mistral-7b-instruct:free"      (FREE, less Hindi)
#   "microsoft/phi-3-mini-128k-instruct:free" (FREE, smaller context)
#
# DEFAULT: meta-llama/llama-3.1-8b-instruct
#   This model works with the current API key and handles Hindi+English
#   (Hinglish) well. Falls back to other models if it fails.
#   Note: The :free suffix models on OpenRouter are currently returning 404;
#   the non-:free versions work if the account has credits.
DEFAULT_MODEL = "meta-llama/llama-3.1-8b-instruct"
FALLBACK_MODELS = [
    "openai/gpt-3.5-turbo",
    "google/gemma-7b-it",
    "mistralai/mistral-7b-instruct",
    "meta-llama/llama-3-8b-instruct",
]

import datetime

# The "system prompt" tells the model who it is and how to behave with live system clock context.
def build_system_prompt() -> str:
    now = datetime.datetime.now()
    time_str = now.strftime("%I:%M %p")
    date_str = now.strftime("%A, %d %B %Y")
    return (
        "You are JARVIS, a highly capable, human-like voice assistant running on a Windows PC.\n"
        "[REAL-TIME SYSTEM INFO]\n"
        f"- Current Local Time: {time_str}\n"
        f"- Current Date: {date_str}\n"
        "- Platform: Windows PC\n\n"
        "Follow these strict spoken voice guidelines:\n"
        "1. Speak directly in natural conversational Hinglish (Hindi + English written in Latin alphabet) or English as appropriate.\n"
        "2. ALWAYS provide accurate, truthful facts. If asked about the current time or date, always refer to the REAL-TIME SYSTEM INFO above.\n"
        "3. NEVER include translations in parentheses or brackets (e.g. NEVER write 'Namaste (Hello)' or 'madad (help)'). Speak your thought directly once.\n"
        "4. NEVER use markdown formatting, asterisks, hashes, or bullet points (*, #, -). Your text is read out loud by text-to-speech.\n"
        "5. Keep your replies short, natural, friendly, and conversational (1 to 3 sentences maximum), like a real smart assistant.\n"
        "6. CRITICAL: You are a conversation model and do not directly open Windows applications. If asked to open an app, instruct the user to say 'open <app_name>' or '<app_name> kholo'. NEVER claim that you opened an application."
    )

SYSTEM_PROMPT = build_system_prompt()


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

    # Build the conversation: system prompt with live clock first, then any history, then
    # the new user message.
    messages = [{"role": "system", "content": build_system_prompt()}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    # Try primary model, then fallback chain if it fails (404, 401, 500, etc.)
    models_to_try = [model]
    if model == DEFAULT_MODEL:
        models_to_try.extend(FALLBACK_MODELS)

    for attempt_model in models_to_try:
        # The body we send, encoded as JSON bytes (HTTP requires bytes).
        payload = json.dumps({
            "model": attempt_model,
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
        except urllib.error.HTTPError as e:
            # If primary model fails, log and try fallback (if any left).
            print(f"[brain] model {attempt_model!r} failed: HTTP {e.code} — {e.reason}")
            if attempt_model == models_to_try[-1]:
                return f"[brain] All models failed (last error: HTTP {e.code})"
            continue
        except urllib.error.URLError as e:
            return f"[brain] API call failed: {e}"

    return "[brain] All models failed"


if __name__ == "__main__":
    # Self-test: either call the real model or show the offline message.
    test_question = "Hey Jarvis, what time is it?"
    print(f"[brain] asking: {test_question!r}")
    reply = ask(test_question)
    print(f"[brain] reply : {reply}")
