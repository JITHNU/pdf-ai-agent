from fastapi import FastAPI, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi import FastAPI, Request, UploadFile, File
import os, re, requests, PyPDF2
from dotenv import load_dotenv
from google import genai
import wikipedia
import re

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
pdf_store = {} 

GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
WEB_SEARCH_API_KEY = os.getenv("WEB_SEARCH_API_KEY")
WEB_SEARCH_CX = os.getenv("WEB_SEARCH_CX")

client = genai.Client(api_key=GEMINI_API_KEY)

app = FastAPI(title="JithBot - AI Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

conversation_history = {}

class ChatRequest(BaseModel):
    query: str
    session_id: str


def get_weather(city: str):
    if not WEATHER_API_KEY:
        return "Weather API key not found."
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        res = requests.get(url)
        data = res.json()
        if data.get("cod") != 200:
            return f"Couldn't find weather for {city}."
        weather = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        feels = data["main"]["feels_like"]
        humidity = data["main"]["humidity"]
        return f"Weather in {city}: {weather}. Temp: {temp}°C, feels like {feels}°C. Humidity: {humidity}%."
    except Exception as e:
        return f"Error fetching weather: {e}"


def google_search(query: str):
    if not WEB_SEARCH_API_KEY or not WEB_SEARCH_CX:
        return "Web search not configured. Please set WEB_SEARCH_API_KEY and WEB_SEARCH_CX."
    try:
        url = f"https://www.googleapis.com/customsearch/v1?q={query}&key={WEB_SEARCH_API_KEY}&cx={WEB_SEARCH_CX}"
        res = requests.get(url)
        data = res.json()
        if "items" not in data:
            return "No search results found."
        top = data["items"][0]
        title = top.get("title", "No title")
        snippet = top.get("snippet", "No description")
        link = top.get("link", "")
        return f"{title}: {snippet}\n🔗 {link}"
    except Exception as e:
        return f"Error during Google search: {e}"

def smart_decision(query: str) -> str:
    """
    Decide what type of question the user asked.
    Returns one of: 'weather', 'who', 'what', 'pdf', or 'general'
    """

    q = query.lower().strip()

    if "weather" in q or "temperature" in q:
        return "weather"
    elif q.startswith("who is") or q.startswith("who was"):
        return "who"
    elif q.startswith("what is") or q.startswith("explain"):
        return "what"
    elif "pdf" in q or "document" in q:
        return "pdf"
    else:
        return "general"

# --- Wikipedia lookup for factual or "who is" queries ---
def get_wikipedia_summary(query: str) -> str:
    try:
        wikipedia.set_lang("en")
        results = wikipedia.search(query)
        if not results:
            return ""
        page_title = results[0]
        page = wikipedia.page(page_title, auto_suggest=False)
        summary = page.summary.split("\n")[0]
        return f"📘 **{page.title}** — {summary}\n🔗 [Read more on Wikipedia]({page.url})"
    except wikipedia.exceptions.DisambiguationError as e:
        try:
            page = wikipedia.page(e.options[0])
            summary = page.summary.split("\n")[0]
            return f"📘 **{page.title}** — {summary}\n🔗 [Read more on Wikipedia]({page.url})"
        except Exception:
            return ""
    except wikipedia.exceptions.PageError:
        return ""
    except Exception as e:
        print("Wikipedia error:", e)
        return ""

def smart_decision(text: str):
    text = text.lower()
    if "weather" in text or "temperature" in text:
        return "weather"
    live_keywords = [
        "rate", "price", "today", "latest", "current", "exchange",
        "news", "update", "stock", "currency", "trend"
    ]
    if any(k in text for k in live_keywords):
        return "google"
    return "gemini"


# --- Helper for time-sensitive or officeholder queries ---
def looks_like_office_query(text: str):
    text = text.lower()
    if re.search(r"\b(who\s+is|who's)\b.*\b(president|prime minister|pm|chancellor|king|queen|mayor)\b", text):
        return True
    if any(k in text for k in ["current", "as of", "today", "now", "latest"]):
        return True
    if any(k in text for k in ["rate", "exchange", "currency", "weather", "score", "ranking"]):
        return True
    return False

# --- PDF upload ---
@app.post("/upload_pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    session_id: str = Form(...)
):
    if not file.filename.endswith(".pdf"):
        return {"error": "Only PDF files are supported."}

    reader = PyPDF2.PdfReader(file.file)
    text = ""
    for i, page in enumerate(reader.pages):
        page_text = page.extract_text()
        if page_text:
            # normalize line breaks
            page_text = re.sub(r'\n+', '\n', page_text.strip())

            # Convert lines starting with "*" to proper list format
            page_text = re.sub(r'^\* ?', '- ', page_text, flags=re.MULTILINE)

            # Add page separators
            text += f"\n--- Page {i + 1} ---\n{page_text}\n--- End of Page {i + 1} ---\n"

    if not text.strip():
        return {"error": "PDF does not contain extractable text."}

    pdf_store[session_id] = text
    print(f"Stored PDF text length for session {session_id}: {len(text)}")
    return {"message": f"PDF uploaded successfully with session id."}

# --- Main Chat Endpoint ---
@app.post("/chat")
async def chat(req: ChatRequest):
    query = req.query.strip()
    session_id = req.session_id
    mode = smart_decision(query)
    print(f"🤖 Detected mode: {mode}")

    if session_id not in conversation_history:
        conversation_history[session_id] = []

    # --- If PDF exists, answer from PDF ---
    if session_id in pdf_store:
        pdf_text = pdf_store[session_id]
        prompt = (
            "You are an AI assistant. Your name is JitBot, Answer the user question based on the PDF content below.\n\n"
            f"PDF CONTENT:\n{pdf_text}\n\n"
            "Instructions for formatting the answer:\n"
            "- Use bullet points for lists like references, skills, projects\n"
            "- Start each item on a new line\n"
            "- Clearly separate different sections\n\n"
            f"User Question: {query}\nAssistant:"
        )

        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt],
        )
        answer = getattr(resp, "text", "I could not find an answer in the PDF.").strip()
        conversation_history[session_id].append({"role": "user", "text": query})
        conversation_history[session_id].append({"role": "assistant", "text": answer})
        return {"answer": answer}

    # --- Weather handling ---
    if mode == "weather":
        match = re.search(r"weather\s+(?:in|of|at)?\s*([a-zA-Z\s]+)", query.lower())
        city = match.group(1).strip() if match else None
        if city:
            return {"answer": get_weather(city.title())}
        return {"answer": "Please mention a city name to get the weather (e.g., 'Weather in Colombo')."}

    # --- Wikipedia / factual queries ---
    if looks_like_office_query(query) or re.search(r"\b(who|what|where)\b", query.lower()):
        try:
            wiki_result = get_wikipedia_summary(query)
            if wiki_result:  # ✅ Wikipedia found something
                conversation_history[session_id].append({"role": "user", "text": query})
                conversation_history[session_id].append({"role": "assistant", "text": wiki_result})
                return {"answer": wiki_result}
            else:  
                google_result = google_search(query)
                conversation_history[session_id].append({"role": "user", "text": query})
                conversation_history[session_id].append({"role": "assistant", "text": google_result})
                return {"answer": google_result}
        except Exception as e:
            print("Wikipedia/Google search error:", e)
            return {"answer": google_search(query)}

    # --- Gemini chat (default mode) ---
    try:
        history = conversation_history[session_id][-5:]
        history_text = "\n".join(
            [f"{m['role'].capitalize()}: {m['text']}" for m in history]
        )

        prompt = (
            "You are JithBot, an AI assistant. "
            "Be concise and accurate. For questions about current facts "
            "(e.g., who is X, current rates, or rankings), verify via reliable sources.\n\n"
            f"Conversation so far:\n{history_text}\n\nUser: {query}\nAssistant:"
        )

        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt],
        )

        if hasattr(resp, "text") and resp.text.strip():
            answer = resp.text.strip()

            # Optional sanity check for outdated responses
            if re.search(r"\b(201[0-9]|2020|2021|2022|2023)\b", answer) or "may be" in answer.lower():
                try:
                    verified = google_search(query)
                    conversation_history[session_id].append({"role": "user", "text": query})
                    conversation_history[session_id].append({"role": "assistant", "text": verified})
                    return {"answer": verified}
                except Exception:
                    pass

            conversation_history[session_id].append({"role": "user", "text": query})
            conversation_history[session_id].append({"role": "assistant", "text": answer})

            if len(conversation_history[session_id]) > 20:
                conversation_history[session_id] = conversation_history[session_id][-10:]

            return {"answer": answer}

        return {"answer": "I'm not sure about that, could you rephrase?"}

    except Exception as e:
        print("Gemini chat error:", e)
        if "RESOURCE_EXHAUSTED" in str(e):
            return {"answer": google_search(query)}
        return {"answer": f"Error: {e}"}
