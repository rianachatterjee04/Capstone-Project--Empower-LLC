"""
Global error handling middleware.
"""
import traceback
from fastapi import Request, status
from fastapi.responses import JSONResponse
from app.core.error_logger import error_logger

async def global_error_handler(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        error_logger.log_error(
            error=e,
            endpoint=str(request.url),
            extra={"method": request.method}
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error", "type": type(e).__name__}
        )
