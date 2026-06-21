"""
Core configuration and utilities for SimplificaPsi
"""

from .config import settings
from .database import (
    Base,
    check_connection,
    create_tables,
    drop_tables,
    get_db,
    get_db_context,
)
from .exceptions import (
    AuthenticationError,
    AuthorizationError,
    CacheError,
    CalendarNotFoundError,
    ClientConflictError,
    ClientNotFoundError,
    ConflictError,
    DatabaseError,
    DuplicateClientError,
    EventConflictError,
    EventNotFoundError,
    ExternalServiceError,
    GoogleCalendarError,
    InvalidDateRangeError,
    InvalidEmailError,
    InvalidPhoneError,
    InvalidRecurrenceRuleError,
    NotFoundError,
    OpenAIError,
    SessionNotFoundError,
    SimplificaPsiException,
    TimeSlotConflictError,
    UserNotFoundError,
    ValidationError,
    WhatsAppAPIError,
    handle_conflict_exception,
    handle_not_found_exception,
    handle_simplificapsi_exception,
    handle_validation_exception,
    to_http_exception,
)
from .logging import (
    LogContext,
    LoggerMixin,
    get_logger,
    log_async_function_call,
    log_function_call,
    setup_logging,
)
from .redis_simple import (
    CacheManager,
    SessionManager,
    cache_manager,
    check_redis_health,
    get_redis,
    get_redis_cache,
    get_redis_session,
    session_manager,
)

__all__ = [
    # Configuration
    "settings",
    
    # Database
    "Base",
    "get_db",
    "get_db_context", 
    "create_tables",
    "drop_tables",
    "check_connection",
    
    # Redis
    "get_redis",
    "get_redis_session",
    "get_redis_cache",
    "SessionManager",
    "CacheManager",
    "session_manager",
    "cache_manager",
    "check_redis_health",
    
    # Logging
    "setup_logging",
    "get_logger",
    "LoggerMixin",
    "log_function_call",
    "log_async_function_call",
    "LogContext",
    
    # Exceptions
    "SimplificaPsiException",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    "AuthenticationError",
    "AuthorizationError",
    "ExternalServiceError",
    "DatabaseError",
    "CacheError",
    "ClientNotFoundError",
    "EventNotFoundError",
    "CalendarNotFoundError",
    "UserNotFoundError",
    "SessionNotFoundError",
    "ClientConflictError",
    "EventConflictError",
    "TimeSlotConflictError",
    "DuplicateClientError",
    "InvalidPhoneError",
    "InvalidEmailError",
    "InvalidDateRangeError",
    "InvalidRecurrenceRuleError",
    "GoogleCalendarError",
    "WhatsAppAPIError",
    "OpenAIError",
    "to_http_exception",
    "handle_simplificapsi_exception",
    "handle_validation_exception",
    "handle_not_found_exception",
    "handle_conflict_exception",
]