"""
Logging configuration for SimplificaPsi
"""

import logging
import logging.config
import sys
from pathlib import Path
from typing import Dict, Any
import structlog
from structlog.stdlib import LoggerFactory

from app.core.config import settings

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================
def setup_logging() -> None:
    """Setup application logging"""
    
    # Create logs directory
    log_file = Path(settings.LOG_FILE)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if settings.LOG_FORMAT == "json" else structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    logging_config = get_logging_config()
    logging.config.dictConfig(logging_config)

def get_logging_config() -> Dict[str, Any]:
    """Get logging configuration dictionary"""
    
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "json": {
                "format": '{"timestamp": "%(asctime)s", "logger": "%(name)s", "level": "%(levelname)s", "message": "%(message)s"}',
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            },
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(funcName)s - %(lineno)d - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "default" if settings.LOG_FORMAT != "json" else "json",
                "stream": sys.stdout,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": log_level,
                "formatter": "json" if settings.LOG_FORMAT == "json" else "detailed",
                "filename": settings.LOG_FILE,
                "maxBytes": parse_size(settings.LOG_MAX_SIZE),
                "backupCount": settings.LOG_BACKUP_COUNT,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "": {  # Root logger
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "app": {  # Application logger
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "uvicorn": {  # Uvicorn logger
                "level": logging.INFO,
                "handlers": ["console"],
                "propagate": False,
            },
            "uvicorn.access": {  # Uvicorn access logger
                "level": logging.INFO,
                "handlers": ["console"],
                "propagate": False,
            },
            "sqlalchemy": {  # SQLAlchemy logger
                "level": logging.WARNING,
                "handlers": ["file"],
                "propagate": False,
            },
            "alembic": {  # Alembic logger
                "level": logging.INFO,
                "handlers": ["console"],
                "propagate": False,
            },
            "redis": {  # Redis logger
                "level": logging.WARNING,
                "handlers": ["file"],
                "propagate": False,
            },
            "httpx": {  # HTTP client logger
                "level": logging.WARNING,
                "handlers": ["file"],
                "propagate": False,
            },
        },
    }

def parse_size(size_str: str) -> int:
    """Parse size string to bytes"""
    size_str = size_str.upper()
    if size_str.endswith("KB"):
        return int(size_str[:-2]) * 1024
    elif size_str.endswith("MB"):
        return int(size_str[:-2]) * 1024 * 1024
    elif size_str.endswith("GB"):
        return int(size_str[:-2]) * 1024 * 1024 * 1024
    else:
        return int(size_str)

# =============================================================================
# LOGGER FACTORY
# =============================================================================
def get_logger(name: str = "app") -> structlog.BoundLogger:
    """Get structured logger"""
    return structlog.get_logger(name)

# =============================================================================
# LOGGING UTILITIES
# =============================================================================
class LoggerMixin:
    """Mixin to add logging capabilities to classes"""
    
    @property
    def logger(self) -> structlog.BoundLogger:
        """Get logger for this class"""
        return get_logger(self.__class__.__name__)

def log_function_call(func):
    """Decorator to log function calls"""
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        logger.info(
            "Function called",
            function=func.__name__,
            args=args,
            kwargs=kwargs
        )
        try:
            result = func(*args, **kwargs)
            logger.info(
                "Function completed",
                function=func.__name__,
                result=result
            )
            return result
        except Exception as e:
            logger.error(
                "Function failed",
                function=func.__name__,
                error=str(e),
                exc_info=True
            )
            raise
    return wrapper

def log_async_function_call(func):
    """Decorator to log async function calls"""
    async def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        logger.info(
            "Async function called",
            function=func.__name__,
            args=args,
            kwargs=kwargs
        )
        try:
            result = await func(*args, **kwargs)
            logger.info(
                "Async function completed",
                function=func.__name__,
                result=result
            )
            return result
        except Exception as e:
            logger.error(
                "Async function failed",
                function=func.__name__,
                error=str(e),
                exc_info=True
            )
            raise
    return wrapper

# =============================================================================
# CONTEXT MANAGERS
# =============================================================================
class LogContext:
    """Context manager for logging"""
    
    def __init__(self, logger: structlog.BoundLogger, message: str, **kwargs):
        self.logger = logger
        self.message = message
        self.kwargs = kwargs
    
    def __enter__(self):
        self.logger.info(f"Starting: {self.message}", **self.kwargs)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.logger.info(f"Completed: {self.message}", **self.kwargs)
        else:
            self.logger.error(
                f"Failed: {self.message}",
                error=str(exc_val),
                exc_info=True,
                **self.kwargs
            )

# =============================================================================
# INITIALIZE LOGGING
# =============================================================================
setup_logging()

