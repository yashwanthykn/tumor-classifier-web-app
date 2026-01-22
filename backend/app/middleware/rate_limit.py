from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,  # Rate limit by IP address
    default_limits=["100/hour"]    # Default: 100 requests per hour
)

def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """
    Custom handler for rate limit exceeded errors.
    Returns user-friendly error message.
    """
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "error": "Rate limit exceeded",
            "message": "Too many requests. Please try again later.",
            "retry_after": exc.retry_after if hasattr(exc, 'retry_after') else 3600
        }
    )