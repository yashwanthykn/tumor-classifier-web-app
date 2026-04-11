from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.predict import router as predict_router

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router

from app.database.database import Base, engine
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.rate_limit import limiter, rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
import time

# Import all models so Base.metadata knows about them
from app.database.models import User, Prediction, Conversation, Message  # noqa: F401

# Create all database tables (handles existing tables — idempotent)
# New tables (conversations, messages) are managed by Alembic migrations,
# but create_all() is safe to keep: it skips tables that already exist.
Base.metadata.create_all(bind=engine)

# App initialization
app = FastAPI(
    title="Tumor Detection API",
    description="Detects brain tumor from MRI images",
    version="2.0.0",
)

# Add rate limiter to app state
app.state.limiter = limiter

# Register rate limit exceeded handler
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Add security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# Health check endpoint
@app.get("/health")
def health_check():
    return {"status": "ok"}


# Include routers
app.include_router(predict_router, prefix="/api", tags=["Predictions"])
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(chat_router, prefix="/api/chat", tags=["chatbot"])

print("FastAPI app loaded correctly")
