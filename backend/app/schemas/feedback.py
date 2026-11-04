"""AIFeedback Pydantic schemas."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class AIFeedbackBase(BaseModel):
    feedback_type: str = "overall"
    content: str
    score: float = 0.0
    suggestions: List[str] = []


class AIFeedbackCreate(AIFeedbackBase):
    session_id: int


class AIFeedbackOut(AIFeedbackBase):
    id: int
    session_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
