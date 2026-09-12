# chat_application/tools.py

import httpx
import logging
import os
from typing import Optional
from .tool_registry import register_tool
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---- Determine base URL ----
ENVIRONMENT = os.getenv("ENVIRONMENT", "Dev")
BASE_URL = os.getenv("BASE_URL")  # explicitly set in .env for production

if not BASE_URL:
    if ENVIRONMENT.lower() == "prod":
        # You must set BASE_URL in your .env for production
        # Fallback to a placeholder (change to your actual Render URL)
        BASE_URL = "https://nigerian-stocks.onrender.com"
        logger.warning("BASE_URL not set. Using fallback: %s", BASE_URL)
    else:
        BASE_URL = "http://localhost:8000"

# Store tokens per session
_session_tokens = {}

def set_session_token(session_id: str, token: str):
    _session_tokens[session_id] = token

def get_session_token(session_id: str) -> Optional[str]:
    return _session_tokens.get(session_id)

# ---------------------------------------------------------------------
# TOOL 1: Get stock report
# ---------------------------------------------------------------------
@register_tool("get_stock_report")
def get_stock_report(symbol: str, session_id: str = "") -> str:
    token = get_session_token(session_id)
    if not token:
        return "Error: Missing authentication token. Please reconnect."

    url = f"{BASE_URL}/api/v1/data-ingest/reports?symbols={symbol.upper()}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            report_data = data.get(symbol.upper())
            if not report_data or report_data.get("error"):
                return f"No report found for {symbol.upper()}. Use `run_stock_analysis` to generate one."

            latest = report_data.get("technical_indicators", {}).get("latest_close")
            if latest is None:
                latest = "N/A"
            sma50 = report_data.get("technical_indicators", {}).get("sma_50", "N/A")
            rsi = report_data.get("technical_indicators", {}).get("rsi", "N/A")
            forecast = report_data.get("forecast_prices", [])
            trend = report_data.get("forecast_trend", "neutral")
            reliability = report_data.get("reliability", "Moderate")
            company = report_data.get("company_name", symbol)

            summary = f"""
📊 **{symbol.upper()} Report** ({company})
- Latest Close: ₦{latest}
- SMA(50): ₦{sma50}
- RSI(14): {rsi}
- Forecast Trend: {trend}
- Model Reliability: {reliability}
- 5‑Day Forecast: {forecast if forecast else 'Not available'}
"""
            return summary.strip()
    except Exception as e:
        logger.error(f"Error fetching report for {symbol}: {e}")
        return f"Failed to retrieve report: {str(e)}"

# ---------------------------------------------------------------------
# TOOL 2: Run stock analysis
# ---------------------------------------------------------------------
@register_tool("run_stock_analysis")
def run_stock_analysis(symbol: str, session_id: str = "") -> str:
    token = get_session_token(session_id)
    if not token:
        return "Error: Missing authentication token. Please reconnect."

    url = f"{BASE_URL}/api/v1/data-ingest/run-single-analysis"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {"symbol": symbol.upper()}

    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            # Fetch the new report
            report_summary = get_stock_report(symbol, session_id)
            return f"✅ Analysis completed for {symbol.upper()}.\n\n{report_summary}"
    except Exception as e:
        logger.error(f"Error running analysis for {symbol}: {e}")
        return f"Failed to run analysis: {str(e)}"

# ---------------------------------------------------------------------
# TOOL 3: Get latest document content
# ---------------------------------------------------------------------
@register_tool("get_latest_document_content")
def get_latest_document_content(session_id: str = "") -> str:
    token = get_session_token(session_id)
    if not token:
        return "Error: Missing authentication token. Please reconnect."

    url = f"{BASE_URL}/api/v1/upload/document"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            doc = resp.json()
            if not doc or not doc.get("content"):
                return "No uploaded document found. Please upload a file first."
            filename = doc.get("filename", "Unknown")
            content = doc.get("content", "")
            if len(content) > 3000:
                content = content[:3000] + "\n... (truncated)"
            return f"📄 Content of '{filename}':\n\n{content}"
    except Exception as e:
        logger.error(f"Error fetching document: {e}")
        return f"Failed to retrieve document: {str(e)}"

# ---------------------------------------------------------------------
# TOOL 4: List documents
# ---------------------------------------------------------------------
@register_tool("list_documents")
def list_documents(session_id: str = "") -> str:
    token = get_session_token(session_id)
    if not token:
        return "Error: Missing authentication token. Please reconnect."

    url = f"{BASE_URL}/api/v1/upload/document"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            doc = resp.json()
            if not doc:
                return "No documents found."
            filename = doc.get("filename", "Unknown")
            doc_id = doc.get("id", "N/A")
            return f"📂 Latest uploaded document:\n- {filename} (ID: {doc_id})"
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        return f"Failed to list documents: {str(e)}"


from pinecone import Pinecone
from dotenv import load_dotenv
load_dotenv()
import os
api_key = os.getenv("PINECONE_API_KEY")

pc = Pinecone(api_key=api_key)

# To get the unique host for an index, 
# see https://docs.pinecone.io/guides/manage-data/target-an-index
index = pc.Index(host="https://sacred-oak-m0mvai4.svc.aped-4627-b74a.pinecone.io")




@register_tool("semantic_search_documents")
def semantic_search_documents(query: str, session_id: str = "") -> str:
    token = get_session_token(session_id)
    if not token:
        return "Error: Missing authentication token. Please reconnect."

    try:
        results = index.search(
            namespace="__default__",
            query={
                "inputs": {"text": query},
                "top_k": 10
            },
            fields=["category", "chunk_text"]
        )
        search_result = getattr(results, "result", None)
        hits = getattr(search_result, "hits", []) if search_result else []
        if not hits:
            return f"No relevant documents found for query: '{query}'"

        response = "📄 Semantic Search Results:\n"
        for match in hits:
            fields = getattr(match, "fields", {}) or {}
            category = fields.get("category", "Unknown")
            chunk_text = fields.get("chunk_text", "")
            response += f"- Category: {category}\n  Text: {chunk_text[:200]}...\n"
        return response.strip()
    except Exception as e:
        logger.error(f"Error performing semantic search: {e}")
        return f"Failed to perform semantic search: {str(e)}"