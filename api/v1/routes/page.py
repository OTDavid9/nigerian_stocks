from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Form
from core.deps import get_current_user
from datetime import timedelta
from typing import Optional

router = APIRouter()

templates = Jinja2Templates(directory="templates")


@router.get("/")
async def home(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={}
    )



# ---------- Logout ----------
@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("access_token")
    return response

# ---------- Protected Dashboard ----------
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user=Depends(get_current_user)):
    
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request, "user": user}
    )