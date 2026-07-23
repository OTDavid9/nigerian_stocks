from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from chat_application.client import (
    ChatRequest,
    ChatResponse,
    handle_chat_message,
    handle_chat_stream,
)
from fastapi import Query

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)

@router.post(
    "",
    response_model=ChatResponse,
)
async def chat(request: ChatRequest):

    response = await handle_chat_message(
        session_id=request.session_id,
        user_input=request.message,
    )

    return ChatResponse(
        response=response,
        session_id=request.session_id,
    )


# @router.websocket("/ws")
# async def websocket_chat(websocket: WebSocket):

#     await websocket.accept()

#     try:

#         while True:

#             data = await websocket.receive_json()

#             session_id = data.get("session_id", "default")
#             message = data.get("message", "")

#             async for token in handle_chat_stream(
#                 session_id=session_id,
#                 user_input=message,
#             ):

#                 await websocket.send_json(
#                     {
#                         "type": "token",
#                         "content": token,
#                     }
#                 )

#             await websocket.send_json(
#                 {
#                     "type": "done"
#                 }
#             )

#     except WebSocketDisconnect:
#         print("Client disconnected")

@router.websocket("")
async def websocket_chat(
    websocket: WebSocket,
    session_id: str = Query(...)
):
    await websocket.accept()

    print(f"Connected: {session_id}")

    try:
        while True:
            message = await websocket.receive_text()

            async for chunk in handle_chat_stream(
                session_id=session_id,
                user_input=message,
            ):
                await websocket.send_text(chunk)

    except WebSocketDisconnect:
        print(f"Disconnected: {session_id}")