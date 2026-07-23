from openai import OpenAI
import json
from chat_application.tools import ollama_tools
from chat_application.functions import *
from chat_application.system_prompt import system_prompt
from chat_application.tool_registry import TOOL_REGISTRY
import logging
from dotenv import load_dotenv
import os
from typing import Dict, List, Optional
from pydantic import BaseModel

load_dotenv()

# Constants
MODEL_NAME = os.getenv("LLM_MODEL_NAME")



# Setup OpenAI API Client
from openai import OpenAI
from dotenv import load_dotenv
import os

# Load environment variables from .env file         

load_dotenv()


OPENAI_API_KEY = os.getenv("LLM_API_KEY")
MODEL_NAME = os.getenv("LLM_MODEL_NAME")



client = OpenAI(
    base_url="https://ollama.com/v1",
    api_key=OPENAI_API_KEY,
)


# Store conversation histories per session
conversation_histories: Dict[str, List[Dict]] = {}

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"

class ChatResponse(BaseModel):
    response: str
    session_id: str

def initialize_conversation(session_id: str):
    """Initialize a new conversation history"""
    conversation_histories[session_id] = [
        {"role": "system", "content": system_prompt},
    ]

def process_tool_calls(tool_calls):
    """Process tool calls and return results using dynamic dispatch."""
    tool_responses = []
    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)

        logging.info(f"🛠️  Tool called: {tool_name} with args: {args}")

        # Get the function from the dispatcher
        func = TOOL_REGISTRY.get(tool_name)

        if func:
            try:
                result = func(**args)
            except Exception as e:
                result = f"Error while executing {tool_name}: {str(e)}"
        else:
            result = f"Error: Unknown tool {tool_name}"

        tool_responses.append({
            "role": "tool",
            "name": tool_name,
            "content": str(result),
            "tool_call_id": tool_call.id
        })

    return tool_responses

async def handle_chat_message(session_id: str, user_input: str):
    """Handle incoming chat message and generate response"""
    if session_id not in conversation_histories:
        initialize_conversation(session_id)
    
    conversation_history = conversation_histories[session_id]
    user_input = user_input + " " + "/no_think"
    conversation_history.append({"role": "user", "content": user_input})

    while True:
        # Prepare messages: system prompt + last 10 items
        truncated_conversation = [conversation_history[0]] + conversation_history[-10:]

        # Get model response
        response = client.chat.completions.create(
            messages=truncated_conversation,
            model=MODEL_NAME,
            tools=ollama_tools,
            tool_choice="auto",
            temperature=0.9
        )

        message = response.choices[0].message
        response_content = message.content.strip() if message.content else ""
        clean_response = response_content.replace("<think>\n\n</think>", "").strip()

        # Add assistant response to full history
        assistant_message = {
            "role": "assistant",
            "content": clean_response,
        }
        if hasattr(message, 'tool_calls') and message.tool_calls:
            assistant_message["tool_calls"] = message.tool_calls
        
        conversation_history.append(assistant_message)

        # If there are tool calls, process them and continue
        if hasattr(message, 'tool_calls') and message.tool_calls:
            tool_responses = process_tool_calls(message.tool_calls)
            conversation_history.extend(tool_responses)
        else:
            # No more tool calls, return response
            return clean_response


async def handle_chat_stream(session_id: str, user_input: str):
    """
    Stream chat responses while supporting tool calling.
    Yields text chunks to the caller.
    """

    if session_id not in conversation_histories:
        initialize_conversation(session_id)

    conversation_history = conversation_histories[session_id]

    user_input = user_input + " /no_think"

    conversation_history.append(
        {
            "role": "user",
            "content": user_input,
        }
    )

    while True:

        # Keep system prompt + last 10 conversation items
        truncated_conversation = (
            [conversation_history[0]]
            + conversation_history[-10:]
        )

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=truncated_conversation,
            tools=ollama_tools,
            tool_choice="auto",
            stream=False,  # Tool detection requires non-streaming
            temperature=0.9,
        )

        message = response.choices[0].message

        assistant_message = {
            "role": "assistant",
            "content": message.content or "",
        }

        if message.tool_calls:
            assistant_message["tool_calls"] = message.tool_calls

        conversation_history.append(assistant_message)

        # ---------------------------------------------------
        # TOOL CALLS
        # ---------------------------------------------------

        if message.tool_calls:

            logging.info(
                f"Model requested {len(message.tool_calls)} tool(s)"
            )

            tool_responses = process_tool_calls(message.tool_calls)

            conversation_history.extend(tool_responses)

            # Loop again so the model can consume tool outputs
            continue

        # ---------------------------------------------------
        # FINAL RESPONSE
        # ---------------------------------------------------

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=truncated_conversation,
            stream=True,
            temperature=0.9,
        )

        full_response = ""

        for chunk in response:

            delta = chunk.choices[0].delta.content or ""

            if delta:
                full_response += delta
                yield delta

        conversation_history.append(
            {
                "role": "assistant",
                "content": full_response,
            }
        )

        break