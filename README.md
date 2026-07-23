# 📈 NGX Market API

A FastAPI-based service for scraping and serving **Nigerian Exchange (NGX)** market data, including:

* 📊 Live market snapshot
* 📉 Historical price data
* 🔁 Batch endpoints for efficient querying
* 💾 Local persistence for historical data
* ⚡ In-memory caching for performance

---

## 🚀 Features

* Real-time NGX market data scraping
* Historical data extraction (via Highcharts + HTML fallback)
* Batch APIs for multiple symbols
* Automatic pagination handling
* Local JSON storage for historical sync
* Smart caching (live + historical)
* CORS-enabled for frontend integration

---

## 🧱 Tech Stack

* **FastAPI** – API framework
* **httpx** – Async HTTP client
* **BeautifulSoup (lxml)** – HTML parsing
* **Pydantic** – Data validation
* **uv** – Dependency management
* **ScraperAPI** – Proxy scraping

---

## 📦 Installation

### 1. Clone the repository

```bash
git clone https://github.com/OTDavid9/nigerian_stocks.git
cd nigerian_stocks
```

### 2. Install dependencies (using `uv`)

```bash
uv sync
```

```bash
source .venv/Scripts/activate
```

> If you don’t have uv:

```bash
pip install uv
```

---

## 🔐 Environment Variables

Create a `.env` file in the root directory:

```env
SCRAPER_API_KEY=your_scraperapi_key_here
```

---

## ▶️ Running the App

```bash
uvicorn main:app --reload
```

App will be available at:

```
http://localhost:8000
http://localhost:8000/docs 

```

---

## 📚 API Endpoints

### 🔹 Live Market Data

```http
GET /api/v1/markets/ngx/live
```

Returns full NGX market snapshot.

---

### 🔹 Get Symbol History

```http
GET /api/v1/history/ngx/{symbol}
```

Example:

```
/api/v1/history/ngx/MTNN
```

---

### 🔹 Get All Symbols

```http
GET /api/v1/symbols/ngx
```

Returns:

* Unique symbols
* Total count

---

### 🔹 Batch Live Data

```http
POST /api/v1/markets/ngx/live/batch
```

**Body:**

```json
{
  "symbols": ["MTNN", "GTCO"]
}
```

---

### 🔹 Batch History (Last 1 Year)

```http
POST /api/v1/history/ngx/batch/last-year
```

Returns:

* Live price
* Historical data (last 365 days)

---

### 🔹 Sync All Historical Data (Local Storage)

```http
POST /api/v1/history/ngx/sync-all
```

* Fetches all symbols
* Stores data in `/data` directory
* Updates `_metadata.json`

---

## 💾 Data Storage

Local files are stored in:

```
/data/
  ├── mtnn.json
  ├── gtco.json
  ├── _metadata.json
```

* Each symbol has its own JSON file
* Metadata tracks latest synced dates

---

## ⚡ Caching Strategy

| Data Type     | Cache Duration |
| ------------- | -------------- |
| Live Snapshot | 5 minutes      |
| Historical    | 24 hours       |

Fallback to stale cache if scraping fails.

---

## 🧠 How It Works

1. **Live Data**

   * Scrapes paginated NGX pages
   * Parses HTML tables
   * Computes % change

2. **Historical Data**

   * Primary: Highcharts JS parsing
   * Fallback: HTML table scraping

3. **Sync Engine**

   * Merges new data into local files
   * Avoids duplicates using date keys

---

## 🛠️ Development Notes

* Pagination capped at 10 pages (safety)
* Graceful fallback on scraping failures
* Async-first architecture
* Designed for frontend + analytics consumption

---

## ⚠️ Limitations

* Dependent on external site structure
* ScraperAPI required for reliability
* No WebSocket streaming (yet)

---

## 🔮 Future Improvements

* WebSocket live updates
* Redis caching
* Docker support
* Rate limiting
* Historical OHLC support (if available)

---

## 👨‍💻 Author

Built by Tunji DAvid Obidokun
ML/AI Engineer | Backend Systems

---

## 📄 License
Apache License
Version 2.0, January 2004
