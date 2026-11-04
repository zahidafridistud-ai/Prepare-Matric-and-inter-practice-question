# 📚 Imtihan Saathi

Exam practice for Pakistani **Matric and Inter** students, built from their **own textbook chapters**.

Upload or paste a chapter and the app will:

1. Create board-style practice questions (MCQs, short, long)
2. Check each answer **against the chapter only**
3. Explain mistakes in **English, Urdu (اردو) or Roman Urdu**

Powered by Google Gemini. The API key stays on the server, so students never see it.

## Project structure

```
imtihan-saathi/
├── app.py               # Flask backend + Gemini calls
├── templates/
│   └── index.html       # Web interface
├── requirements.txt
├── Procfile             # for Render / Railway / Heroku
├── .env.example         # copy to .env and add your key
└── .gitignore
```

## Run locally

You need Python 3.9 or newer and a free Gemini API key from <https://aistudio.google.com/apikey>.

```bash
git clone https://github.com/YOUR-USERNAME/imtihan-saathi.git
cd imtihan-saathi

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # Windows: copy .env.example .env
# open .env and paste your GEMINI_API_KEY

python app.py
```

Open <http://localhost:5000>.

## Deploy online (free tier on Render)

GitHub Pages cannot run Python, so deploy the repo to a Python host:

1. Push this project to GitHub.
2. On <https://render.com> choose **New → Web Service** and connect your repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Under **Environment**, add `GEMINI_API_KEY` with your key.
6. Deploy. Share the URL with students.

Railway, PythonAnywhere and Fly.io work the same way.

## Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | none | Your Gemini key (required) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Change if Google renames or updates models |
| `RATE_LIMIT_PER_MIN` | `20` | Max AI requests per IP per minute |

## Security notes

- Never commit `.env`. If a key leaks, delete it in Google AI Studio and create a new one.
- The built-in rate limit is simple and in memory. For a large public launch, add login or a stronger limiter so your free quota is not used up.
- Textbook text is sent to Google Gemini for processing. Only upload material you are allowed to use.

## Ideas to extend

- Save question history and scores (SQLite)
- Timed mock tests and past-paper mode
- Chapter-wise progress dashboard
- Urdu-language questions

## License

MIT, use it freely for education.
