from test import OllamaAgent

agent = OllamaAgent(
    api_key="ee94c3ffc203426697910e9f79fb9d43.l0YaMNReKlS952lbEMEXCPTP",
    model="gemma4:31b-cloud",
    system_prompt="""
You are an intelligent AI assistant.

You can use tools to retrieve information and perform operations.

Always:
- Understand the user's intent.
- Use tools when appropriate.
- Never fabricate tool results.
- Remember previous messages in the conversation.
- Give clear and concise answers.
"""
)

response = agent.chat(
    "I am an Aquarius. What is my horoscope?"
)

print(response)

response = agent.chat(
    "What did I just tell you my sign was?"
)

print(response)