from fastapi import APIRouter, UploadFile, File
from app.services.pdf_reader import extract_text_from_pdf
import google.generativeai as genai
import os

router = APIRouter()

@router.post("/upload_pdf/")
async def upload_pdf(file: UploadFile = File(...)):
    # Save file temporarily
    file_location = f"uploads/{file.filename}"
    with open(file_location, "wb") as f:
        f.write(await file.read())

    # Extract text
    text = extract_text_from_pdf(file_location)

    # Store text in memory (temporary for demo)
    with open("uploads/current_text.txt", "w") as f:
        f.write(text)

    return {"message": "PDF uploaded and processed successfully!"}

@router.post("/ask/")
async def ask_question(question: str):
    # Load previously extracted text
    with open("uploads/current_text.txt", "r") as f:
        context = f.read()

    prompt = f"You are an assistant that answers questions based on this PDF text:\n\n{context}\n\nQuestion: {question}"

    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)

    return {"answer": response.text}
