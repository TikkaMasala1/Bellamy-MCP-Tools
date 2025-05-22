from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import google.generativeai as genai
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

app = FastAPI()

# Global variable to store the uploaded file reference
uploaded_file_reference = None
PDF_FILENAME = "CCSK.pdf"

# Configure Gemini
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-2.0-flash')

def get_or_upload_pdf():
    """
    Uploads 'CCSK.pdf' to Gemini if not already done and returns the file reference.
    """
    global uploaded_file_reference
    if uploaded_file_reference is None:
        pdf_path = os.path.join('PDF_FILENAME')
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"The PDF file was not found at {pdf_path}")
        print(f"Uploading {pdf_path} to Gemini...")
        try:
            uploaded_pdf_file = genai.upload_file(path=pdf_path,
                                                 display_name="CCSK Cybersecurity Knowledge Base")
            uploaded_file_reference = uploaded_pdf_file
            print(f"File uploaded successfully: {uploaded_file_reference.name}")
        except Exception as e:
            print(f"Error uploading file: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to upload PDF knowledge base: {e}")
    return uploaded_file_reference


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
        pdf_knowledge_file = get_or_upload_pdf()
        if not pdf_knowledge_file:
             raise HTTPException(status_code=500, detail="PDF knowledge base is not available.")

        prompt_parts = [
            pdf_knowledge_file,
            f"""
            Based on the content of the provided cybersecurity document ({pdf_knowledge_file.display_name}):

            Generate {request.amount} {request.level} level {request.type} question(s) about {request.topic}.
            Ensure the questions are directly answerable from the document's content.

            Format:
            - Question: [question text]
            - Options: [if multiple choice, provide 3-4 plausible options]
            - Answer: [correct answer]
            - Explanation: [detailed explanation of why the answer is correct, referencing information from the document if possible]
            """
        ]

        response = model.generate_content(prompt_parts)
        return {"question": response.text}
    except Exception as e:
        print(f"Error in /generate_question: {e}") # Log for debugging
        if "DeadlineExceeded" in str(e): # Example of more specific handling
            raise HTTPException(status_code=504, detail=f"Request timed out: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.post("/clean_for_logging")
async def clean_for_logging(request: PIIInputRequest):
    try:
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

@app.get("/get_pdf_page_link")
async def get_pdf_page_link(page_number: int = Query(..., gt=0, description="The page number to link to in the PDF.")):

    pdf_file_path = Path(PDF_FILENAME).resolve() # Get absolute path
    if not pdf_file_path.exists():
        raise HTTPException(status_code=404, detail=f"The PDF file '{PDF_FILENAME}' was not found at {pdf_file_path}")

    # Construct a file URL.
    # Example: file:///path/to/your/CCSK.pdf#page=5
    file_uri = f"{pdf_file_path.as_uri()}#page={page_number}"

    return {
        file_uri,
    }


@app.get("/health")
async def health_check():
    return {"status": "ok"}