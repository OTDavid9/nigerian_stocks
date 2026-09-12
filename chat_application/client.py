# chat_application/client.py

import json
import logging
from typing import Dict, List
from .ollama_tools import ollama_tools
from .tool_registry import TOOL_REGISTRY
from .tools import set_session_token
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("LLM_API_KEY")
MODEL_NAME = os.getenv("LLM_MODEL_NAME")

client = OpenAI(
    base_url="https://ollama.com/v1",
    api_key=OPENAI_API_KEY,
)

conversation_histories: Dict[str, List[Dict]] = {}
logger = logging.getLogger(__name__)

def initialize_conversation(session_id: str):
    from .system_prompt import system_prompt
    conversation_histories[session_id] = [
        {"role": "system", "content": system_prompt},
    ]

def process_tool_calls(tool_calls, session_id: str):
    tool_responses = []
    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)
        args['session_id'] = session_id

        logger.info(f"🛠️  Tool called: {tool_name} with args: {args}")

        func = TOOL_REGISTRY.get(tool_name)
        if func:
            try:
                result = func(**args)
            except Exception as e:
                result = f"Error: {str(e)}"
        else:
            result = f"Unknown tool: {tool_name}"

        tool_responses.append({
            "role": "tool",
            "name": tool_name,
            "content": str(result),
            "tool_call_id": tool_call.id
        })

    return tool_responses

async def handle_chat_stream(session_id: str, user_input: str, token: str = None):
    if token:
        set_session_token(session_id, token)

    if session_id not in conversation_histories:
        initialize_conversation(session_id)

    conversation_history = conversation_histories[session_id]
    conversation_history.append({"role": "user", "content": user_input})

    while True:
        truncated = [conversation_history[0]] + conversation_history[-10:]

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=truncated,
            tools=ollama_tools,
            tool_choice="auto",
            stream=False,
            temperature=0.9,
        )

        message = response.choices[0].message
        assistant_msg = {"role": "assistant", "content": message.content or ""}
        if message.tool_calls:
            assistant_msg["tool_calls"] = message.tool_calls
        conversation_history.append(assistant_msg)

        if message.tool_calls:
            tool_responses = process_tool_calls(message.tool_calls, session_id)
            conversation_history.extend(tool_responses)
            continue

        # Stream final response
        stream = client.chat.completions.create(
            model=MODEL_NAME,
            messages=truncated,
            stream=True,
            temperature=0.9,
        )
        full = ""
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                full += delta
                yield delta

        conversation_history.append({"role": "assistant", "content": full})
        break