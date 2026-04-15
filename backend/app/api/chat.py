import json
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import logging

# Import our modules
from app.database.database import get_db
from app.auth.dependencies import get_current_active_user
from app.database.models import User, MessageRole
from app.middleware.rate_limit import limiter
from app.crud import conversation as crud_conversation
from app.api.Pydantic_Schema import (
    ChatMessageRequest,
    ConversationResponse,
    ConversationDetailResponse,
    ConversationListResponse,
    MessageResponse,
)

# Import the AI agent
from app.ai.agent import ChatAgent


router = APIRouter()
logger = logging.getLogger(__name__)


# ── Send Message (updated with DB persistence) ──────────────────────


@router.post("/message")
@limiter.limit("20/minute")
async def send_message(
    request: Request,
    chat_request: ChatMessageRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Send a message to the AI agent with full conversation persistence.

    - If conversation_id is provided, loads existing conversation.
    - If not, creates a new conversation using the first message as title.
    - Saves user message BEFORE calling LLM.
    - Saves assistant response AFTER streaming completes.
    - Streams SSE with JSON-encoded events to handle newlines in text.
    - Sends suggested follow-up questions after the main response.
    """
    try:
        # ── Resolve conversation ─────────────────────────────────────
        if chat_request.conversation_id:
            # Load existing conversation (also verifies ownership)
            conversation = crud_conversation.get_conversation(
                db,
                conversation_id=chat_request.conversation_id,
                user_id=current_user.id,
            )
            if conversation is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation not found",
                )
        else:
            # Create new conversation
            conversation = crud_conversation.create_conversation(
                db,
                user_id=current_user.id,
                first_message=chat_request.message,
            )

        conversation_id = conversation.id

        logger.info(
            f"User {current_user.id} sending message in conversation {conversation_id}"
        )

        # ── Save user message BEFORE calling LLM ────────────────────
        crud_conversation.save_message(
            db,
            conversation_id=conversation_id,
            role=MessageRole.user,
            content=chat_request.message,
        )

        # ── Create AI agent (loads history from DB) ──────────────────
        agent = ChatAgent(
            user_id=current_user.id,
            conversation_id=conversation_id,
            db=db,
        )

        async def response_generator():
            full_response = ""
            try:
                # Send conversation_id as first SSE event
                yield f"data: {json.dumps({'conversation_id': conversation_id})}\n\n"

                async for chunk in agent.send_message(chat_request.message):
                    full_response += chunk
                    # JSON-encode the chunk so newlines in the text become \n literals
                    # This prevents SSE from splitting on \n\n inside the response text
                    yield f"data: {json.dumps({'text': chunk})}\n\n"

                # Save assistant response AFTER streaming completes
                if full_response:
                    crud_conversation.save_message(
                        db,
                        conversation_id=conversation_id,
                        role=MessageRole.assistant,
                        content=full_response,
                    )

                # ── Generate suggested follow-ups (non-blocking) ─────
                # Only generate if we got a real response (not an error code)
                if full_response and not full_response.startswith("__ERROR_"):
                    try:
                        suggestions = agent.generate_follow_ups(full_response)
                        if suggestions:
                            yield f"data: {json.dumps({'suggestions': suggestions})}\n\n"
                    except Exception as e:
                        # Follow-ups are non-critical — never break the response
                        logger.warning(f"Follow-up generation failed: {e}")

                yield "data: [DONE]\n\n"

            except Exception as e:
                logger.exception("Error in response generator")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            response_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in send_message endpoint")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process message",
        )


# ── List Conversations ───────────────────────────────────────────────


@router.get("/conversations", response_model=ConversationListResponse)
@limiter.limit("30/minute")
async def list_conversations(
    request: Request,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List all conversations for the authenticated user, newest first."""
    conversations = crud_conversation.list_user_conversations(
        db, user_id=current_user.id, skip=skip, limit=limit
    )

    conversation_list = [
        ConversationResponse(
            id=conv.id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=len(conv.messages),
        )
        for conv in conversations
    ]

    return ConversationListResponse(
        conversations=conversation_list,
        total=len(conversation_list),
    )


# ── Get Single Conversation with Messages ────────────────────────────


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
)
@limiter.limit("30/minute")
async def get_conversation(
    request: Request,
    conversation_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get a single conversation with all its messages."""
    conversation = crud_conversation.get_conversation(
        db, conversation_id=conversation_id, user_id=current_user.id
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    messages = crud_conversation.get_conversation_messages(
        db, conversation_id=conversation_id, user_id=current_user.id
    )

    return ConversationDetailResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[MessageResponse.model_validate(msg) for msg in messages],
    )


# ── Delete Conversation ──────────────────────────────────────────────


@router.delete("/conversations/{conversation_id}")
@limiter.limit("10/minute")
async def delete_conversation(
    request: Request,
    conversation_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Delete a conversation and all its messages."""
    deleted = crud_conversation.delete_conversation(
        db, conversation_id=conversation_id, user_id=current_user.id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    return {"status": "deleted", "conversation_id": conversation_id}


# ── Test Endpoint (unchanged) ────────────────────────────────────────


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
