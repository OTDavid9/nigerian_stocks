from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from chat_application.client import handle_chat_stream, handle_chat_message
from models.chat import ChatRequest, ChatResponse
from jose import JWTError, jwt
from core.security import JWT_SECRET, JWT_ALGORITHM
from core.database import users_collection
import json
import uuid

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)

# POST endpoint (unchanged)
@router.post("")
async def chat(request: ChatRequest):
    response = await handle_chat_message(
        session_id=request.session_id, # type: ignore
        user_input=request.prompt,
    )
    return ChatResponse(
        response=response,
        session_id=request.session_id, # type: ignore
    )

# # WebSocket endpoint – now at "/api/v1/chat"
# @router.websocket("")
# async def websocket_chat(
#     websocket: WebSocket,
#     token: str = Query(...)
# ):
#     print(f"🔑 Received token (first 20 chars): {token[:20]}...")

#     try:
#         payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
#         print(f"✅ Decoded payload: {payload}")

#         email = payload.get("email")
#         if not email:
#             print("❌ No 'email' claim in token")
#             await websocket.close(code=1008, reason="Invalid token payload")
#             return

#         user = users_collection.find_one({"email": email})
#         if not user:
#             print(f"❌ User not found for email: {email}")
#             await websocket.close(code=1008, reason="User not found")
#             return

#         print(f"✅ User authenticated: {email}")

#     except JWTError as e:
#         print(f"❌ JWT decode error: {e}")
#         await websocket.close(code=1008, reason="Invalid token")
#         return

#     await websocket.accept()
#     session_id = str(user["_id"])
#     print(f"🔌 WebSocket connected: session_id={session_id}, user={email}")

#     try:
#         while True:
#             message = await websocket.receive_text()
#             async for chunk in handle_chat_stream(
#                 session_id=session_id,
#                 user_input=message
#             ):
#                 await websocket.send_text(chunk)
#     except WebSocketDisconnect:
#         print(f"🔌 Disconnected: session_id={session_id}")

@router.websocket("")
async def websocket_chat(
    websocket: WebSocket,
    token: str = Query(...)
):
    # ... (authentication logic stays the same) ...
    try:
        payload = jwt.decode(token, key=JWT_SECRET, algorithms=[JWT_ALGORITHM])
        print(f"✅ Decoded payload: {payload}")

        email = payload.get("email")
        if not email:
            print("❌ No 'email' claim in token")
            await websocket.close(code=1008, reason="Invalid token payload")
            return

        user = users_collection.find_one({"email": email})
        if not user:
            print(f"❌ User not found for email: {email}")
            await websocket.close(code=1008, reason="User not found")
            return

        print(f"✅ User authenticated: {email}")

    except JWTError as e:
        print(f"❌ JWT decode error: {e}")
        await websocket.close(code=1008, reason="Invalid token")
        return

    await websocket.accept()
    session_id = str(uuid.uuid4())  # Generate a unique session ID for this WebSocket connection
    print(f"🔌 WebSocket connected: session_id={session_id}, user={email}")

    try:
        while True:
            message = await websocket.receive_text()
            # Send each chunk as a JSON object with is_complete=False
            async for chunk in handle_chat_stream(
                session_id=session_id,
                user_input=message
            ):
                # Wrap chunk in JSON
                await websocket.send_text(
                    json.dumps({"content": chunk, "is_complete": False})
                )
            # After the stream ends, send a final marker
            await websocket.send_text(
                json.dumps({"content": "", "is_complete": True})
            )
    except WebSocketDisconnect:
        print(f"🔌 Disconnected: session_id={session_id}")