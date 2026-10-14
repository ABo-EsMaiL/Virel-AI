"""Current Chat Completions request contract."""

from typing import Any, List, Optional
from pydantic import BaseModel
from .config import DEFAULT_MODEL


class ChatMessage(BaseModel):
    role: str
    content: Any = None


class ChatRequest(BaseModel):
    model: str = DEFAULT_MODEL
    messages: List[ChatMessage]
    stream: bool = True
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
