"""Natural language chat interface endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import require_api_key
from app.chat import get_or_create_session

router = APIRouter(
    prefix="/api",
    tags=["chat"],
    dependencies=[Depends(require_api_key)],
)


class ChatMessage(BaseModel):
    message: str
    session_id: str = "default"


class ChatConfirm(BaseModel):
    session_id: str = "default"
    confirmed: bool = True


@router.post("/chat")
async def chat(msg: ChatMessage):
    """Send a natural language message to interact with Odoo."""
    session = get_or_create_session(msg.session_id)
    result = session.send_message(msg.message)
    return result


@router.post("/chat/confirm")
async def chat_confirm(req: ChatConfirm):
    """Confirm or reject pending write actions from the chat."""
    session = get_or_create_session(req.session_id)
    result = session.confirm_actions(req.confirmed)
    return result
