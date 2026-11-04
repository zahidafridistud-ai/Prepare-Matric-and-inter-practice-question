"""Imtihan Saathi - exam practice from your own textbook chapter (Streamlit).

Run locally:   streamlit run app.py
Deploy:        Streamlit Community Cloud (main file: app.py)
The Gemini API key is read from Streamlit secrets (GEMINI_API_KEY), never from the code.
"""
import base64
import html
import json
import os
import re

import requests
import streamlit as st

st.set_page_config(page_title="Imtihan Saathi", page_icon="📚", layout="centered")

st.markdown(
    """<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Nastaliq+Urdu&display=swap');
.ur{direction:rtl;text-align:right;font-family:'Noto Nastaliq Urdu','Noto Naskh Arabic',serif;line-height:2.2}
.res{border-radius:10px;padding:12px 14px;margin-top:8px}
.res p{margin:6px 0}
</style>""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------ settings
def get_secret(name, default=""):
    """Read from Streamlit secrets first, then environment variables."""
    try:
        value = st.secrets[name]
    except Exception:
        value = os.getenv(name, default)
    return str(value).strip()


API_KEY = get_secret("GEMINI_API_KEY")
MODEL = get_secret("GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash"
try:
    MAX_CALLS = int(get_secret("MAX_CALLS_PER_SESSION", "60"))
except ValueError:
    MAX_CALLS = 60
MAX_CHARS = 20000
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
ALLOWED_MIME = {"application/pdf", "image/png", "image/jpeg", "image/webp"}

BOARDS = ["Not specified", "Punjab", "Sindh", "Federal (FBISE)", "KPK", "Balochistan", "AJK"]
SUBJECTS = ["Biology", "Physics", "Chemistry", "Mathematics", "Computer Science", "English",
            "Urdu", "Islamiyat", "Pakistan Studies", "Economics", "Accounting", "Statistics",
            "Other (type below)"]
QTYPES = {
    "mix": "Mixed (MCQ + short + long)",
    "mcq": "MCQs only",
    "short": "Short questions",
    "long": "Long questions",
}
KIND_TEXT = {
    "mix": "a mix of MCQs (4 options), short questions (2-3 lines) and long questions (a paragraph)",
    "mcq": "only MCQs with 4 options",
    "short": "only short questions answerable in 2-3 lines",
    "long": "only long questions answerable in a detailed paragraph",
}
LANGS = ["English", "Urdu", "Roman Urdu"]


# -------------------------------------------------------------------- Gemini
class GeminiError(Exception):
    pass


def call_gemini(parts, as_json=True):
    if not API_KEY:
        raise GeminiError("GEMINI_API_KEY is missing. Add it in the app's Secrets.")
    used = st.session_state.get("calls", 0)
    if used >= MAX_CALLS:
        raise GeminiError("You have reached the limit for this session. Refresh the page to continue.")
    st.session_state["calls"] = used + 1

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
        raise GeminiError("Could not reach Gemini. Please try again.")
    if r.status_code != 200:
        try:
            msg = r.json()["error"]["message"]
        except Exception:
            msg = f"Gemini request failed ({r.status_code})"
        raise GeminiError(msg)
    try:
        cand = r.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in cand)
    except (KeyError, IndexError, TypeError):
        raise GeminiError("Gemini returned no answer (the content may have been blocked).")
    if not as_json:
        return text
    try:
        return json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip())
    except json.JSONDecodeError:
        raise GeminiError("Could not read the AI response. Please try again.")


def lang_rule(lang):
    if lang == "Urdu":
        return ("Write all explanations and feedback in clear Urdu script (اردو). "
                "Keep scientific/technical terms in English in brackets where helpful.")
    if lang == "Roman Urdu":
        return ("Write all explanations and feedback in Roman Urdu (Urdu in Latin letters, "
                "as Pakistani students write), simple and friendly. Keep technical terms in English.")
    return "Write all explanations and feedback in simple English suitable for a Pakistani student."


def context_line(meta):
    names = (("Board", "board"), ("Subject", "subject"), ("Book", "book"), ("Chapter", "chapter_name"))
    bits = [f"{label}: {meta[key]}" for label, key in names if meta.get(key)]
    return ("Context - " + "; ".join(bits) + ".\n") if bits else ""


def extract_text(file):
    """Turn an uploaded txt / pdf / image into plain text."""
    name = file.name.lower()
    if name.endswith(".txt") or file.type == "text/plain":
        return file.getvalue().decode("utf-8", "ignore")
    mime = file.type
    if name.endswith(".pdf"):
        mime = "application/pdf"
    if mime not in ALLOWED_MIME:
        raise GeminiError("Upload a .txt, PDF, PNG, JPG or WEBP file.")
    if file.size > 15 * 1024 * 1024:
        raise GeminiError("File is too large (max 15 MB).")
    data = base64.b64encode(file.getvalue()).decode()
    text = call_gemini(
        [
            {"inlineData": {"mimeType": mime, "data": data}},
            {"text": "Transcribe the textbook content in this file as plain text, keeping headings, "
                     "definitions and lists. Keep the original language. Output only the text."},
        ],
        as_json=False,
    )
    return text.strip()


def generate_questions(chapter, meta, level, qtype, count):
    prompt = (
        f"You are an exam setter for Pakistani board exams ({level}). {context_line(meta)}"
        f"Using ONLY the chapter below, write {count} practice questions: {KIND_TEXT[qtype]}. "
        "Questions must be in English, in board-exam style, and answerable from the chapter. "
        "Return ONLY a JSON array. Each item: "
        '{"type":"mcq"|"short"|"long","q":string,"options":[4 strings, mcq only],'
        '"marks":number,"key":"the correct answer / key points taken from the chapter"}.'
        f"\n\nCHAPTER:\n{chapter}"
    )
    out = call_gemini([{"text": prompt}])
    items = out if isinstance(out, list) else out.get("questions", []) if isinstance(out, dict) else []
    cleaned = []
    for it in items:
        if not isinstance(it, dict) or not it.get("q"):
            continue
        if it.get("type") == "mcq" and not (isinstance(it.get("options"), list) and len(it["options"]) >= 2):
            it["type"] = "short"
        if it.get("type") not in ("mcq", "short", "long"):
            it["type"] = "short"
        cleaned.append(it)
    if not cleaned:
        raise GeminiError("No questions were created. Try a longer chapter excerpt.")
    return cleaned


def check_answer(chapter, meta, q, answer, lang):
    marks = q.get("marks") or 1
    options = q.get("options") if q.get("type") == "mcq" else None
    prompt = (
        "You are a kind but strict Pakistani board examiner. Check the student's answer ONLY against "
        f"the chapter text. {context_line(meta)}{lang_rule(lang)}\n"
        'Return ONLY JSON: {"score":number,"out_of":' + str(marks) + ',"level":"good"|"partial"|"wrong",'
        '"right":"what the student got right","missing":"what is wrong or missing, with the chapter\'s facts",'
        '"model_answer":"a model answer in 2-5 sentences grounded in the chapter","tip":"one short exam tip"}.\n\n'
        f"QUESTION: {q.get('q', '')}\n"
        + (f"OPTIONS: {' | '.join(map(str, options))}\n" if options else "")
        + f"KEY: {q.get('key', '')}\nSTUDENT ANSWER: {answer}\n\nCHAPTER:\n{chapter}"
    )
    result = call_gemini([{"text": prompt}])
    if not isinstance(result, dict):
        raise GeminiError("Could not read the AI response. Please try again.")
    return result


def result_html(r, lang):
    color = {"good": "#2e8b57", "partial": "#c28a00"}.get(r.get("level"), "#c0392b")
    e = lambda v: html.escape("" if v is None else str(v))
    cls = "ur" if lang == "Urdu" else ""
    return (
        f'<div class="res {cls}" style="border-left:5px solid {color};background:{color}22">'
        f'<h4 style="margin:0 0 6px">{e(r.get("score"))} / {e(r.get("out_of"))}</h4>'
        f'<p><b>✔</b> {e(r.get("right"))}</p>'
        f'<p><b>✖</b> {e(r.get("missing"))}</p>'
        f'<p><b>Model answer:</b> {e(r.get("model_answer"))}</p>'
        f'<p><i>{e(r.get("tip"))}</i></p></div>'
    )


# ------------------------------------------------------------------------ UI
st.title("📚 Imtihan Saathi")
st.caption("Upload or paste a chapter from your own textbook. Get practice questions and have your "
           "answers checked against it. Explanations in English, Urdu or Roman Urdu.")

if not API_KEY:
    st.error("GEMINI_API_KEY is missing. On Streamlit Cloud open **Manage app → Settings → Secrets** "
             "and add it. See the README.")
    st.stop()

col1, col2 = st.columns(2)
board = col1.selectbox("Board", BOARDS)
subject_choice = col2.selectbox("Subject", SUBJECTS)
subject = subject_choice
if subject_choice.startswith("Other"):
    subject = st.text_input("Subject name", max_chars=60, placeholder="e.g. Home Economics")
col3, col4 = st.columns(2)
chapter_name = col3.text_input("Chapter name / number", max_chars=80, placeholder="e.g. Ch 5 - Cell Cycle")
book = col4.text_input("Book (optional)", max_chars=80, placeholder="e.g. Punjab Textbook Board")

col5, col6, col7, col8 = st.columns(4)
level = col5.selectbox("Level", ["Matric (9th/10th)", "Inter (11th/12th)"])
qtype = col6.selectbox("Question type", list(QTYPES), format_func=QTYPES.get)
count = col7.selectbox("How many", [5, 8, 10])
lang = col8.selectbox("Explain in", LANGS)

st.subheader("Your chapter")
uploaded = st.file_uploader("Upload .txt, PDF or a photo of a page", type=["txt", "pdf", "png", "jpg", "jpeg", "webp"])
if uploaded is not None and st.button("📄 Read text from file"):
    try:
        with st.spinner("Reading your file…"):
            st.session_state["chapter_text"] = extract_text(uploaded)
        st.success("Done. Check the text below, then create questions.")
    except GeminiError as err:
        st.error(str(err))

st.text_area("…or paste the chapter text here", key="chapter_text", height=220,
             placeholder="Paste the chapter text (Biology, Physics, Pak Studies, English…)")

meta = {
    "board": "" if board == "Not specified" else board,
    "subject": subject.strip() if subject else "",
    "book": book.strip(),
    "chapter_name": chapter_name.strip(),
}

if st.button("✨ Create practice questions", type="primary"):
    chapter = st.session_state.get("chapter_text", "").strip()[:MAX_CHARS]
    if len(chapter) < 200:
        st.warning("Please add a longer chapter excerpt (at least a few paragraphs).")
    else:
        try:
            with st.spinner("Reading your chapter and writing questions…"):
                questions = generate_questions(chapter, meta, level, qtype, count)
            for key in [k for k in st.session_state if k.startswith(("ans_", "chk_"))]:
                del st.session_state[key]
            st.session_state.update(questions=questions, results={}, chapter_used=chapter, meta_used=meta)
        except GeminiError as err:
            st.error(str(err))

questions = st.session_state.get("questions", [])
if questions:
    st.divider()
    title = " – ".join(v for v in (st.session_state["meta_used"].get("subject"),
                                    st.session_state["meta_used"].get("chapter_name")) if v)
    if title:
        st.subheader(title)
    for i, q in enumerate(questions):
        with st.container(border=True):
            marks = q.get("marks") or 1
            st.markdown(f"**Q{i + 1}.** {q['q']}")
            st.caption(f"{q['type']} · {marks} mark{'s' if marks != 1 else ''}")
            if q["type"] == "mcq":
                answer = st.radio("Choose one", q["options"], index=None, key=f"ans_{i}",
                                  label_visibility="collapsed")
            else:
                answer = st.text_area("Your answer", key=f"ans_{i}", height=120,
                                      placeholder="Write your answer in English, Urdu or Roman Urdu…",
                                      label_visibility="collapsed")
            if st.button("Check my answer", key=f"chk_{i}"):
                if not answer or not str(answer).strip():
                    st.warning("Please answer first.")
                else:
                    try:
                        with st.spinner("Checking against your chapter…"):
                            st.session_state["results"][i] = (
                                check_answer(st.session_state["chapter_used"], st.session_state["meta_used"],
                                             q, str(answer).strip()[:4000], lang),
                                lang,
                            )
                    except GeminiError as err:
                        st.error(str(err))
            if i in st.session_state.get("results", {}):
                res, res_lang = st.session_state["results"][i]
                st.markdown(result_html(res, res_lang), unsafe_allow_html=True)
