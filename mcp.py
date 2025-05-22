from fastapi import FastAPI, HTTPException, Body, Request as FastAPIRequest
from pydantic import BaseModel, Field, conint
from typing import Optional, Dict, Any, Union, Literal
import google.generativeai as genai
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(".env")

app = FastAPI(
    title="MCP Server Example (Minimal Logging/Errors)",
    description="An MCP-like server with logging and detailed error messages removed.",
    version="1.1.0",
)

SCRIPT_DIR = Path(__file__).resolve().parent
PDF_FILENAME_WITH_PATH = SCRIPT_DIR / "CCSK.pdf"
uploaded_file_reference = None

# Configure Gemini API
try:
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

    genai.configure(api_key=GEMINI_API_KEY)
    MODEL_NAME = os.getenv('GEMINI_MODEL_NAME', 'gemini-2.0-flash')
    model = genai.GenerativeModel(MODEL_NAME)

except Exception:
    model = None

def get_or_upload_pdf():
    """
    Uploads 'CCSK.pdf' to Gemini if not already done and returns the file reference.
    """
    global uploaded_file_reference
    if uploaded_file_reference is None:
        pdf_path = PDF_FILENAME_WITH_PATH
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

TOOL_GENERATE_QUESTION = "tool_generate_question_from_ccsk_pdf"
TOOL_CLEAN_PII = "tool_clean_pii_text"
TOOL_GET_PDF_PAGE_URL = "tool_get_ccsk_pdf_page_url"


class GenerateQuestionInputs(BaseModel):
    topic: str = Field(..., description="The topic for the questions.")
    type: str = Field(..., description="The type of question.")
    level: str = Field(..., description="The difficulty level.")
    amount: conint(gt=0) = Field(..., description="The number of questions to generate.")


class CleanPIIInputs(BaseModel):
    text_to_clean: str = Field(..., description="The text to be cleaned of PII.")


class GetPDFPageURLInputs(BaseModel):
    page_number: conint(gt=0) = Field(..., description="The page number to link to in the PDF.")


async def _execute_generate_question(inputs_dict: dict) -> dict:
    inputs = GenerateQuestionInputs(**inputs_dict)
    if not model:
        raise RuntimeError("MODEL_UNINITIALIZED")  # Generic internal signal

    pdf_knowledge_file = get_or_upload_pdf()

    prompt_parts = [
        pdf_knowledge_file,
        f"Based on the content of the provided cybersecurity document\n"
        f"Generate {inputs.amount} {inputs.level} level {inputs.type} question(s) about {inputs.topic}.\n"
        "Ensure the questions are directly answerable from the document's content.\n\n"
        "Format for each question:\n"
        "- Question: [question text]\n"
        "- Options: [if multiple choice, provide 3-4 plausible options, otherwise skip this line for open questions]\n"
        "- Answer: [correct answer]\n"
        "- Explanation: [detailed explanation of why the answer is correct, referencing information from the document if possible]"
    ]
    try:
        response = model.generate_content(prompt_parts)
        return {"generated_content": response.text}
    except Exception as e:
        if "DeadlineExceeded" in str(e):
            raise HTTPException(status_code=504, detail="Request timed out.")
        raise HTTPException(status_code=500, detail="Error generating question.")


async def _execute_clean_pii(inputs_dict: dict) -> dict:
    inputs = CleanPIIInputs(**inputs_dict)
    if not model:
        raise RuntimeError("MODEL_UNINITIALIZED")

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
    "{inputs.text_to_clean}"
    Cleaned Text:
    """
    try:
        response = model.generate_content(pii_cleaning_prompt)
        cleaned_text = response.text.strip()
        return {"cleaned_text": cleaned_text}
    except Exception:
        raise HTTPException(status_code=500, detail="Error cleaning PII.")


async def _execute_get_pdf_page_url(inputs_dict: dict) -> dict:
    inputs = GetPDFPageURLInputs(**inputs_dict)
    pdf_file_path = PDF_FILENAME_WITH_PATH
    if not pdf_file_path.exists():
        raise HTTPException(status_code=404, detail="PDF resource not found.")

    file_url = f"{pdf_file_path.as_uri()}#page={inputs.page_number}"
    return {"file_url": file_url}


# --- MCP JSON-RPC Structures ---
class JsonRpcErrorDetail(BaseModel):
    code: int
    message: str  # Will make these generic
    data: Optional[Any] = None


class JsonRpcResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    result: Optional[Any] = None
    error: Optional[JsonRpcErrorDetail] = None
    id: Union[str, int, None]


class JsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Union[str, int, None] = None


async def mcp_discover_impl(request_id: Union[str, int, None]) -> JsonRpcResponse:
    tools = [
        {
            "id": TOOL_GENERATE_QUESTION,
            "name": "Generate Question from CCSK PDF",
            "description": "Generates questions based on the internally managed CCSK PDF knowledge base.",
            "inputs_schema": GenerateQuestionInputs.model_json_schema(ref_template="#/components/schemas/{model}"),
            "outputs_schema": {
                "type": "object",
                "properties": {
                    "generated_content": {"type": "string", "description": "Generated questions and answers."}},
            },
        },
        {
            "id": TOOL_CLEAN_PII,
            "name": "Clean PII from Text",
            "description": "Redacts Personally Identifiable Information from text.",
            "inputs_schema": CleanPIIInputs.model_json_schema(ref_template="#/components/schemas/{model}"),
            "outputs_schema": {
                "type": "object",
                "properties": {
                    "original_text": {"type": "string"},
                    "cleaned_text": {"type": "string"},
                },
            },
        },
        {
            "id": TOOL_GET_PDF_PAGE_URL,
            "name": "Get CCSK PDF Page URL",
            "description": "Gets a local file URL for a specific page of the CCSK PDF.",
            "inputs_schema": GetPDFPageURLInputs.model_json_schema(ref_template="#/components/schemas/{model}"),
            "outputs_schema": {
                "type": "object",
                "properties": {"file_uri": {"type": "string", "format": "uri", "description": "Local file URL."}},
            },
        },
    ]
    return JsonRpcResponse(result={"tools": tools, "resources": []}, id=request_id)


async def mcp_perform_action_impl(params: Dict[str, Any], request_id: Union[str, int, None]) -> JsonRpcResponse:
    tool_id = params.get("tool_id")
    inputs = params.get("inputs", {})

    JSONRPC_INVALID_PARAMS_CODE = -32602
    JSONRPC_METHOD_NOT_FOUND_CODE = -32601
    JSONRPC_INTERNAL_ERROR_CODE = -32603
    SERVER_ERROR_BASE_CODE = -32000
    SERVER_ERROR_GEMINI_UNAVAILABLE = SERVER_ERROR_BASE_CODE - 1
    SERVER_ERROR_GEMINI_TIMEOUT = SERVER_ERROR_BASE_CODE - 2
    SERVER_ERROR_PDF_UPLOAD_FAILED = SERVER_ERROR_BASE_CODE - 3  # Used if get_or_upload_pdf fails
    SERVER_ERROR_PDF_NOT_FOUND = SERVER_ERROR_BASE_CODE - 4

    try:
        if not isinstance(inputs, dict):
            # This indicates a malformed request, rather than an issue with specific input values
            return JsonRpcResponse(
                error=JsonRpcErrorDetail(code=JSONRPC_INVALID_PARAMS_CODE,
                                         message="Invalid 'inputs' parameter format."),
                id=request_id
            )

        if tool_id in [TOOL_GENERATE_QUESTION, TOOL_CLEAN_PII] and (
                not model or not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_API_KEY_PLACEHOLDER"):
            return JsonRpcResponse(
                error=JsonRpcErrorDetail(code=SERVER_ERROR_GEMINI_UNAVAILABLE, message="Service configuration error."),
                id=request_id
            )

        if tool_id == TOOL_GENERATE_QUESTION:
            result = await _execute_generate_question(inputs)
        elif tool_id == TOOL_CLEAN_PII:
            result = await _execute_clean_pii(inputs)
        elif tool_id == TOOL_GET_PDF_PAGE_URL:
            result = await _execute_get_pdf_page_url(inputs)
        else:
            return JsonRpcResponse(
                error=JsonRpcErrorDetail(code=JSONRPC_METHOD_NOT_FOUND_CODE, message="Method not found."),
                id=request_id
            )
        return JsonRpcResponse(result=result, id=request_id)

    except FileNotFoundError:  # From get_or_upload_pdf or _execute_get_pdf_page_uri
        return JsonRpcResponse(
            error=JsonRpcErrorDetail(code=SERVER_ERROR_PDF_NOT_FOUND, message="Required file not found."),
            id=request_id
        )
    except HTTPException as he:
        # Map known HTTPException status codes to generic JSON-RPC errors
        error_code = SERVER_ERROR_BASE_CODE - he.status_code
        error_message = "An error occurred."  # Generic message
        if he.status_code == 504:  # Gemini Timeout
            error_code = SERVER_ERROR_GEMINI_TIMEOUT
            error_message = "Request timed out."
        elif he.status_code == 404:  # PDF resource not found by _execute_get_pdf_page_uri
            error_code = SERVER_ERROR_PDF_NOT_FOUND
            error_message = "Resource not found."
        # Other generic errors from _execute functions
        elif "generating question" in he.detail.lower():
            error_message = "Error generating question."
        elif "cleaning pii" in he.detail.lower():
            error_message = "Error cleaning PII."

        return JsonRpcResponse(
            error=JsonRpcErrorDetail(code=error_code, message=error_message),
            id=request_id
        )
    except (ValueError, TypeError) as ve:  # Catches Pydantic validation errors or bad inputs type
        # For Pydantic errors (invalid inputs)
        return JsonRpcResponse(
            error=JsonRpcErrorDetail(code=JSONRPC_INVALID_PARAMS_CODE, message="Invalid parameters."),
            id=request_id
        )
    except RuntimeError as rte:  # E.g. model not initialized or API key not configured from internal checks
        if "MODEL_UNINITIALIZED" in str(rte) or "API_KEY_NOT_CONFIGURED" in str(rte):
            return JsonRpcResponse(
                error=JsonRpcErrorDetail(code=SERVER_ERROR_GEMINI_UNAVAILABLE, message="Service configuration error."),
                id=request_id
            )
        return JsonRpcResponse(
            error=JsonRpcErrorDetail(code=JSONRPC_INTERNAL_ERROR_CODE, message="Internal server error."),
            id=request_id
        )
    except Exception:  # Catch-all for any other unexpected errors
        return JsonRpcResponse(
            error=JsonRpcErrorDetail(code=JSONRPC_INTERNAL_ERROR_CODE,
                                     message="An unexpected internal server error occurred."),
            id=request_id
        )


@app.post("/mcp", response_model=JsonRpcResponse, summary="Main MCP Endpoint")
async def mcp_router(request: JsonRpcRequest = Body(...)):
    if request.method == "mcp.discover":
        return await mcp_discover_impl(request.id)
    elif request.method == "mcp.perform_action":
        params_to_pass = request.params if request.params is not None else {}
        return await mcp_perform_action_impl(params_to_pass, request.id)
    else:
        return JsonRpcResponse(
            error=JsonRpcErrorDetail(code=-32601, message="Method not found."),  # JSONRPC_METHOD_NOT_FOUND_CODE
            id=request.id
        )




