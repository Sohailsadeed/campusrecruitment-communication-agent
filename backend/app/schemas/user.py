"""User-related Pydantic schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    username: str = Field(min_length=3, max_length=100)
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: str = Field(min_length=1, max_length=255, description="Email or username")
    password: str


class UserOut(UserBase):
    id: int
    resume_name: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
