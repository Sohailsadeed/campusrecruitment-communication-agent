"""Session-related Pydantic schemas."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SessionBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    round_type: str = "jam"
    overall_score: Optional[float] = None
    round_metadata: Dict[str, Any] = Field(default_factory=dict)
    report: Optional[Dict[str, Any]] = None


class SessionCreate(SessionBase):
    duration_seconds: float = 0.0


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    overall_score: Optional[float] = None
    report: Optional[Dict[str, Any]] = None


class SessionOut(SessionBase):
    id: int
    user_id: Optional[int] = None
    duration_seconds: float
    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TranscriptionOut(BaseModel):
    id: int
    session_id: int
    text: str
    language: str
    confidence: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionAnalysisOut(BaseModel):
    id: int
    session_id: int
    speaking_pace: float
    filler_words_count: int
    filler_words_list: Dict[str, Any]
    clarity_score: float
    eye_contact_percentage: float
    posture_quality: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionDetailOut(SessionOut):
    transcription: Optional[TranscriptionOut] = None
    analysis: Optional[SessionAnalysisOut] = None
    feedback: List["AIFeedbackOut"] = []  # noqa: F821

    model_config = ConfigDict(from_attributes=True)


from .feedback import AIFeedbackOut  # noqa: E402

SessionDetailOut.model_rebuild()
