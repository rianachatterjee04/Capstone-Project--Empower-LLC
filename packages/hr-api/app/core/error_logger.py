"""
Centralized error logging system.
"""
import logging
import traceback
from datetime import datetime
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/empower_errors.log')
    ]
)

logger = logging.getLogger("empower")

class ErrorLogger:
    @staticmethod
    def log_error(
        error: Exception,
        endpoint: Optional[str] = None,
        user_id: Optional[str] = None,
        org_id: Optional[str] = None,
        extra: Optional[dict] = None
    ):
        error_type = type(error).__name__
        message = str(error)
        stack = traceback.format_exc()

        logger.error(
            f"[{error_type}] {message} | "
            f"endpoint={endpoint} | "
            f"user={user_id} | "
            f"org={org_id} | "
            f"extra={extra}"
        )
        logger.debug(f"Stack trace:\n{stack}")

    @staticmethod
    def log_warning(message: str, context: Optional[dict] = None):
        logger.warning(f"{message} | context={context}")

    @staticmethod
    def log_info(message: str, context: Optional[dict] = None):
        logger.info(f"{message} | context={context}")

    @staticmethod
    def log_db_error(error: Exception, query: Optional[str] = None):
        logger.error(
            f"[DatabaseError] {str(error)} | "
            f"query={query[:100] if query else None}"
        )

    @staticmethod
    def log_auth_error(message: str, user_id: Optional[str] = None):
        logger.warning(f"[AuthError] {message} | user={user_id}")

    @staticmethod
    def log_validation_error(field: str, message: str, value: any = None):
        logger.warning(f"[ValidationError] field={field} | {message} | value={value}")

error_logger = ErrorLogger()
