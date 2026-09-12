# agents/stock_agent.py

import json
import logging
import os
import time
from typing import Any, AsyncGenerator, Dict, List, Optional
import asyncio

import httpx
from openai import OpenAI, PermissionDeniedError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---- Configuration ----
OPENAI_API_KEY = os.getenv("LLM_API_KEY")
MODEL_NAME = os.getenv("LLM_MODEL_NAME", "llama3.2:3b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://ollama.com/v1")

# ---- Internal API base ----
API_BASE = os.getenv("BASE_URL")
if not API_BASE:
    ENVIRONMENT = os.getenv("ENVIRONMENT", "Dev")
    if ENVIRONMENT.lower() == "prod":
        API_BASE = "https://your-app.onrender.com"
    else:
        API_BASE = "http://localhost:8000"

# ---- Tool definitions ----
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_stock_report",
            "description": "Retrieve the latest predictive report for a given NGX stock symbol (e.g., GTCO, WEMABANK).",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g., GTCO)"
                    }
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_stock_analysis",
            "description": "Run the full ML analysis for a stock (can take up to 60 seconds).",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g., GTCO)"
                    }
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_latest_document_content",
            "description": "Retrieve the full content of the most recently uploaded document.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_documents",
            "description": "List all uploaded documents (returns the latest one).",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_search_documents",
            "description": "Perform a semantic search across uploaded documents from pinecone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query string."
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of top results to return.",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    }
    
]

# ---- Async internal API caller ----
async def _call_internal_api_async(
    endpoint: str,
    method: str = "GET",
    data: dict = None,
    timeout: float = 60.0
) -> dict:
    """
    Async call to internal API. No authentication required.
    """
    headers = {"Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    url = f"{API_BASE}{endpoint}"
    logger.info(f"Calling internal API (async): {method} {url} (timeout={timeout}s)")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method.upper() == "GET":
                resp = await client.get(url, headers=headers)
            else:
                resp = await client.post(url, json=data, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        logger.error(f"Timeout after {timeout}s calling {url}")
        raise Exception(f"Request timed out after {timeout} seconds.")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
        raise Exception(f"API returned {e.response.status_code}: {e.response.text[:200]}")
    except Exception as e:
        logger.error(f"API call failed: {e}")
        raise

# ---- Tool implementations (async) ----
async def get_stock_report_async(symbol: str, session_id: str = "") -> str:
    try:
        data = await _call_internal_api_async(
            f"/api/v1/data-ingest/reports?symbols={symbol.upper()}",
            timeout=60.0
        )
        report = data.get(symbol.upper())
        if not report or report.get("error"):
            return f"No report found for {symbol.upper()}. Use `run_stock_analysis` to generate one."
        latest = report.get("technical_indicators", {}).get("latest_close", "N/A")
        sma50 = report.get("technical_indicators", {}).get("sma_50", "N/A")
        rsi = report.get("technical_indicators", {}).get("rsi", "N/A")
        forecast = report.get("forecast_prices", [])
        trend = report.get("forecast_trend", "neutral")
        reliability = report.get("reliability", "Moderate")
        company = report.get("company_name", symbol)
        return f"""
📊 **{symbol.upper()} Report** ({company})
- Latest Close: ₦{latest}
- SMA(50): ₦{sma50}
- RSI(14): {rsi}
- Forecast Trend: {trend}
- Model Reliability: {reliability}
- 5‑Day Forecast: {forecast if forecast else 'Not available'}
""".strip()
    except Exception as e:
        logger.error(f"get_stock_report error: {e}")
        return f"Failed to retrieve report: {str(e)}"

async def run_stock_analysis_async(symbol: str, session_id: str = "") -> str:
    try:
        await _call_internal_api_async(
            "/api/v1/data-ingest/run-single-analysis",
            method="POST",
            data={"symbol": symbol.upper()},
            timeout=300.0
        )
        await asyncio.sleep(2)  # allow DB write
        report = await get_stock_report_async(symbol)
        return f"✅ Analysis completed for {symbol.upper()}.\n\n{report}"
    except Exception as e:
        logger.error(f"run_stock_analysis error: {e}")
        return f"Failed to run analysis: {str(e)}"

async def get_latest_document_content_async(session_id: str = "") -> str:
    try:
        data = await _call_internal_api_async("/api/v1/upload/document", timeout=60.0)
        if not data or not data.get("content"):
            return "No uploaded document found. Please upload a file first."
        content = data["content"]
        filename = data.get("filename", "Unknown")
        if len(content) > 3000:
            content = content[:3000] + "\n... (truncated)"
        return f"📄 Content of '{filename}':\n\n{content}"
    except Exception as e:
        logger.error(f"get_latest_document_content error: {e}")
        return f"Failed to retrieve document: {str(e)}"

async def list_documents_async(session_id: str = "") -> str:
    try:
        data = await _call_internal_api_async("/api/v1/upload/document", timeout=60.0)
        if not data:
            return "No documents found."
        filename = data.get("filename", "Unknown")
        doc_id = data.get("id", "N/A")
        return f"📂 Latest uploaded document:\n- {filename} (ID: {doc_id})"
    except Exception as e:
        logger.error(f"list_documents error: {e}")
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

async def semantic_search_documents_async(query: str, top_k: int = 5, session_id: str = "") -> str:
    try:
        results = index.search(
            namespace="__default__",
            query={
                "inputs": {"text": query},
                "top_k": top_k
            },
            fields=["category", "chunk_text"]
        )
        search_result = getattr(results, "result", None)
        hits = getattr(search_result, "hits", []) if search_result else []
        if not hits:
            return "No relevant documents found for the query."
        
        response = "📄 Semantic Search Results:\n"
        for match in hits:
            fields = getattr(match, "fields", {}) or {}
            category = fields.get("category", "Unknown")
            chunk_text = fields.get("chunk_text", "")
            response += f"- Category: {category}\n  Text: {chunk_text[:200]}...\n"
        
        return response.strip()
    except Exception as e:
        logger.error(f"semantic_search_documents error: {e}")
        return f"Failed to perform semantic search: {str(e)}"   
# ---- Agent class ----
class StockAgent:
    def __init__(self, session_id: str, token: str = None, model: str = None):
        self.session_id = session_id
        self.model = model or MODEL_NAME
        self.system_prompt = """
You are a helpful AI assistant specialized in Nigerian stock market analysis.

You have access to tools that can fetch stock reports, run analyses, and retrieve uploaded document content.

Rules:
1. Use tools when they are required to answer the user's request.
2. Never invent the result of a tool call.
3. If a tool fails, clearly explain the failure.
4. Use previous conversation context when answering.
5. Be concise but useful.
6. Do not expose internal tool execution details unless necessary.
"""
        self.history: List[Dict] = []
        self.available_tools = {
            "get_stock_report": get_stock_report_async,
            "run_stock_analysis": run_stock_analysis_async,
            "get_latest_document_content": get_latest_document_content_async,
            "list_documents": list_documents_async,
            "semantic_search_documents": semantic_search_documents_async,
        }

    def _build_messages(self):
        return [{"role": "system", "content": self.system_prompt}] + self.history

    async def _execute_tool_async(self, tool_name: str, arguments: dict) -> str:
        func = self.available_tools.get(tool_name)
        if not func:
            return f"Unknown tool: {tool_name}"
        try:
            args = arguments.copy()
            args["session_id"] = self.session_id
            result = await func(**args)
            return result
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return f"Tool execution failed: {str(e)}"

    async def stream_response(self, user_message: str) -> AsyncGenerator[str, None]:
        self.history.append({"role": "user", "content": user_message})

        client = OpenAI(base_url=OLLAMA_BASE_URL, api_key=OPENAI_API_KEY)
        messages = self._build_messages()

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                stream=False,
                temperature=0.9,
            )
        except PermissionDeniedError as e:
            yield f"❌ Model error: {e}. Please check your model name and subscription. Consider using a free model like 'llama3.2:3b' or setting OLLAMA_BASE_URL to a local endpoint."
            return
        except Exception as e:
            yield f"❌ Unexpected error: {str(e)}"
            return

        assistant_message = response.choices[0].message
        self.history.append(assistant_message.model_dump())

        if assistant_message.tool_calls:
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                result = await self._execute_tool_async(tool_name, args)
                self.history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": result
                })

            try:
                stream = client.chat.completions.create(
                    model=self.model,
                    messages=self._build_messages(),
                    stream=True,
                    temperature=0.9,
                ) # type: ignore
            except PermissionDeniedError as e:
                yield f"❌ Model error during streaming: {e}"
                return
            except Exception as e:
                yield f"❌ Unexpected error during streaming: {str(e)}"
                return

            full_response = ""
            for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    full_response += delta
                    yield delta
            self.history.append({"role": "assistant", "content": full_response})
        else:
            if assistant_message.content:
                yield assistant_message.content
                self.history.append({"role": "assistant", "content": assistant_message.content})
            else:
                yield "I'm sorry, I couldn't generate a response."

    def clear_history(self):
        self.history = []