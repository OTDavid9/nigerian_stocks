from uuid import uuid4

from services.chat_client import ChatSession


class SessionManager:

    def __init__(self):

        self.sessions: dict[str, ChatSession] = {}

    def create(self):

        session_id = str(uuid4())

        self.sessions[session_id] = ChatSession()

        return session_id

    def get(self, session_id: str) -> ChatSession:

        return self.sessions[session_id]

    def exists(self, session_id: str) -> bool:

        return session_id in self.sessions

    def get_or_create(self, session_id: str | None):

        if session_id and self.exists(session_id):

            return session_id, self.get(session_id)

        session_id = self.create()

        return session_id, self.get(session_id)

    def delete(self, session_id):

        self.sessions.pop(session_id, None)


manager = SessionManager()