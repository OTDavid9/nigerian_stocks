# chat_application/tool_registry.py

TOOL_REGISTRY = {}

def register_tool(name: str):
    def decorator(func):
        TOOL_REGISTRY[name] = func
        return func
    return decorator