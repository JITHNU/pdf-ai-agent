from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
import os, re, requests, PyPDF2, io
from dotenv import load_dotenv
from pathlib import Path
import pdfplumber
import wikipedia
from typing import TypedDict, List, Optional, Dict, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from mangum import Mangum

handler = Mangum(app)

# Additional document parsing libraries
# Ensure these are installed in your environment: python-docx, python-pptx, pandas, openpyxl
try:
    from docx import Document as DocxDocument
except Exception:
    DocxDocument = None

try:
    from pptx import Presentation as PptxPresentation
except Exception:
    PptxPresentation = None

try:
    import pandas as pd
except Exception:
    pd = None

load_dotenv()

# --- Config / Keys  ---
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
WEB_SEARCH_API_KEY = os.getenv("WEB_SEARCH_API_KEY")
WEB_SEARCH_CX = os.getenv("WEB_SEARCH_CX")

# LLM client (your original)
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0,
    api_key=GEMINI_API_KEY
)

# Keep a simple in-memory stores (for demo). 
pdf_store: Dict[str, str] = {}         
doc_store: Dict[str, List[Dict]] = {} 
retrieval_index: Dict[str, Dict[str, Any]] = {} 

# --- LangGraph State Typing (expanded) ---
class AgentState(TypedDict):
    messages: List[HumanMessage]
    session_id: str
    query: str

# For this time can only upload Pdfs
# --- Utility: Document parsers (DOCX, PPTX, CSV/Excel) ---
def extract_text_from_pdf_file(file_obj) -> str:
    text = ""
    with pdfplumber.open(file_obj) as pdf:
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text() or ""
            
            if not page_text:
                words = page.extract_words()
                page_text = " ".join([w['text'] for w in words])
            
            page_text = page_text.strip()
            if page_text:
                page_text = re.sub(r'\n+', '\n', page_text)
                text += f"\n--- Page {i + 1} ---\n{page_text}\n--- End of Page {i + 1} ---\n"
    return text

def extract_text_from_docx_file(file_obj) -> str:
    if DocxDocument is None:
        return ""
    try:
        file_obj.seek(0)
        doc = DocxDocument(io.BytesIO(file_obj.read()))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs)
        return text
    except Exception:
        return ""

def extract_text_from_pptx_file(file_obj) -> str:
    if PptxPresentation is None:
        return ""
    try:
        file_obj.seek(0)
        prs = PptxPresentation(io.BytesIO(file_obj.read()))
        slides_text = []
        for idx, slide in enumerate(prs.slides):
            texts = []
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    t = shape.text.strip()
                    if t:
                        texts.append(t)
            if texts:
                slides_text.append(f"--- Slide {idx+1} ---\n" + "\n".join(texts))
        return "\n".join(slides_text)
    except Exception:
        return ""

def extract_text_from_tabular(file_obj, filename) -> str:
    # CSV or Excel
    if pd is None:
        return ""
    try:
        file_obj.seek(0)
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_obj.read()))
        else:
            # excel
            df = pd.read_excel(io.BytesIO(file_obj.read()))
        # Convert to a readable string: header + first N rows
        text = "Table content:\n"
        text += df.head(50).to_csv(index=False)
        return text
    except Exception:
        return ""

# --- Simple local RAG: Tfidf vector store per session ---
def build_session_index(session_id: str):
    # Builds TF-IDF index from doc_store[session_id]
    docs_meta = doc_store.get(session_id, [])
    texts = [d["text"] for d in docs_meta]
    if not texts:
        retrieval_index.pop(session_id, None)
        return

    vectorizer = TfidfVectorizer(stop_words="english", max_features=50000)
    matrix = vectorizer.fit_transform(texts)
    retrieval_index[session_id] = {
        "vectorizer": vectorizer,
        "matrix": matrix,
        "docs": docs_meta,
        "texts": texts
    }

def retrieve_relevant(session_id: str, query: str, k: int = 3) -> List[Dict]:
    # Returns top-k doc metadata dicts with score
    idx = retrieval_index.get(session_id)
    if not idx:
        return []
    vec = idx["vectorizer"].transform([query])
    sims = cosine_similarity(vec, idx["matrix"]).flatten()
    best_idx = sims.argsort()[::-1][:k]
    results = []
    for i in best_idx:
        score = float(sims[i])
        if score <= 0:
            continue
        meta = idx["docs"][i].copy()
        meta["score"] = score
        results.append(meta)
    return results

# --- Existing simple helpers (weather / google search / wiki)  ---
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

def get_wikipedia_summary(query: str) -> str:
    try:
        wikipedia.set_lang("en")
        results = wikipedia.search(query)
        if not results:
            return ""
        page_title = results[0]
        page = wikipedia.page(page_title, auto_suggest=False)
        summary = page.summary.split("\n")[0]
        return f"📘 **{page.title}** — {summary}\n🔗 {page.url}"
    except wikipedia.exceptions.DisambiguationError as e:
        try:
            page = wikipedia.page(e.options[0])
            summary = page.summary.split("\n")[0]
            return f"📘 **{page.title}** — {summary}\n🔗 {page.url}"
        except Exception:
            return ""
    except wikipedia.exceptions.PageError:
        return ""
    except Exception as e:
        print("Wikipedia error:", e)
        return ""

# --- Decision logic  ---
def smart_decision_type(text: str) -> str:
    """
    Returns one of: 'weather', 'wiki', 'pdf_rag', 'google', 'gemini'
    This function is deliberately conservative.
    """
    t = text.lower().strip()
    # weather detection
    if "weather" in t or "temperature" in t:
        return "weather"
    # direct doc mention or if session has docs -> pdf_rag (only if user mentions PDF/document or file exists)
    if any(w in t for w in ["pdf", "document", "file", "resume", "cv", "report"]) :
        return "pdf_rag"
    # live queries
    live_keywords = ["today", "latest", "current", "now", "rate", "price", "exchange", "stock", "news"]
    if any(k in t for k in live_keywords):
        return "google"
    # who/what factual
    if re.search(r"^\s*(who|what|where|when|why)\b", t):
        return "wiki"
    # fallback
    return "gemini"

# --- Agents implementation (one function per agent) ---

# PDF / Document RAG agent: uses the simple TF-IDF retriever
def PDFRAGAgent(session_id: str, query: str) -> str:
    # Retrieve top documents from the session's doc_store
    results = retrieve_relevant(session_id, query, k=10)
    if not results:
        return "I couldn't find relevant document content in your uploaded files. Please upload a document or be more specific."

    # Build a simple prompt using retrieved passages
    context = "\n\n".join([f"Source: {r.get('source','unknown')}\n{r.get('text')}" for r in results])
    prompt = (
        "You are JithBot, a helpful assistant. Use the document excerpts below to answer the user's question.\n\n"
        f"{context}\n\nUser question: {query}\nAnswer comprehensively and list all relevant items, citing the source (filename)."
    )

    # Use the Gemini LLM 
    history = [
        SystemMessage(content="You are JithBot, a helpful assistant specialized in answering from documents."),
        HumanMessage(content=prompt)
    ]
    try:
        res = llm.invoke(history) 
        if hasattr(res, "content"):
            return res.content.strip()
        return str(res).strip()
    except Exception as e:
        return f"Error invoking LLM for document answer: {e}"

# Weather agent
def WeatherAgent(session_id: str, query: str) -> str:
    match = re.search(r"weather\s+(?:in|of|at)?\s*([a-zA-Z\s]+)", query.lower())
    city = match.group(1).strip() if match else None
    if city:
        return get_weather(city.title())
    return "Please tell me the city name (e.g., 'Weather in Colombo')."

# Wiki agent
def WikiAgent(session_id: str, query: str) -> str:
    wiki_result = get_wikipedia_summary(query)
    if wiki_result:
        return wiki_result
    # fallback to google search if wikipedia empty
    return google_search(query)

# General Gemini agent (default)
def GeminiAgent(session_id: str, query: str, conversation_history: List[Dict]) -> str:
    # simple context usage: last few messages
    history_text = "\n".join([f"{m['role'].capitalize()}: {m['text']}" for m in conversation_history[-6:]])
    prompt = (
        "You are JithBot, an AI assistant. Be concise and accurate.\n\n"
        f"Conversation so far:\n{history_text}\n\nUser: {query}\nAssistant:"
    )
    agent_history = [
        SystemMessage(content="You are JithBot, a helpful AI assistant."),
        HumanMessage(content=prompt)
    ]
    try:
        res = llm.invoke(agent_history)
        if hasattr(res, "content"):
            return res.content.strip()
        return str(res).strip()
    except Exception as e:
        return f"Error invoking Gemini: {e}"

# --- LangGraph nodes (kept simple; functions exist so you can wire them into a graph if you wish) ---
# We'll declare them so you can compile a small graph if you want to visualize flows.
def DispatcherNode(state: AgentState) -> AgentState:
    # Decide which agent to call and store route in state
    query = state["messages"][-1].content if state["messages"] else state.get("query", "")
    route = smart_decision_type(query)
    # Add a small metadata message
    state["messages"].append(AIMessage(content=f"[Dispatcher chosen route: {route}]"))
    # store route for later use
    state["route"] = route  
    return state

def DummyEndNode(state: AgentState) -> AgentState:
    # Do nothing; end node
    return state

UPLOAD_DIR = Path("uploaded_pdfs")
UPLOAD_DIR.mkdir(exist_ok=True)

# Build a simple langgraph workflow description
workflow = StateGraph(AgentState)
workflow.add_node("Dispatcher", DispatcherNode)
workflow.add_node("End", DummyEndNode)
workflow.set_entry_point("Dispatcher")
workflow.add_edge("Dispatcher", "End")
app_agent = workflow.compile()

# --- FastAPI app (routes) ---
app = FastAPI(title="JithBot - Next Gen (doc ingestion + orchestration)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

conversation_history: Dict[str, List[Dict]] = {}

class ChatRequest(BaseModel):
    query: str
    session_id: str

@app.post("/upload_pdf")
async def upload_pdf(file: UploadFile = File(...), session_id: str = Form(...)):
    session_path = UPLOAD_DIR / session_id
    session_path.mkdir(exist_ok=True)

    file_path = session_path / file.filename
    raw = await file.read()
    with open(file_path, "wb") as f:
        f.write(raw)

    # Extract text
    text = extract_text_from_pdf_file(io.BytesIO(raw))
    if session_id not in doc_store:
        doc_store[session_id] = []
    doc_store[session_id].append({"source": file.filename, "text": text})
    build_session_index(session_id)

    return {"message": f"PDF '{file.filename}' uploaded and indexed successfully!"}
    
# --- Upload route: accept PDF, DOCX, PPTX, CSV, XLSX ---
@app.post("/upload_doc")
async def upload_doc(file: UploadFile = File(...), session_id: str = Form(...)):
    filename = file.filename.lower()
    raw = await file.read()
    if session_id not in doc_store:
        doc_store[session_id] = []

    text = ""
    # Route by extension
    if filename.endswith(".pdf"):
        try:
            text = extract_text_from_pdf_file(io.BytesIO(raw))
        except Exception:
            text = ""
    elif filename.endswith(".docx") or filename.endswith(".doc"):
        text = extract_text_from_docx_file(io.BytesIO(raw))
    elif filename.endswith(".pptx") or filename.endswith(".ppt"):
        text = extract_text_from_pptx_file(io.BytesIO(raw))
    elif filename.endswith(".csv") or filename.endswith(".xls") or filename.endswith(".xlsx"):
        text = extract_text_from_tabular(io.BytesIO(raw), filename)
    else:
        return {"error": "Unsupported file type. Supported: PDF, DOCX, PPTX, CSV, XLSX."}

    if not text.strip():
        return {"error": "Uploaded file did not yield extractable text or required parser not installed."}

    # Normalize and store
    snippet = text[:2000]  
    meta = {"source": file.filename, "text": text}
    doc_store[session_id].append(meta)

    build_session_index(session_id)

    return {"message": f"File '{file.filename}' uploaded and indexed for session {session_id}."}

# --- Chat endpoint with orchestration  ---
@app.post("/chat")
async def chat(req: ChatRequest):
    query = req.query.strip()
    session_id = req.session_id

    if session_id not in conversation_history:
        conversation_history[session_id] = []

    # append user message
    conversation_history[session_id].append({"role": "user", "text": query})

    # Decide route
    route = smart_decision_type(query)

    # Force PDF RAG if session has documents
    if session_id in doc_store and doc_store[session_id]:
        route = "pdf_rag"
    else:
        # fallback to existing dispatcher logic
        route = smart_decision_type(query)

    # Logging
    print(f"Dispatcher: session={session_id}, query='{query}', route={route}")

    # Route to corresponding agent
    try:
        if route == "weather":
            answer = WeatherAgent(session_id, query)

        elif route == "wiki":
            answer = WikiAgent(session_id, query)

        elif route == "google":
            # For 'google' route we default to web search (as in your original)
            answer = google_search(query)

        elif route == "pdf_rag":
            answer = PDFRAGAgent(session_id, query)

        else:  # 'gemini' or fallback
            answer = GeminiAgent(session_id, query, conversation_history[session_id])

        # Save assistant reply in history
        conversation_history[session_id].append({"role": "assistant", "text": answer})

        # Trim history for memory
        if len(conversation_history[session_id]) > 40:
            conversation_history[session_id] = conversation_history[session_id][-20:]

        return {"answer": answer}

    except Exception as e:
        print("Routing / agent error:", e)
        return {"answer": f"Error: {e}"}
