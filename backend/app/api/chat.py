from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
import logging
import uuid

# Import our modules
from app.database.database import get_db
from app.auth.dependencies import get_current_active_user
from app.database.models import User
from app.middleware.rate_limit import limiter
from app.api.Pydantic_Schema import (
    ChatMessageRequest,
    ChatMessageResponse,
    ConversationHistory,
)

# Import the AI agent
from app.ai.agent import ChatAgent


router = APIRouter()
logger = logging.getLogger(__name__)


# sends message to Ai agents and get streaming response
@router.post("/message")
@limiter.limit("20/minute")  # 20 msg per minute
async def send_message(
    request: Request,
    chat_request: ChatMessageRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        # Get or generate conversation ID
        conversation_id = (
            chat_request.conversation_id or f"conv_{uuid.uuid4().hex[:12]}"
        )

        logger.info(
            f"User {current_user.id} sending message in conversation {conversation_id}"
        )

        # Create AI agent for this user
        agent = ChatAgent(
            user_id=current_user.id, conversation_id=conversation_id, db=db
        )

        async def response_generator():
            try:
                async for chunk in agent.send_message(chat_request.message):
                    # Send chunk to client
                    yield f"data: {chunk}\n\n"
                # Send end marker
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.exception("Error in response generator")
                yield f"data: Error: {str(e)}\n\n"

        return StreamingResponse(
            response_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    except Exception as e:
        logger.exception("Error in send_message endpoint")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process message",
        )


@router.get("/test")
async def test_chat(current_user: User = Depends(get_current_active_user)):
    """
    Simple test endpoint to verify chat API is working.

    Returns basic info about authenticated user.
    """
    return {
        "status": "Chat API is working!",
        "user_id": current_user.id,
        "user_email": current_user.email,
        "message": "Chat endpoints are ready to use",
    }
