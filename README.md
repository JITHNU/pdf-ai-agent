# AstraDocs AI - PDF Integrated AI Agent

An intelligent PDF chat workspace with a polished, enterprise-style interface for document Q&A, conversation history, and PDF upload handling.

The frontend has been refreshed to feel closer to modern AI products: a layered chat shell, premium glassmorphism panels, stronger hierarchy, better empty states, and a more focused composer area.

## Highlights

- PDF upload and document-grounded chat flow
- Persistent conversation history in local storage
- Premium UI with a sidebar workspace, status cards, and richer message presentation
- Responsive layout that works on desktop and mobile
- Link-aware assistant responses

## Project Structure

- `backend/` FastAPI service for chat and PDF upload endpoints
- `frontend/` Vite + React client with the redesigned chat experience

## Run Locally

Start the backend API first, then the frontend app.

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## UX Notes

The current UI emphasizes a premium knowledge-work feel with visual depth, calmer spacing, and clearer document context. If you want, the next step can be a more branded theme direction such as “Claude-like minimal”, “Gemini-like vibrant”, or “ChatGPT-like compact”.
