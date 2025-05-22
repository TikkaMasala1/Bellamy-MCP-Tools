from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import google.generativeai as genai
from PyPDF2 import PdfReader
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()


# Load PDF knowledge base
def load_knowledge():
    pdf_path = os.path.join('CCSK.pdf')
    text = ""
    with open(pdf_path, 'rb') as file:
        reader = PdfReader(file)
        for page in reader.pages:
            text += page.extract_text()
    return text


knowledge_base = load_knowledge()

# Configure Gemini
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-2.0-flash')


class QuestionRequest(BaseModel):
    topic: str
    type: str  # "multiple_choice" or "open"
    level: str  # "beginner", "intermediate", "advanced"
    amount: int

class PIIInputRequest(BaseModel):
    text_to_clean: str

@app.post("/generate_question")
async def generate_question(request: QuestionRequest):
    try:
        prompt = f"""
        Based on this cybersecurity knowledge:
        {knowledge_base[:10000]}...

        Generate {request.amount} {request.level} level {request.type} question(s) about {request.topic}.
        Format: 
        - Question: [question text]
        - Options: [if multiple choice]
        - Answer: [correct answer]
        - Explanation: [detailed explanation]
        """

        response = model.generate_content(prompt)
        return {"question": response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/clean_for_logging")
async def clean_for_logging(request: PIIInputRequest):
    try:
        # Prompt for PII detection and redaction
        # Instruct the model to replace PII with placeholders like [REDACTED_EMAIL], [REDACTED_PHONE], etc.
        pii_cleaning_prompt = f"""
        Analyze the following text and identify any Personally Identifiable Information (PII).
        PII includes, but is not limited to: names, email addresses, phone numbers, physical addresses,
        social security numbers, credit card numbers, bank account numbers, dates of birth, driver's license numbers,
        IP addresses if they can identify an individual, and any other information that can be used to
        uniquely identify, contact, or locate a single person.

        Your task is to return the text with all identified PII replaced by a generic placeholder.
        For example:
        - Replace names with "[REDACTED_NAME]"
        - Replace email addresses with "[REDACTED_EMAIL]"
        - Replace phone numbers with "[REDACTED_PHONE]"
        - Replace physical addresses with "[REDACTED_ADDRESS]"
        - Replace specific dates of birth with "[REDACTED_DOB]"
        - Replace any other PII with "[REDACTED_PII]"

        Only return the cleaned text. Do not include any preamble or explanation.

        Original Text:
        "{request.text_to_clean}"

        Cleaned Text:
        """

        response = model.generate_content(pii_cleaning_prompt)
        cleaned_text = response.text.strip()

        return {"original_text": request.text_to_clean, "cleaned_text": cleaned_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "ok"}