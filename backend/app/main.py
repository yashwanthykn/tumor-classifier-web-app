from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.api.predict import router as predict_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router

from app.database.database import Base, engine
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.rate_limit import limiter, rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.database.models import User, Prediction, Conversation, Message  # noqa: F401

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    ON STARTUP:
    - Creates DB tables (idempotent)
    - Initializes the RAG service: loads sentence-transformers model,
      connects to ChromaDB, and ingests medical documents if the
      collection is empty.

    RAG initialization is best-effort: if it fails (e.g., missing model
    weights, out of memory), the app starts anyway and RAG is silently
    disabled. All other features continue to work normally.
    """
    # ── DB tables ────────────────────────────────────────────────────
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified")

    # ── RAG service ──────────────────────────────────────────────────
    try:
        from app.ai.rag import rag_service

        logger.info("Initializing RAG service...")
        rag_service.initialize()  # loads model + connects ChromaDB + ingests docs
        logger.info(f"RAG service ready: {rag_service.is_ready}")
    except Exception as e:
        logger.error(f"RAG service failed to initialize: {e}", exc_info=True)
        logger.warning("App will start without RAG support")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("Application shutting down")


app = FastAPI(
    title="Tumor Detection API",
    description="Detects brain tumor from MRI images",
    version="2.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(predict_router, prefix="/api", tags=["Predictions"])
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(chat_router, prefix="/api/chat", tags=["chatbot"])

print("FastAPI app loaded correctly")
