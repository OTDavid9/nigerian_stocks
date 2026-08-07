from pydantic import BaseModel
from typing import List, Optional
# from datetime import datetime, timedelta
# ---------------------------------------------------------------------------
# Pydantic models 
# ---------------------------------------------------------------------------
class NgxTicker(BaseModel):
    symbol: str
    name: str
    price: float
    change: float
    change_pct: float
    volume: int
    currency: str = "NGN"

class NgxSnapshot(BaseModel):
    exchange: str = "NGX"
    status: str  # "OPEN" or "CLOSED"
    last_updated: str  # ISO date string
    tickers: List[NgxTicker]

class HistoricalDataPoint(BaseModel):
    date: str  # YYYY-MM-DD
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float
    volume: Optional[int] = None

class HistoricalData(BaseModel):
    symbol: str
    exchange: str = "NGX"
    currency: str = "NGN"
    data: List[HistoricalDataPoint]

class SymbolItem(BaseModel):
    symbol: str
    name: str

class SymbolList(BaseModel):
    length: int = 0
    exchange: str = "NGX"
    symbols: List[SymbolItem]
    

# --- Request model for batch endpoints ---
class BatchSymbolsRequest(BaseModel):
    symbols: List[str]

# --- Response model for batch history (live + history) ---
class SymbolHistoryWithLive(BaseModel):
    symbol: str
    name: str
    price: float
    change: float
    change_pct: float
    volume: int
    currency: str = "NGN"
    history: List[HistoricalDataPoint]

class BatchHistoryResponse(BaseModel):
    data: List[SymbolHistoryWithLive]

# ---------------------------------------------------------------------------
# Simple in‑memory cache
# ---------------------------------------------------------------------------
class Symbol(BaseModel):
    symbol: str



class SymbolList(BaseModel):
    symbols: List[str]  # e.g., ["DANGCEM", "GTCO", "ZENITHBANK"]