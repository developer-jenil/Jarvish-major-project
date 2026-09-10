import sys
from pathlib import Path
import re

ROOT = Path(r"c:\Users\Asus\OneDrive\Desktop\major-project-jarvis")
sys.path.insert(0, str(ROOT))

from jarvis.brain import load_api_key, API_URL
import json
import urllib.request

def draft_email_with_gemini(topic: str, to_addrs: list[str]) -> tuple[str, str]:
    api_key = load_api_key()
    if not api_key:
        return f"Regarding: {topic}", topic

    recips_str = ", ".join(to_addrs)
    system_prompt = (
        "You are an elite, premium AI executive assistant. Your task is to draft a high-quality, "
        "impeccably written, context-appropriate email.\n"
        "- If writing to family (e.g. mom, dad), keep it warm, respectful, and natural.\n"
        "- If writing to a boss, professor, client, or colleague, keep it polished, articulate, and professional.\n"
        "- Write in clear English unless the topic is explicitly in Hindi.\n"
        "- Do NOT use markdown asterisks or quotes around the output.\n"
        "Output format strictly:\n"
        "SUBJECT: <Clear, concise subject line>\n"
        "BODY:\n"
        "<Full email body with greeting, message paragraphs, and sign-off>"
    )

    user_prompt = f"Compose an email.\nRecipient(s): {recips_str}\nTopic / Intent: {topic}"

    payload = json.dumps({
        "model": "google/gemini-2.5-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.6,
        "max_tokens": 600,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost",
        "X-Title": "JARVIS Major Project",
    }

    req = urllib.request.Request(API_URL, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            reply = data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Error calling API: {e}")
        return f"Regarding: {topic}", topic

    print("--- RAW GEMINI RESPONSE ---")
    print(reply)
    print("---------------------------")

    # Robust multi-line parser
    lines = reply.strip().split("\n")
    subject = ""
    body_lines = []
    in_body = False

    for line in lines:
        clean = line.strip()
        low = clean.lower()
        if low.startswith("subject:"):
            subject = re.sub(r"^subject:\s*", "", clean, flags=re.IGNORECASE).strip()
            in_body = True
            continue
        if low.startswith("body:"):
            in_body = True
            rest = re.sub(r"^body:\s*", "", clean, flags=re.IGNORECASE).strip()
            if rest:
                body_lines.append(rest)
            continue
        if in_body or subject:
            body_lines.append(clean)

    body = "\n".join(body_lines).strip()
    if not subject:
        subject = f"Regarding: {topic}"
    if not body:
        body = topic

    # Clean up placeholders like [Your Name]
    body = re.sub(r"\[Your Name\]|\[Name\]", "Aryan", body, flags=re.IGNORECASE)
    subject = re.sub(r'^["\']|["\']$', '', subject).strip()

    return subject, body

if __name__ == "__main__":
    test_cases = [
        ("I wanted to eat something spicy today", ["mom@example.com"]),
        ("I have a fever today and won't be able to come to office", ["boss@company.com"]),
        ("rain today so i cant come to college", ["prof_sharma@university.edu"]),
    ]

    for topic, recips in test_cases:
        s, b = draft_email_with_gemini(topic, recips)
        print(f"\n==========================================")
        print(f"RECIPIENT: {recips}")
        print(f"TOPIC    : {topic}")
        print(f"SUBJECT  : {s}")
        print(f"BODY     :\n{b}")
        print(f"==========================================")
