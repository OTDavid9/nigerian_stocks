# api/v1/routes/chat.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from agents.stock_agent import StockAgent
from jose import JWTError, jwt
from core.security import JWT_SECRET, JWT_ALGORITHM
from core.database import users_collection
import json
import uuid
import logging

router = APIRouter(prefix="/chat", tags=["Chat"])
logger = logging.getLogger(__name__)

# In‑memory agent store (for simplicity; in production use a cache)
_agent_store = {}

@router.websocket("")
async def websocket_chat(
    websocket: WebSocket,
    token: str = Query(...)
):
    try:
        payload = jwt.decode(token, key=JWT_SECRET, algorithms=[JWT_ALGORITHM])
        email = payload.get("email")
        if not email:
            await websocket.close(code=1008, reason="Invalid token payload")
            return
        user = users_collection.find_one({"email": email})
        if not user:
            await websocket.close(code=1008, reason="User not found")
            return
        logger.info(f"✅ User authenticated: {email}")
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        await websocket.close(code=1008, reason="Invalid token")
        return

    await websocket.accept()
    session_id = str(uuid.uuid4())
    logger.info(f"🔌 WebSocket connected: session_id={session_id}, user={email}")

    # Create an agent instance for this session
    agent = StockAgent(session_id=session_id, token=token)
    _agent_store[session_id] = agent

    try:
        while True:
            message = await websocket.receive_text()
            # Stream the agent's response
            async for chunk in agent.stream_response(message):
                await websocket.send_text(
                    json.dumps({"content": chunk, "is_complete": False})
                )
            await websocket.send_text(
                json.dumps({"content": "", "is_complete": True})
            )
    except WebSocketDisconnect:
        logger.info(f"🔌 Disconnected: session_id={session_id}")
        if session_id in _agent_store:
            del _agent_store[session_id]
# # api/v1/routes/chat.py

# from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
# from chat_application.client import handle_chat_stream
# from jose import JWTError, jwt
# from core.security import JWT_SECRET, JWT_ALGORITHM
# from core.database import users_collection
# import json
# import uuid
# import logging

# router = APIRouter(prefix="/chat", tags=["Chat"])
# logger = logging.getLogger(__name__)

# @router.websocket("")
# async def websocket_chat(
#     websocket: WebSocket,
#     token: str = Query(...)
# ):
#     try:
#         payload = jwt.decode(token, key=JWT_SECRET, algorithms=[JWT_ALGORITHM])
#         email = payload.get("email")
#         if not email:
#             await websocket.close(code=1008, reason="Invalid token payload")
#             return
#         user = users_collection.find_one({"email": email})
#         if not user:
#             await websocket.close(code=1008, reason="User not found")
#             return
#         logger.info(f"✅ User authenticated: {email}")
#     except JWTError as e:
#         logger.error(f"JWT decode error: {e}")
#         await websocket.close(code=1008, reason="Invalid token")
#         return

#     await websocket.accept()
#     session_id = str(uuid.uuid4())
#     logger.info(f"🔌 WebSocket connected: session_id={session_id}, user={email}")

#     try:
#         while True:
#             message = await websocket.receive_text()
#             async for chunk in handle_chat_stream(
#                 session_id=session_id,
#                 user_input=message,
#                 token=token
#             ):
#                 await websocket.send_text(
#                     json.dumps({"content": chunk, "is_complete": False})
#                 )
#             await websocket.send_text(
#                 json.dumps({"content": "", "is_complete": True})
#             )
#     except WebSocketDisconnect:
#         logger.info(f"🔌 Disconnected: session_id={session_id}")
#         # Clean up token from memory
#         from chat_application.tools import _session_tokens
#         if session_id in _session_tokens:
#             del _session_tokens[session_id]