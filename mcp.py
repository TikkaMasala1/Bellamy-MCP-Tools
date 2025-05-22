from fastapi import FastAPI, HTTPException
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
    type: str  # "multiple_choice" or "scenario"
    level: str  # "beginner", "intermediate", "advanced"



@app.post("/generate_question")
async def generate_question(request: QuestionRequest):
    try:
        prompt = f"""
        Based on this cybersecurity knowledge:
        {knowledge_base[:300000]}...

        Generate a {request.level} level {request.type} question about {request.topic}.
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


@app.get("/health")
async def health_check():
    return {"status": "ok"}