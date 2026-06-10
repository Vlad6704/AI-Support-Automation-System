from pydantic import BaseModel


class ExecuteAgentRequest(BaseModel):
    ticket: str
    thread_id: str = "ticket-1"
    user_id: str | None = None
