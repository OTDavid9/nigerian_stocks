# chat_application/ollama_tools.py

ollama_tools = [
    # ---- Stock tools ----
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
                        "description": "The stock ticker symbol (e.g., GTCO, WEMABANK)."
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
            "description": "Run the full machine‑learning analysis for a stock (technical + forecast). This can take up to 60 seconds.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "The stock ticker symbol (e.g., GTCO, WEMABANK)."
                    }
                },
                "required": ["symbol"]
            }
        }
    },
    # ---- Document tools ----
    {
        "type": "function",
        "function": {
            "name": "get_latest_document_content",
            "description": "Retrieve the full content of the most recently uploaded document (PDF, CSV, etc.) to answer questions based on its text.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_documents",
            "description": "List all uploaded documents (currently returns the latest one).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_search_documents",
            "description": "Perform a semantic search on the uploaded documents based on a query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query."
                    }
                },
                "required": ["query"]
            }
        }
    }
]