"""Imtihan Saathi - exam practice from your own textbook chapter.

Flask backend that keeps the Gemini API key on the server.
Run locally:  python app.py
Production:   gunicorn app:app
"""
import base64
import json
import os
import re
import time
from collections import defaultdict, deque

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "20"))
MAX_CHARS = 20000
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
ALLOWED_MIME = {"application/pdf", "image/png", "image/jpeg", "image/webp"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB uploads


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


# ---------------------------------------------------------------- rate limit
_hits = defaultdict(deque)


@app.before_request
def limit_requests():
    if not request.path.startswith("/api/"):
        return
    ip = (request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown").split(",")[0].strip()
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise ApiError("Too many requests. Please wait a minute and try again.", 429)
    q.append(now)


@app.errorhandler(ApiError)
def handle_api_error(e):
    return jsonify({"error": e.message}), e.status


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "File is too large (max 16 MB)."}), 413


# ------------------------------------------------------------------- Gemini
def call_gemini(parts, as_json=True):
    if not API_KEY:
        raise ApiError("Server is missing GEMINI_API_KEY. See the README.", 500)
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.4 if as_json else 0.1},
    }
    if as_json:
        body["generationConfig"]["responseMimeType"] = "application/json"
    try:
        r = requests.post(
            GEMINI_URL.format(model=MODEL),
            headers={"x-goog-api-key": API_KEY, "Content-Type": "application/json"},
            json=body,
            timeout=90,
        )
    except requests.RequestException:
        raise ApiError("Could not reach Gemini. Please try again.", 502)
    if r.status_code != 200:
        try:
            msg = r.json()["error"]["message"]
        except Exception:
            msg = f"Gemini request failed ({r.status_code})"
        raise ApiError(msg, 502)
    try:
        cand = r.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in cand)
    except (KeyError, IndexError):
        raise ApiError("Gemini returned no answer (the content may have been blocked).", 502)
    if not as_json:
        return text
    try:
        return json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip())
    except json.JSONDecodeError:
        raise ApiError("Could not read the AI response. Please try again.", 502)


def lang_rule(lang):
    if lang == "Urdu":
        return ("Write all explanations and feedback in clear Urdu script (اردو). "
                "Keep scientific/technical terms in English in brackets where helpful.")
    if lang == "Roman Urdu":
        return ("Write all explanations and feedback in Roman Urdu (Urdu in Latin letters, "
                "as Pakistani students write), simple and friendly. Keep technical terms in English.")
    return "Write all explanations and feedback in simple English suitable for a Pakistani student."


def clean(v, n=80):
    return re.sub(r"[\r\n]+", " ", str(v or "")).strip()[:n]


def context_line(d):
    """Optional board / subject / book / chapter name typed by the student."""
    bits = []
    for label, key in (("Board", "board"), ("Subject", "subject"), ("Book", "book"), ("Chapter", "chapter_name")):
        v = clean(d.get(key))
        if v:
            bits.append(f"{label}: {v}")
    return ("Context - " + "; ".join(bits) + ".\n") if bits else ""


def get_chapter(data):
    chapter = (data.get("chapter") or "").strip()[:MAX_CHARS]
    if len(chapter) < 200:
        raise ApiError("Please add a longer chapter excerpt (at least a few paragraphs).")
    return chapter


# ------------------------------------------------------------------- routes
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return {"ok": True, "key_configured": bool(API_KEY), "model": MODEL}


@app.post("/api/extract")
def extract():
    f = request.files.get("file")
    if not f:
        raise ApiError("No file uploaded.")
    mime = f.mimetype
    if mime not in ALLOWED_MIME:
        raise ApiError("Upload a PDF, PNG, JPG or WEBP file.")
    data = base64.b64encode(f.read()).decode()
    text = call_gemini(
        [
            {"inlineData": {"mimeType": mime, "data": data}},
            {"text": "Transcribe the textbook content in this file as plain text, keeping headings, "
                     "definitions and lists. Keep the original language. Output only the text."},
        ],
        as_json=False,
    )
    return {"text": text.strip()}


@app.post("/api/generate")
def generate():
    d = request.get_json(silent=True) or {}
    chapter = get_chapter(d)
    level = "Inter (11th/12th)" if "Inter" in str(d.get("level", "")) else "Matric (9th/10th)"
    kinds = {
        "mix": "a mix of MCQs (4 options), short questions (2-3 lines) and long questions (a paragraph)",
        "mcq": "only MCQs with 4 options",
        "short": "only short questions answerable in 2-3 lines",
        "long": "only long questions answerable in a detailed paragraph",
    }.get(d.get("type"), "a mix of MCQs, short and long questions")
    try:
        count = max(1, min(15, int(d.get("count", 5))))
    except (TypeError, ValueError):
        count = 5
    prompt = (
        f"You are an exam setter for Pakistani board exams ({level}). {context_line(d)}Using ONLY the chapter below, "
        f"write {count} practice questions: {kinds}. Questions must be in English, in board-exam style, "
        "and answerable from the chapter. Return ONLY a JSON array. Each item: "
        '{"type":"mcq"|"short"|"long","q":string,"options":[4 strings, mcq only],'
        '"marks":number,"key":"the correct answer / key points taken from the chapter"}.'
        f"\n\nCHAPTER:\n{chapter}"
    )
    out = call_gemini([{"text": prompt}])
    questions = out if isinstance(out, list) else out.get("questions", [])
    return {"questions": questions}


@app.post("/api/check")
def check():
    d = request.get_json(silent=True) or {}
    chapter = get_chapter(d)
    q = d.get("question") or {}
    answer = str(d.get("answer", "")).strip()[:4000]
    if not answer:
        raise ApiError("Please write an answer first.")
    marks = q.get("marks") or 1
    options = q.get("options")
    prompt = (
        "You are a kind but strict Pakistani board examiner. Check the student's answer ONLY against "
        f"the chapter text. {context_line(d)}{lang_rule(d.get('lang'))}\n"
        'Return ONLY JSON: {"score":number,"out_of":' + str(marks) + ',"level":"good"|"partial"|"wrong",'
        '"right":"what the student got right","missing":"what is wrong or missing, with the chapter\'s facts",'
        '"model_answer":"a model answer in 2-5 sentences grounded in the chapter","tip":"one short exam tip"}.\n\n'
        f"QUESTION: {q.get('q', '')}\n"
        + (f"OPTIONS: {' | '.join(map(str, options))}\n" if options else "")
        + f"KEY: {q.get('key', '')}\nSTUDENT ANSWER: {answer}\n\nCHAPTER:\n{chapter}"
    )
    return call_gemini([{"text": prompt}])


if __name__ == "__main__":
    app.run(debug=True, port=int(os.getenv("PORT", "5000")))
