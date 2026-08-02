from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from core.database import users_collection
from models.auth import UserCreate, UserLogin
from core.security import hash_password, verify_password, create_access_token
from core.deps import get_current_user


router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/signup")
def signup(user: UserCreate):
    # Check if user already exists
    existing = users_collection.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    # Hash password and store user
    hashed = hash_password(user.password)
    document = {
        "fullname": user.fullname,
        "email": user.email,
        "password": hashed,
    }
    result = users_collection.insert_one(document)

    # Create token with email and user_id
    token = create_access_token(
        {
            "user_id": str(result.inserted_id),
            "email": user.email,
        }
    )

    # Return JSON with token and set cookie
    response = JSONResponse(content={"access_token": token, "token_type": "bearer"})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 7,  # 7 days
        samesite="lax",
        secure=False,   # set True if using HTTPS
        path="/"
    )
    return response

@router.post("/signin")
def signin(user: UserLogin):
    db_user = users_collection.find_one({"email": user.email})
    if not db_user or not verify_password(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(
        {
            "user_id": str(db_user["_id"]),
            "email": db_user["email"],
        }
    )

    response = JSONResponse(content={"access_token": token, "token_type": "bearer"})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 7,
        samesite="lax",
        secure=False,
        path="/"
    )
    return response

@router.get("/me")
def get_me(current_user=Depends(get_current_user)):
    return current_user

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("access_token")
    return response