# ------------------------------------------------------------------
# 3. OPENAI FUNCTION DEFINITIONS (the schema)
# ------------------------------------------------------------------
ollama_tools= [
    {
        "type": "function",
        "function": {
            "name": "get_predictive_report",
            "description": "Get the latest AI predictive report for an NGX stock. Contains technical indicators, model comparison, 5-day price forecast, and reliability assessment. Use when the user asks about a stock's outlook or recommendation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "The NGX stock ticker symbol, e.g. 'GTCO', 'DANGCEM'"
                    }
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Search uploaded financial statements (annual reports, filings) for relevant passages. Use when the user asks a specific question about a company’s financials or notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language question or search phrase, e.g. 'What was the revenue in 2025?'"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_ratio",
            "description": "Retrieve a pre-calculated financial ratio for a stock. Available ratios: current_ratio, quick_ratio, debt_to_equity, return_on_assets, return_on_equity, earnings_per_share, price_to_earnings, dividend_yield.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Stock ticker, e.g. 'ZENITHBANK'"
                    },
                    "ratio_name": {
                        "type": "string",
                        "enum": [
                            "current_ratio",
                            "quick_ratio",
                            "debt_to_equity",
                            "return_on_assets",
                            "return_on_equity",
                            "earnings_per_share",
                            "price_to_earnings",
                            "dividend_yield"
                        ],
                        "description": "The ratio to fetch."
                    }
                },
                "required": ["symbol", "ratio_name"]
            }
        }
    }
]
