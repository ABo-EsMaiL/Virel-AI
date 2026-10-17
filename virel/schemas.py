"""Current Chat Completions request contract."""

from typing import Any, List, Optional, Literal
from pydantic import BaseModel
from .config import DEFAULT_MODEL


class ChatMessage(BaseModel):
    role: str
    content: Any = None
    phase: Optional[Literal["commentary", "final_answer"]] = None


class ChatRequest(BaseModel):
    model: str = DEFAULT_MODEL
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
