import os
from dotenv import load_dotenv
from openai import OpenAI
from chat_application.system_prompt import system_prompt

load_dotenv()

client = OpenAI(
    base_url="https://ollama.com/v1",
    api_key=os.getenv("LLM_API_KEY", "ollama"),
)


class ChatSession:
    def __init__(self):
        self.messages = [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]

    def add_user_message(self, prompt: str):
        self.messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

    def stream(self):

        response = client.chat.completions.create(
            model="gemma4:31b-cloud",
            messages=self.messages,
            stream=True,
            max_tokens=150,
        ) # type: ignore

        assistant_message = ""

        for chunk in response:

            token = chunk.choices[0].delta.content or ""

            assistant_message += token

            yield token

        self.messages.append(
            {
                "role": "assistant",
                "content": assistant_message,
            }
        )