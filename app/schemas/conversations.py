from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.enums import MessageSource


def non_blank(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("Value cannot be blank")
    return stripped


NonBlankString = Annotated[str, AfterValidator(non_blank)]


class CustomerOption(BaseModel):
    id: int
    company_name: str


class TicketSummary(BaseModel):
    id: int
    title: str
    updated_at: datetime


class TicketResponse(BaseModel):
    id: int
    customer_id: int
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    status: str


class CreateTicketRequest(BaseModel):
    customer_id: int = Field(gt=0)
    title: NonBlankString = Field(max_length=255)
    description: NonBlankString = Field(max_length=10_000)


class CreateTicketResponse(BaseModel):
    id: int


class MessageResponse(BaseModel):
    id: int
    customer_id: int
    ticket_id: int
    message: str
    created_at: datetime
    updated_at: datetime
    source: MessageSource


class CreateMessageRequest(BaseModel):
    message: NonBlankString = Field(max_length=10_000)


class ConversationResponse(BaseModel):
    user_message: MessageResponse
    agent_message: MessageResponse
