from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class PredictionResponse(BaseModel):
    label: str
    confidence: float


"""
pydantic data validation library

Controls API output format

Self-documentation for FastAPI

Prevents inconsistent responses"""


# Validates user registration data
class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str


# Validates login credentials
class Userlogin(BaseModel):
    email: EmailStr
    password: str


# Defines what user data looks like when sent to user
class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
        # allos sqlalchmey model conversions to pydantic models


# what you return after successful login
class Token(BaseModel):
    access_token: str
    token_type: str


# What's inside the JWT token after decoding
class TokenData(BaseModel):
    email: Optional[str] = None


# request body must look like when the frontend sends a message.[chat]
class ChatMessageRequest(BaseModel):
    message: str = Field(
        ..., min_length=1, max_length=2000, description="User's message to the AI"
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="Optional conversation ID to continue existing conversation",
    )

    # make docs clearn in swagger ui
    class Config:
        json_schema_extra = {
            "example": {
                "message": "What are the different types of brain tumors?",
                "conversation_id": "conv_abc123",
            }
        }


# structure of the response
class ChatMessageResponse(BaseModel):
    conversation_id: str
    message_sent: bool
    status: str


# respnose message for conversation history
class ConversationHistory(BaseModel):
    conversation_id: str
    messages: list
    total_messages: int
