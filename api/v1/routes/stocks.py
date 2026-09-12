import os
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import httpx
from datetime import timedelta
from models.stocks import *
import json
from pathlib import Path
from fastapi import (
    APIRouter, HTTPException, Query)
from core.database import stocks_data  # MongoDB collection
from bson import ObjectId

router = APIRouter(tags=["NGX Stocks"])
# Load environment variables
load_dotenv()
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY")
if not SCRAPER_API_KEY:
    raise RuntimeError("SCRAPER_API_KEY is not defined in environment variables")

AF_BASE = "https://afx.kwayisi.org"

client = httpx.AsyncClient(timeout=60.0)

_cache: Dict[str, dict] = {}  # key -> {"data": ..., "timestamp": float}

def _cache_set(key: str, data: any) -> None:
    _cache[key] = {"data": data, "timestamp": time.time()}

def _cache_get(key: str, max_age_seconds: float) -> Optional[any]:
    entry = _cache.get(key)
    if entry and (time.time() - entry["timestamp"]) < max_age_seconds:
        return entry["data"]
    return None

# ---------------------------------------------------------------------------
# MongoDB Storage Helpers
# ---------------------------------------------------------------------------

def get_symbol_document(symbol: str) -> Optional[Dict]:
    """Get the document for a symbol from MongoDB."""
    return stocks_data.find_one({"symbol": symbol.upper()})

def load_symbol_history(symbol: str) -> List[HistoricalDataPoint]:
    """Load existing history points from MongoDB for a symbol."""
    doc = get_symbol_document(symbol)
    if not doc or "history" not in doc:
        return []
    return [HistoricalDataPoint(**p) for p in doc["history"]]

def save_symbol_history(symbol: str, points: List[HistoricalDataPoint]):
    """Save (or update) the symbol's history in MongoDB."""
    symbol_upper = symbol.upper()
    
    # Convert points to dict for storage
    points_dict = [p.dict() for p in points]
    
    # Update or insert the document
    stocks_data.update_one(
        {"symbol": symbol_upper},
        {
            "$set": {
                "symbol": symbol_upper,
                "history": points_dict,
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "data_points": len(points_dict)
            }
        },
        upsert=True
    )

def get_symbol_metadata() -> Dict[str, str]:
    """Get metadata for all symbols (latest date per symbol)."""
    metadata = {}
    # Get all documents with their latest date
    cursor = stocks_data.find({}, {"symbol": 1, "history": 1})
    for doc in cursor:
        symbol = doc.get("symbol")
        history = doc.get("history", [])
        if history:
            # Get the latest date from history
            latest = max(history, key=lambda x: x.get("date", ""))
            metadata[symbol] = latest.get("date", "")
    return metadata

def get_all_symbols_from_db() -> List[str]:
    """Get all unique symbols from MongoDB."""
    cursor = stocks_data.distinct("symbol")
    return [s for s in cursor if s]

def get_latest_date_for_symbol(symbol: str) -> Optional[str]:
    """Get the latest date for a symbol from MongoDB."""
    doc = get_symbol_document(symbol)
    if not doc or "history" not in doc:
        return None
    history = doc["history"]
    if not history:
        return None
    latest = max(history, key=lambda x: x.get("date", ""))
    return latest.get("date")

# ---------------------------------------------------------------------------
# Helper: market open check (same logic as original)
# ---------------------------------------------------------------------------
def is_ngx_open() -> bool:
    now = datetime.now(timezone.utc)
    day = now.weekday()  # Monday=0 .. Sunday=6
    minutes = now.hour * 60 + now.minute
    # 08:30 UTC to 13:30 UTC (09:30–14:30 WAT) – adjust if needed
    return 0 <= day <= 4 and 510 <= minutes < 810

# ---------------------------------------------------------------------------
# Scraper proxy builder
# ---------------------------------------------------------------------------
# def build_proxy_url(target_url: str) -> str:
#     return f"http://api.scraperapi.com/?api_key={SCRAPER_API_KEY}&url={httpx.URL(target_url)}"

def build_proxy_url(target_url: str) -> str:
    """
    Build a proxy URL for the ScraperAPI service.
    Ensures the target URL is properly encoded.
    """
    return f"http://api.scraperapi.com/?api_key={SCRAPER_API_KEY}&url={httpx.URL(target_url)}"

# ---------------------------------------------------------------------------
# Snapshot fetching (NGX live)
# ---------------------------------------------------------------------------
async def fetch_ngx_snapshot() -> NgxSnapshot:
    # Check cache (5 minutes for live data)
    cached = _cache_get("ngx_snapshot", max_age_seconds=300)
    if cached:
        return cached

    print("[NGX] Starting full snapshot fetch...")
    try:
        all_tickers: List[NgxTicker] = []
        page = 1
        max_empty_pages = 0  # stop after 1 empty page (safety)

        while True:
            page_url = f"{AF_BASE}/ngx/" if page == 1 else f"{AF_BASE}/ngx/?page={page}"
            proxy_url = build_proxy_url(page_url)
            print(f"  Fetching page {page}...")
            resp = await client.get(proxy_url)
            html = resp.text
            soup = BeautifulSoup(html, "lxml")

            # Extract rows from this page
            rows = soup.select("div.t table tbody tr")
            page_tickers = []
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 4:
                    continue
                symbol = cells[0].get_text(strip=True)
                name = cells[1].get_text(strip=True) if len(cells) > 1 else symbol
                volume_text = cells[2].get_text(strip=True).replace(",", "")
                price_text = cells[3].get_text(strip=True).replace(",", "")
                change_text = cells[4].get_text(strip=True).replace(",", "") if len(cells) > 4 else "0"

                if not symbol:
                    continue
                try:
                    price = float(price_text)
                except ValueError:
                    continue
                try:
                    change = float(change_text.replace("+", ""))
                except ValueError:
                    change = 0.0

                prev_price = price - change
                change_pct = (change / prev_price * 100) if prev_price else 0.0
                change_pct = round(change_pct, 2)

                page_tickers.append(NgxTicker(
                    symbol=symbol,
                    name=name,
                    price=price,
                    change=change,
                    change_pct=change_pct,
                    volume=int(volume_text) if volume_text.isdigit() else 0,
                ))

            if not page_tickers:
                max_empty_pages += 1
                if max_empty_pages >= 2:  # two consecutive empty pages → stop
                    break
            else:
                max_empty_pages = 0
                all_tickers.extend(page_tickers)

            # Stop if we've fetched a lot of pages and still no end (safety)
            if page > 10:
                print("  Reached max page limit (10). Stopping.")
                break

            page += 1
            await asyncio.sleep(1.0)  # gentle delay between pages

        if all_tickers:
            snapshot = NgxSnapshot(
                status="OPEN" if is_ngx_open() else "CLOSED",
                last_updated=datetime.now(timezone.utc).isoformat(),
                tickers=all_tickers,
            )
            _cache_set("ngx_snapshot", snapshot)
            return snapshot

    except Exception as e:
        print(f"[NGX] Snapshot fetch failed: {e}")
        cached = _cache_get("ngx_snapshot", max_age_seconds=99999)
        if cached:
            return cached

    raise HTTPException(status_code=502, detail="Failed to fetch NGX snapshot and no cache available")

# ---------------------------------------------------------------------------
# History fetching (for a symbol)
# ---------------------------------------------------------------------------
import asyncio

def parse_highcharts_script(js_text: str) -> List[HistoricalDataPoint]:
    points: List[HistoricalDataPoint] = []
    # Match data array similar to original
    pattern = r'\[d\("(\d{4}-\d{2}-\d{2})"\)\s*,\s*([\d.]+)\]'
    matches = re.findall(pattern, js_text)
    for date_str, close_str in matches:
        try:
            close = float(close_str)
        except ValueError:
            continue
        points.append(HistoricalDataPoint(date=date_str, close=close))
    # Sort ascending by date
    points.sort(key=lambda x: x.date)
    return points

# async def fetch_ngx_history(symbol: str) -> HistoricalData:
#     symbol_upper = symbol.upper()
#     cache_key = f"ngx_history_{symbol_upper}"
#     cached = _cache_get(cache_key, max_age_seconds=86400)  # 24h
#     if cached:
#         return cached

#     # 1. Try highcharts chart endpoint
#     slug = "" if symbol_upper == "ASI" else f"/{symbol.lower()}"
#     chart_url = f"{AF_BASE}/chart/ngx{slug}"
#     print(f"[NGX] Trying chart endpoint for {symbol_upper}: {chart_url}")
#     try:
#         resp = await client.get(build_proxy_url(chart_url))
#         js = resp.text
#         points = parse_highcharts_script(js)
#         if points:
#             result = HistoricalData(symbol=symbol_upper, data=points)
#             _cache_set(cache_key, result)
#             return result
#     except Exception as e:
#         print(f"Chart fetch failed for {symbol_upper}: {e}")

#     # 2. Fallback: HTML page with data-hist table
#     page_url = f"{AF_BASE}/ngx/{symbol.lower()}.html"
#     print(f"[NGX] Trying HTML fallback for {symbol_upper}: {page_url}")
#     try:
#         resp = await client.get(build_proxy_url(page_url))
#         soup = BeautifulSoup(resp.text, "lxml")
#         points: List[HistoricalDataPoint] = []
#         table = soup.select_one("table[data-hist]")
#         if table:
#             for row in table.select("tbody tr"):
#                 cells = row.find_all("td")
#                 if len(cells) < 3:
#                     continue
#                 date_text = cells[0].get_text(strip=True)
#                 volume_text = cells[1].get_text(strip=True).replace(",", "")
#                 close_text = cells[2].get_text(strip=True)
#                 try:
#                     close = float(close_text)
#                 except ValueError:
#                     continue
#                 if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_text):
#                     continue
#                 points.append(HistoricalDataPoint(
#                     date=date_text,
#                     close=close,
#                     volume=int(volume_text) if volume_text.isdigit() else None,
#                 ))
#         if points:
#             points.sort(key=lambda x: x.date)
#             result = HistoricalData(symbol=symbol_upper, data=points)
#             _cache_set(cache_key, result)
#             return result
#     except Exception as e:
#         print(f"HTML fallback failed for {symbol_upper}: {e}")

#     # Return stale cache if exists
#     stale = _cache_get(cache_key, max_age_seconds=99999)
#     if stale:
#         return stale

#     raise HTTPException(status_code=404, detail=f"No data found for NGX symbol: {symbol_upper}")
def filter_by_range(points: List[HistoricalDataPoint], range_str: str) -> List[HistoricalDataPoint]:
    """Filter points to the last N years based on range string like '5y'."""
    if not points or range_str is None:
        return points
    # Parse range (e.g., "5y" -> 5 years)
    if range_str.endswith('y'):
        years = int(range_str[:-1])
        days = years * 365
    else:
        # Default to 5 years if unknown
        days = 5 * 365
    sorted_points = sorted(points, key=lambda x: x.date)
    latest = datetime.strptime(sorted_points[-1].date, "%Y-%m-%d")
    cutoff = latest - timedelta(days=days)
    return [p for p in sorted_points if datetime.strptime(p.date, "%Y-%m-%d") >= cutoff]

async def fetch_ngx_history(symbol: str, range: str = "5y") -> HistoricalData:
    symbol_upper = symbol.upper()
    cache_key = f"ngx_history_{symbol_upper}_{range}"  # include range in cache key
    cached = _cache_get(cache_key, max_age_seconds=86400)
    if cached:
        return cached

    # 1. Try highcharts chart endpoint with range parameter
    slug = "" if symbol_upper == "ASI" else f"/{symbol.lower()}"
    chart_url = f"{AF_BASE}/chart/ngx{slug}?range={range}"   # <-- ADD RANGE
    print(f"[NGX] Trying chart endpoint for {symbol_upper}: {chart_url}")
    try:
        resp = await client.get(build_proxy_url(chart_url))
        js = resp.text
        points = parse_highcharts_script(js)
        if points:
            result = HistoricalData(symbol=symbol_upper, data=points)
            _cache_set(cache_key, result)
            return result
    except Exception as e:
        print(f"Chart fetch failed for {symbol_upper}: {e}")

    # 2. Fallback: HTML page – we can't easily pass range to HTML, so we still filter after fetch
    page_url = f"{AF_BASE}/ngx/{symbol.lower()}.html"
    print(f"[NGX] Trying HTML fallback for {symbol_upper}: {page_url}")
    try:
        resp = await client.get(build_proxy_url(page_url))
        soup = BeautifulSoup(resp.text, "lxml")
        points: List[HistoricalDataPoint] = []
        table = soup.select_one("table[data-hist]")
        if table:
            for row in table.select("tbody tr"):
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue
                date_text = cells[0].get_text(strip=True)
                volume_text = cells[1].get_text(strip=True).replace(",", "")
                close_text = cells[2].get_text(strip=True)
                try:
                    close = float(close_text)
                except ValueError:
                    continue
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_text):
                    continue
                points.append(HistoricalDataPoint(
                    date=date_text,
                    close=close,
                    volume=int(volume_text) if volume_text.isdigit() else None,
                ))
        if points:
            points.sort(key=lambda x: x.date)
            # After HTML fallback, filter to the last 5 years (or whatever range was requested)
            filtered_points = filter_by_range(points, range)
            result = HistoricalData(symbol=symbol_upper, data=filtered_points)
            _cache_set(cache_key, result)
            return result
    except Exception as e:
        print(f"HTML fallback failed for {symbol_upper}: {e}")

    # Stale cache – also filter
    stale = _cache_get(cache_key, max_age_seconds=99999)
    if stale:
        return stale

    raise HTTPException(status_code=404, detail=f"No data found for NGX symbol: {symbol_upper}")

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/markets/ngx/live", response_model=NgxSnapshot)
async def get_live_snapshot():
    return await fetch_ngx_snapshot()

@router.get("/history/ngx/{symbol}", response_model=HistoricalData)
async def get_history(
    symbol: str,
    range: Optional[str] = Query("5y", description="Time range (currently unused)")
):
    return await fetch_ngx_history(symbol)

@router.get("/symbols/ngx", response_model=SymbolList)
async def get_ngx_symbols():
    """Return all available NGX symbols (unique) with count."""
    snapshot = await fetch_ngx_snapshot()
    seen = set()
    unique = []
    for t in snapshot.tickers:
        if t.symbol not in seen:
            seen.add(t.symbol)
            unique.append(SymbolItem(symbol=t.symbol, name=t.name))
    return SymbolList(length=len(unique), symbols=unique)

@router.post("/markets/ngx/live/batch")
async def get_batch_live(request: BatchSymbolsRequest):
    """Return live data for a list of symbols."""
    snapshot = await fetch_ngx_snapshot()
    # Build a lookup dictionary
    lookup = {t.symbol.upper(): t for t in snapshot.tickers}
    result = []
    missing = []
    for sym in request.symbols:
        ticker = lookup.get(sym.upper())
        if ticker:
            result.append(ticker)
        else:
            missing.append(sym)
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Symbols not found: {', '.join(missing)}"
        )
    return {"symbols": result}

def filter_last_year(points: List[HistoricalDataPoint]) -> List[HistoricalDataPoint]:
    """Keep only points with date >= today - 365 days."""
    cutoff = datetime.now().date() - timedelta(days=365)
    return [p for p in points if datetime.strptime(p.date, "%Y-%m-%d").date() >= cutoff]

@router.post("/history/ngx/batch/last-year")
async def get_batch_history_last_year(request: BatchSymbolsRequest) -> BatchHistoryResponse:
    """
    For each requested symbol, return its live snapshot data + history for the last 1 year.
    """
    # 1. Get live data for all symbols (to attach name, price, etc.)
    snapshot = await fetch_ngx_snapshot()
    ticker_lookup = {t.symbol.upper(): t for t in snapshot.tickers}

    results = []
    for sym in request.symbols:
        sym_upper = sym.upper()
        ticker = ticker_lookup.get(sym_upper)
        if not ticker:
            raise HTTPException(
                status_code=404,
                detail=f"Symbol '{sym}' not found in live snapshot"
            )

        # 2. Fetch full history (cached or fresh)
        history_data = await fetch_ngx_history(sym)  # This returns HistoricalData
        # 3. Filter to last year
        last_year_points = filter_last_year(history_data.data)

        # 4. Build combined object
        results.append(SymbolHistoryWithLive(
            symbol=ticker.symbol,
            name=ticker.name,
            price=ticker.price,
            change=ticker.change,
            change_pct=ticker.change_pct,
            volume=ticker.volume,
            currency=ticker.currency,
            history=last_year_points,
        ))

    return BatchHistoryResponse(data=results)

@router.get("/stocks/data/all")
async def get_all_stocks_data():
    """
    Get all stock data from MongoDB.
    """
    try:
        cursor = stocks_data.find({}, {"_id": 0})  # Exclude _id field
        data = list(cursor)
        return {
            "count": len(data),
            "data": data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching data: {str(e)}")

@router.get("/stocks/data/{symbol}")
async def get_stock_data_by_symbol(symbol: str):
    """
    Get stock data for a specific symbol from MongoDB.
    """
    try:
        doc = stocks_data.find_one({"symbol": symbol.upper()}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")
        return doc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching data: {str(e)}")

# ---------------------------------------------------------------------------
# Sync all historical data to MongoDB
# ---------------------------------------------------------------------------
@router.post("/history/ngx/sync-all")
async def sync_all_historical_data():
    """
    Sync all symbols' historical data to MongoDB.
    - Gets all symbols from the live snapshot.
    - For each symbol, fetches complete history (from cache or scraper).
    - Merges only new dates into the MongoDB collection.
    """
    snapshot = await fetch_ngx_snapshot()
    symbols = list({t.symbol for t in snapshot.tickers})  # unique symbols

    updated_count = 0
    new_points_total = 0
    skipped_count = 0
    errors = []

    for symbol in symbols:
        try:
            # Fetch full history for the symbol (respects internal cache)
            hist = await fetch_ngx_history(symbol)
        except HTTPException as e:
            errors.append(f"{symbol}: {str(e)}")
            continue

        if not hist.data:
            skipped_count += 1
            continue

        # Get existing points from MongoDB
        existing = load_symbol_history(symbol)
        existing_dates = {p.date for p in existing}

        # New points = those not already in the database
        new_points = [p for p in hist.data if p.date not in existing_dates]
        if not new_points:
            skipped_count += 1
            continue

        # Merge and sort
        merged = sorted(existing + new_points, key=lambda x: x.date)
        
        # Save to MongoDB
        save_symbol_history(symbol, merged)
        
        updated_count += 1
        new_points_total += len(new_points)
        
        # Log progress
        print(f"[SYNC] {symbol}: Added {len(new_points)} new points (total: {len(merged)})")

    return {
        "message": "Sync completed successfully",
        "total_symbols_checked": len(symbols),
        "symbols_updated": updated_count,
        "symbols_skipped": skipped_count,
        "new_data_points_added": new_points_total,
        "errors": errors if errors else None
    }

@router.post("/history/ngx/sync-single/{symbol}")
async def sync_single_symbol(symbol: str):
    """
    Sync a single symbol's historical data to MongoDB.
    """
    try:
        # Fetch history
        hist = await fetch_ngx_history(symbol)
        if not hist.data:
            raise HTTPException(status_code=404, detail=f"No data found for symbol: {symbol}")

        # Get existing points from MongoDB
        existing = load_symbol_history(symbol)
        existing_dates = {p.date for p in existing}

        # New points
        new_points = [p for p in hist.data if p.date not in existing_dates]
        
        # Merge and save
        merged = sorted(existing + new_points, key=lambda x: x.date)
        save_symbol_history(symbol, merged)

        return {
            "message": f"Sync completed for {symbol}",
            "symbol": symbol.upper(),
            "total_points": len(merged),
            "new_points_added": len(new_points)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error syncing symbol: {str(e)}")

@router.delete("/stocks/data/{symbol}")
async def delete_stock_data(symbol: str):
    """
    Delete stock data for a specific symbol from MongoDB.
    """
    try:
        result = stocks_data.delete_one({"symbol": symbol.upper()})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")
        return {"message": f"Data for '{symbol}' deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting data: {str(e)}")

@router.get("/stocks/data/stats")
async def get_stocks_stats():
    """
    Get statistics about the stock data in MongoDB.
    """
    try:
        total_symbols = stocks_data.count_documents({})
        total_points = 0
        
        # Get total data points across all symbols
        pipeline = [
            {"$project": {"point_count": {"$size": "$history"}}},
            {"$group": {"_id": None, "total": {"$sum": "$point_count"}}}
        ]
        result = list(stocks_data.aggregate(pipeline))
        total_points = result[0]["total"] if result else 0
        
        # Get latest update times
        latest_updates = list(stocks_data.find(
            {}, 
            {"symbol": 1, "last_updated": 1, "data_points": 1}
        ).sort("last_updated", -1).limit(5))
        
        return {
            "total_symbols": total_symbols,
            "total_data_points": total_points,
            "latest_updates": latest_updates
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching stats: {str(e)}")
# import os
# import re
# import time
# from datetime import datetime, timezone
# from typing import Dict, List, Optional
# from bs4 import BeautifulSoup
# from dotenv import load_dotenv
# import httpx
# from datetime import timedelta
# from models.stocks import *
# import json
# from pathlib import Path
# from fastapi import (
#     APIRouter,  HTTPException, Query)

# from core.database import stocks_data


# router = APIRouter(tags=["NGX Stocks"])
# # Load environment variables
# load_dotenv()
# SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY")
# if not SCRAPER_API_KEY:
#     raise RuntimeError("SCRAPER_API_KEY is not defined in environment variables")

# AF_BASE = "https://afx.kwayisi.org"

# client = httpx.AsyncClient(timeout=60.0)

# _cache: Dict[str, dict] = {}  # key -> {"data": ..., "timestamp": float}

# def _cache_set(key: str, data: any) -> None:
#     _cache[key] = {"data": data, "timestamp": time.time()}

# def _cache_get(key: str, max_age_seconds: float) -> Optional[any]:
#     entry = _cache.get(key)
#     if entry and (time.time() - entry["timestamp"]) < max_age_seconds:
#         return entry["data"]
#     return None


# # ---- Local file storage helpers ----
# DATA_DIR = Path("data")
# DATA_DIR.mkdir(exist_ok=True)
# META_FILE = DATA_DIR / "_metadata.json"

# def _get_symbol_filename(symbol: str) -> Path:
#     return DATA_DIR / f"{symbol.lower()}.json"

# def load_symbol_file(symbol: str) -> List[HistoricalDataPoint]:
#     """Load existing history points from a symbol's JSON file."""
#     filepath = _get_symbol_filename(symbol)
#     if not filepath.exists():
#         return []
#     try:
#         with open(filepath, "r") as f:
#             raw = json.load(f)
#         return [HistoricalDataPoint(**p) for p in raw]
#     except Exception:
#         return []

# def save_symbol_file(symbol: str, points: List[HistoricalDataPoint]):
#     """Save (overwrite) the symbol's history file with the complete list."""
#     filepath = _get_symbol_filename(symbol)
#     with open(filepath, "w") as f:
#         json.dump([p.dict() for p in points], f, indent=2)

# def load_metadata() -> Dict[str, str]:
#     """Load the metadata dict {symbol: last_date_iso}."""
#     if not META_FILE.exists():
#         return {}
#     with open(META_FILE, "r") as f:
#         return json.load(f)

# def save_metadata(meta: Dict[str, str]):
#     with open(META_FILE, "w") as f:
#         json.dump(meta, f, indent=2)

# # ---------------------------------------------------------------------------
# # Helper: market open check (same logic as original)
# # ---------------------------------------------------------------------------
# def is_ngx_open() -> bool:
#     now = datetime.now(timezone.utc)
#     day = now.weekday()  # Monday=0 .. Sunday=6
#     minutes = now.hour * 60 + now.minute
#     # 08:30 UTC to 13:30 UTC (09:30–14:30 WAT) – adjust if needed
#     return 0 <= day <= 4 and 510 <= minutes < 810

# # ---------------------------------------------------------------------------
# # Scraper proxy builder
# # ---------------------------------------------------------------------------
# def build_proxy_url(target_url: str) -> str:
#     return f"http://api.scraperapi.com/?api_key={SCRAPER_API_KEY}&url={httpx.URL(target_url)}"


# # ---------------------------------------------------------------------------
# # Snapshot fetching (NGX live)
# # ---------------------------------------------------------------------------
# async def fetch_ngx_snapshot() -> NgxSnapshot:
#     # Check cache (5 minutes for live data)
#     cached = _cache_get("ngx_snapshot", max_age_seconds=300)
#     if cached:
#         return cached

#     print("[NGX] Starting full snapshot fetch...")
#     try:
#         all_tickers: List[NgxTicker] = []
#         page = 1
#         max_empty_pages = 0  # stop after 1 empty page (safety)

#         while True:
#             page_url = f"{AF_BASE}/ngx/" if page == 1 else f"{AF_BASE}/ngx/?page={page}"
#             proxy_url = build_proxy_url(page_url)
#             print(f"  Fetching page {page}...")
#             resp = await client.get(proxy_url)
#             html = resp.text
#             soup = BeautifulSoup(html, "lxml")

#             # Extract rows from this page
#             rows = soup.select("div.t table tbody tr")
#             page_tickers = []
#             for row in rows:
#                 cells = row.find_all("td")
#                 if len(cells) < 4:
#                     continue
#                 symbol = cells[0].get_text(strip=True)
#                 name = cells[1].get_text(strip=True) if len(cells) > 1 else symbol
#                 volume_text = cells[2].get_text(strip=True).replace(",", "")
#                 price_text = cells[3].get_text(strip=True).replace(",", "")
#                 change_text = cells[4].get_text(strip=True).replace(",", "") if len(cells) > 4 else "0"

#                 if not symbol:
#                     continue
#                 try:
#                     price = float(price_text)
#                 except ValueError:
#                     continue
#                 try:
#                     change = float(change_text.replace("+", ""))
#                 except ValueError:
#                     change = 0.0

#                 prev_price = price - change
#                 change_pct = (change / prev_price * 100) if prev_price else 0.0
#                 change_pct = round(change_pct, 2)

#                 page_tickers.append(NgxTicker(
#                     symbol=symbol,
#                     name=name,
#                     price=price,
#                     change=change,
#                     change_pct=change_pct,
#                     volume=int(volume_text) if volume_text.isdigit() else 0,
#                 ))

#             if not page_tickers:
#                 max_empty_pages += 1
#                 if max_empty_pages >= 2:  # two consecutive empty pages → stop
#                     break
#             else:
#                 max_empty_pages = 0
#                 all_tickers.extend(page_tickers)

#             # Stop if we've fetched a lot of pages and still no end (safety)
#             if page > 10:
#                 print("  Reached max page limit (10). Stopping.")
#                 break

#             page += 1
#             await asyncio.sleep(1.0)  # gentle delay between pages

#         if all_tickers:
#             snapshot = NgxSnapshot(
#                 status="OPEN" if is_ngx_open() else "CLOSED",
#                 last_updated=datetime.now(timezone.utc).isoformat(),
#                 tickers=all_tickers,
#             )
#             _cache_set("ngx_snapshot", snapshot)
#             return snapshot

#     except Exception as e:
#         print(f"[NGX] Snapshot fetch failed: {e}")
#         cached = _cache_get("ngx_snapshot", max_age_seconds=99999)
#         if cached:
#             return cached

#     raise HTTPException(status_code=502, detail="Failed to fetch NGX snapshot and no cache available")

# # ---------------------------------------------------------------------------
# # History fetching (for a symbol)
# # ---------------------------------------------------------------------------
# import asyncio

# def parse_highcharts_script(js_text: str) -> List[HistoricalDataPoint]:
#     points: List[HistoricalDataPoint] = []
#     # Match data array similar to original
#     pattern = r'\[d\("(\d{4}-\d{2}-\d{2})"\)\s*,\s*([\d.]+)\]'
#     matches = re.findall(pattern, js_text)
#     for date_str, close_str in matches:
#         try:
#             close = float(close_str)
#         except ValueError:
#             continue
#         points.append(HistoricalDataPoint(date=date_str, close=close))
#     # Sort ascending by date
#     points.sort(key=lambda x: x.date)
#     return points

# async def fetch_ngx_history(symbol: str) -> HistoricalData:
#     symbol_upper = symbol.upper()
#     cache_key = f"ngx_history_{symbol_upper}"
#     cached = _cache_get(cache_key, max_age_seconds=86400)  # 24h
#     if cached:
#         return cached

#     # 1. Try highcharts chart endpoint
#     slug = "" if symbol_upper == "ASI" else f"/{symbol.lower()}"
#     chart_url = f"{AF_BASE}/chart/ngx{slug}"
#     print(f"[NGX] Trying chart endpoint for {symbol_upper}: {chart_url}")
#     try:
#         resp = await client.get(build_proxy_url(chart_url))
#         js = resp.text
#         points = parse_highcharts_script(js)
#         if points:
#             result = HistoricalData(symbol=symbol_upper, data=points)
#             _cache_set(cache_key, result)
#             return result
#     except Exception as e:
#         print(f"Chart fetch failed for {symbol_upper}: {e}")

#     # 2. Fallback: HTML page with data-hist table
#     page_url = f"{AF_BASE}/ngx/{symbol.lower()}.html"
#     print(f"[NGX] Trying HTML fallback for {symbol_upper}: {page_url}")
#     try:
#         resp = await client.get(build_proxy_url(page_url))
#         soup = BeautifulSoup(resp.text, "lxml")
#         points: List[HistoricalDataPoint] = []
#         table = soup.select_one("table[data-hist]")
#         if table:
#             for row in table.select("tbody tr"):
#                 cells = row.find_all("td")
#                 if len(cells) < 3:
#                     continue
#                 date_text = cells[0].get_text(strip=True)
#                 volume_text = cells[1].get_text(strip=True).replace(",", "")
#                 close_text = cells[2].get_text(strip=True)
#                 try:
#                     close = float(close_text)
#                 except ValueError:
#                     continue
#                 if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_text):
#                     continue
#                 points.append(HistoricalDataPoint(
#                     date=date_text,
#                     close=close,
#                     volume=int(volume_text) if volume_text.isdigit() else None,
#                 ))
#         if points:
#             points.sort(key=lambda x: x.date)
#             result = HistoricalData(symbol=symbol_upper, data=points)
#             _cache_set(cache_key, result)
#             return result
#     except Exception as e:
#         print(f"HTML fallback failed for {symbol_upper}: {e}")

#     # Return stale cache if exists
#     stale = _cache_get(cache_key, max_age_seconds=99999)
#     if stale:
#         return stale

#     raise HTTPException(status_code=404, detail=f"No data found for NGX symbol: {symbol_upper}")

# # ---------------------------------------------------------------------------
# # Endpoints
# # ---------------------------------------------------------------------------
# @router.get("/markets/ngx/live", response_model=NgxSnapshot)
# async def get_live_snapshot():
#     return await fetch_ngx_snapshot()

# @router.get("/history/ngx/{symbol}", response_model=HistoricalData)
# async def get_history(
#     symbol: str,
#     range: Optional[str] = Query("All", description="Time range (currently unused)")
# ):
#     return await fetch_ngx_history(symbol)

# @router.get("/symbols/ngx", response_model=SymbolList)
# async def get_ngx_symbols():
#     """Return all available NGX symbols (unique) with count."""
#     snapshot = await fetch_ngx_snapshot()
#     seen = set()
#     unique = []
#     for t in snapshot.tickers:
#         if t.symbol not in seen:
#             seen.add(t.symbol)
#             unique.append(SymbolItem(symbol=t.symbol, name=t.name))
#     return SymbolList(length=len(unique), symbols=unique)

# @router.post("/markets/ngx/live/batch")
# async def get_batch_live(request: BatchSymbolsRequest):
#     """Return live data for a list of symbols."""
#     snapshot = await fetch_ngx_snapshot()
#     # Build a lookup dictionary
#     lookup = {t.symbol.upper(): t for t in snapshot.tickers}
#     result = []
#     missing = []
#     for sym in request.symbols:
#         ticker = lookup.get(sym.upper())
#         if ticker:
#             result.append(ticker)
#         else:
#             missing.append(sym)
#     if missing:
#         raise HTTPException(
#             status_code=404,
#             detail=f"Symbols not found: {', '.join(missing)}"
#         )
#     return {"symbols": result}

# def filter_last_year(points: List[HistoricalDataPoint]) -> List[HistoricalDataPoint]:
#     """Keep only points with date >= today - 365 days."""
#     cutoff = datetime.now().date() - timedelta(days=365)
#     return [p for p in points if datetime.strptime(p.date, "%Y-%m-%d").date() >= cutoff]

# @router.post("/history/ngx/batch/last-year")
# async def get_batch_history_last_year(request: BatchSymbolsRequest) -> BatchHistoryResponse:
#     """
#     For each requested symbol, return its live snapshot data + history for the last 1 year.
#     """
#     # 1. Get live data for all symbols (to attach name, price, etc.)
#     snapshot = await fetch_ngx_snapshot()
#     ticker_lookup = {t.symbol.upper(): t for t in snapshot.tickers}

#     results = []
#     for sym in request.symbols:
#         sym_upper = sym.upper()
#         ticker = ticker_lookup.get(sym_upper)
#         if not ticker:
#             raise HTTPException(
#                 status_code=404,
#                 detail=f"Symbol '{sym}' not found in live snapshot"
#             )

#         # 2. Fetch full history (cached or fresh)
#         history_data = await fetch_ngx_history(sym)  # This returns HistoricalData
#         # 3. Filter to last year
#         last_year_points = filter_last_year(history_data.data)

#         # 4. Build combined object
#         results.append(SymbolHistoryWithLive(
#             symbol=ticker.symbol,
#             name=ticker.name,
#             price=ticker.price,
#             change=ticker.change,
#             change_pct=ticker.change_pct,
#             volume=ticker.volume,
#             currency=ticker.currency,
#             history=last_year_points,
#         ))

#     return BatchHistoryResponse(data=results)
# # ---------------------------------------------------------------------------
# # Run with: uvicorn main:app --reload
# # ---------------------------------------------------------------------------

# @router.post("/history/ngx/sync-all")
# async def sync_all_historical_data():
#     """
#     Sync all symbols' historical data.
#     - Gets all symbols from the live snapshot.
#     - For each symbol, fetches complete history (from cache or scraper).
#     - Merges only new dates into the local data/{symbol}.json file.
#     - Updates _metadata.json with the latest date per symbol.
#     """
#     snapshot = await fetch_ngx_snapshot()
#     symbols = list({t.symbol for t in snapshot.tickers})  # unique symbols

#     metadata = load_metadata()
#     updated_count = 0
#     new_points_total = 0

#     for symbol in symbols:
#         # Fetch full history for the symbol (respects internal cache)
#         try:
#             hist = await fetch_ngx_history(symbol)
#         except HTTPException:
#             continue  # skip symbols that can't be fetched

#         if not hist.data:
#             continue

#         # Get existing points from file
#         existing = load_symbol_file(symbol)
#         existing_dates = {p.date for p in existing}

#         # New points = those not already in the file
#         new_points = [p for p in hist.data if p.date not in existing_dates]
#         if not new_points:
#             continue

#         # Merge and sort
#         merged = sorted(existing + new_points, key=lambda x: x.date)
#         save_symbol_file(symbol, merged)

#         # Update metadata with the latest date for this symbol
#         latest_date = merged[-1].date
#         metadata[symbol.upper()] = latest_date
#         updated_count += 1
#         new_points_total += len(new_points)

#     save_metadata(metadata)

#     return {
#         "message": "Sync completed",
#         "total_symbols_checked": len(symbols),
#         "symbols_updated": updated_count,
#         "new_data_points_added": new_points_total,
#     }



