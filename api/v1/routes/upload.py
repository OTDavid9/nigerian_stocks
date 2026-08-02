import os
import shutil
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends
from fastapi.responses import JSONResponse
from pathlib import Path
import PyPDF2
import docx
import io
from core.deps import get_current_user
import fitz  # PyMuPDF for better PDF extraction
from core.database import users_documents

router = APIRouter(
    prefix="/upload",
    tags=["Upload"]
)

# Create upload directory if it doesn't exist
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# # Path for the extracted text file
# DOCUMENT_TXT = Path("document.txt")

# @router.post("/document")
# async def upload_document(
#     file: UploadFile = File(...),
#     current_user=Depends(get_current_user)
# ):
#     """
#     Upload a document (PDF, image, Word, text) and extract text content.
#     Saves extracted text to document.txt
#     """
    
#     # Validate file type
#     allowed_extensions = ['.pdf', '.png', '.jpg', '.jpeg', '.doc', '.docx', '.txt']
#     file_extension = Path(file.filename).suffix.lower()
    
#     if file_extension not in allowed_extensions:
#         raise HTTPException(
#             status_code=400,
#             detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
#         )
    
#     try:
#         # Read file content
#         content = await file.read()
        
#         # Extract text based on file type
#         extracted_text = ""
        
#         if file_extension == '.pdf':
#             extracted_text = extract_text_from_pdf(content)
#         elif file_extension == '.txt':
#             extracted_text = content.decode('utf-8')
#         elif file_extension == '.docx':
#             extracted_text = extract_text_from_docx(content)
#         elif file_extension in ['.png', '.jpg', '.jpeg']:
#             # For images, we can't extract text directly, but we'll note it
#             extracted_text = f"Image file uploaded: {file.filename}\nPlease use OCR or image analysis for text extraction."
#         elif file_extension in ['.doc']:
#             extracted_text = "Legacy Word documents (.doc) are not supported. Please convert to .docx or .pdf."
#         else:
#             extracted_text = f"File uploaded: {file.filename}\nContent extraction not available for this format."
        
#         # Save extracted text to document.txt
#         with open(DOCUMENT_TXT, 'w', encoding='utf-8') as f:
#             f.write(f"Document: {file.filename}\n")
#             f.write(f"Type: {file_extension}\n")
#             f.write("=" * 50 + "\n\n")
#             f.write(extracted_text)
        
#         # Also save the original file (optional)
#         file_path = UPLOAD_DIR / file.filename
#         with open(file_path, 'wb') as f:
#             f.write(content)
        
#         return JSONResponse({
#             "message": "File uploaded and processed successfully",
#             "filename": file.filename,
#             "characters": len(extracted_text),
#             "file_path": str(file_path),
#             "text_preview": extracted_text[:500] + "..." if len(extracted_text) > 500 else extracted_text
#         })
        
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

def extract_text_from_pdf(content: bytes) -> str:
    """Extract text from PDF using PyMuPDF (fitz) for better extraction"""
    try:
        import fitz
        doc = fitz.open(stream=content, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text.strip() if text else "No text could be extracted from the PDF."
    except:
        # Fallback to PyPDF2
        try:
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text()
            return text.strip() if text else "No text could be extracted from the PDF."
        except:
            return "PDF extraction failed. The file might be scanned or encrypted."

def extract_text_from_docx(content: bytes) -> str:
    """Extract text from DOCX file"""
    try:
        doc = docx.Document(io.BytesIO(content))
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text.strip()
    except:
        return "DOCX extraction failed."

# @router.get("/document")
# async def get_document_text(current_user=Depends(get_current_user)):
#     """Retrieve the extracted document text"""
#     try:
#         if DOCUMENT_TXT.exists():
#             with open(DOCUMENT_TXT, 'r', encoding='utf-8') as f:
#                 content = f.read()
#             return {"content": content}
#         else:
#             return {"content": "No document has been uploaded yet."}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error reading document: {str(e)}")

from datetime import datetime
from bson import ObjectId
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.responses import JSONResponse

from core.database import users_documents
from core.deps import get_current_user

router = APIRouter(
    prefix="/upload",
    tags=["Upload"],
)


@router.post("/document")
async def upload_document(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):

    allowed_extensions = [
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".doc",
        ".docx",
        ".txt",
    ]

    extension = Path(file.filename).suffix.lower()

    if extension not in allowed_extensions:
        raise HTTPException(
            400,
            "Unsupported file type",
        )

    content = await file.read()

    if extension == ".pdf":
        extracted_text = extract_text_from_pdf(content)

    elif extension == ".docx":
        extracted_text = extract_text_from_docx(content)

    elif extension == ".txt":
        extracted_text = content.decode("utf-8")

    elif extension in [".png", ".jpg", ".jpeg"]:
        extracted_text = (
            "OCR not implemented yet."
        )

    else:
        extracted_text = ""

    document = {
        "user_id": ObjectId(current_user["_id"]),
        "filename": file.filename,
        "extension": extension,
        "content": extracted_text,
        "file_size": len(content),
        "uploaded_at": datetime.utcnow(),
    }

    result = users_documents.insert_one(document)

    return JSONResponse(
        {
            "id": str(result.inserted_id),
            "filename": file.filename,
            "characters": len(extracted_text),
            "message": "Document uploaded successfully",
        }
    )

@router.get("/document")
async def get_document(
    current_user=Depends(get_current_user),
):

    document = users_documents.find_one(
        {
            "user_id": ObjectId(current_user["_id"])
        },
        sort=[("uploaded_at", -1)],
    )

    if document is None:
        raise HTTPException(
            404,
            "No document found",
        )

    return {
        "id": str(document["_id"]),
        "filename": document["filename"],
        "content": document["content"],
        "uploaded_at": document["uploaded_at"],
    }

@router.get("/documents")
async def get_documents(
    current_user=Depends(get_current_user),
):

    cursor = users_documents.find(
        {
            "user_id": ObjectId(current_user["_id"])
        }
    ).sort("uploaded_at", -1)

    documents = []

    for doc in cursor:

        documents.append(
            {
                "id": str(doc["_id"]),
                "filename": doc["filename"],
                "extension": doc["extension"],
                "uploaded_at": doc["uploaded_at"],
                "characters": len(doc["content"]),
            }
        )

    return documents

@router.delete("/document/{document_id}")
async def delete_document(
    document_id: str,
    current_user=Depends(get_current_user),
):

    result = users_documents.delete_one(
        {
            "_id": ObjectId(document_id),
            "user_id": ObjectId(current_user["_id"]),
        }
    )

    if result.deleted_count == 0:
        raise HTTPException(
            404,
            "Document not found",
        )

    return {
        "message": "Document deleted"
    }