from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.v1.routes.stocks import router as stock_router
from api.v1.routes.chat import router as chat_router
from api.v1.routes.page import router as page_router
import httpx

app = FastAPI(title="NGX Market API", version="1.0.0")

# CORS (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# HTTP client (reusable, with timeout)
# ---------------------------------------------------------------------------
client = httpx.AsyncClient(timeout=60.0)

@app.on_event("shutdown")
async def shutdown():
    await client.aclose()

app.include_router(page_router,  tags=["Pages"])
app.include_router(stock_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1",  tags=["Chat"],
)

