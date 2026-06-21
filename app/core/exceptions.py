"""
Custom exceptions for SimplificaPsi
"""

from typing import Any, Dict, Optional
from fastapi import HTTPException, status

# =============================================================================
# BASE EXCEPTIONS
# =============================================================================
class SimplificaPsiException(Exception):
    """Base exception for SimplificaPsi"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

class ValidationError(SimplificaPsiException):
    """Validation error"""
    pass

class NotFoundError(SimplificaPsiException):
    """Resource not found error"""
    pass

class ConflictError(SimplificaPsiException):
    """Resource conflict error"""
    pass

class AuthenticationError(SimplificaPsiException):
    """Authentication error"""
    pass

class AuthorizationError(SimplificaPsiException):
    """Authorization error"""
    pass

class ExternalServiceError(SimplificaPsiException):
    """External service error"""
    pass

class DatabaseError(SimplificaPsiException):
    """Database error"""
    pass

class CacheError(SimplificaPsiException):
    """Cache error"""
    pass

# =============================================================================
# BUSINESS LOGIC EXCEPTIONS
# =============================================================================
class ClientNotFoundError(NotFoundError):
    """Client not found"""
    
    def __init__(self, client_id: str):
        super().__init__(
            f"Client with ID {client_id} not found",
            {"client_id": client_id}
        )

class EventNotFoundError(NotFoundError):
    """Event not found"""
    
    def __init__(self, event_id: str):
        super().__init__(
            f"Event with ID {event_id} not found",
            {"event_id": event_id}
        )

class CalendarNotFoundError(NotFoundError):
    """Calendar not found"""
    
    def __init__(self, calendar_id: str):
        super().__init__(
            f"Calendar with ID {calendar_id} not found",
            {"calendar_id": calendar_id}
        )

class UserNotFoundError(NotFoundError):
    """User not found"""
    
    def __init__(self, user_id: str):
        super().__init__(
            f"User with ID {user_id} not found",
            {"user_id": user_id}
        )

class SessionNotFoundError(NotFoundError):
    """Chat session not found"""
    
    def __init__(self, session_id: str):
        super().__init__(
            f"Chat session with ID {session_id} not found",
            {"session_id": session_id}
        )

# =============================================================================
# CONFLICT EXCEPTIONS
# =============================================================================
class ClientConflictError(ConflictError):
    """Client conflict error"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(f"Client conflict: {message}", details)

class EventConflictError(ConflictError):
    """Event conflict error"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(f"Event conflict: {message}", details)

class TimeSlotConflictError(EventConflictError):
    """Time slot conflict error"""
    
    def __init__(self, start_time: str, end_time: str, conflicting_event_id: str):
        super().__init__(
            f"Time slot {start_time} - {end_time} is already occupied",
            {
                "start_time": start_time,
                "end_time": end_time,
                "conflicting_event_id": conflicting_event_id
            }
        )

class DuplicateClientError(ClientConflictError):
    """Duplicate client error"""
    
    def __init__(self, phone: str = None, email: str = None):
        if phone and email:
            message = f"Client with phone {phone} and email {email} already exists"
        elif phone:
            message = f"Client with phone {phone} already exists"
        elif email:
            message = f"Client with email {email} already exists"
        else:
            message = "Client already exists"
        
        super().__init__(message, {"phone": phone, "email": email})

# =============================================================================
# VALIDATION EXCEPTIONS
# =============================================================================
class InvalidPhoneError(ValidationError):
    """Invalid phone number error"""
    
    def __init__(self, phone: str):
        super().__init__(
            f"Invalid phone number format: {phone}",
            {"phone": phone}
        )

class InvalidEmailError(ValidationError):
    """Invalid email error"""
    
    def __init__(self, email: str):
        super().__init__(
            f"Invalid email format: {email}",
            {"email": email}
        )

class InvalidDateRangeError(ValidationError):
    """Invalid date range error"""
    
    def __init__(self, start_time: str, end_time: str):
        super().__init__(
            f"Invalid date range: start_time {start_time} must be before end_time {end_time}",
            {"start_time": start_time, "end_time": end_time}
        )

class InvalidRecurrenceRuleError(ValidationError):
    """Invalid recurrence rule error"""
    
    def __init__(self, rule: str):
        super().__init__(
            f"Invalid recurrence rule: {rule}",
            {"rule": rule}
        )

# =============================================================================
# EXTERNAL SERVICE EXCEPTIONS
# =============================================================================
class GoogleCalendarError(ExternalServiceError):
    """Google Calendar API error"""
    
    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(
            f"Google Calendar error: {message}",
            {"error_code": error_code}
        )

class WhatsAppAPIError(ExternalServiceError):
    """WhatsApp API error"""
    
    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(
            f"WhatsApp API error: {message}",
            {"error_code": error_code}
        )

class OpenAIError(ExternalServiceError):
    """OpenAI API error"""
    
    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(
            f"OpenAI API error: {message}",
            {"error_code": error_code}
        )

# =============================================================================
# HTTP EXCEPTION CONVERTERS
# =============================================================================
def to_http_exception(exc: SimplificaPsiException) -> HTTPException:
    """Convert SimplificaPsi exception to HTTP exception"""
    
    if isinstance(exc, (ClientNotFoundError, EventNotFoundError, CalendarNotFoundError, UserNotFoundError, SessionNotFoundError)):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
            headers={"X-Error-Details": str(exc.details)}
        )
    
    elif isinstance(exc, (ClientConflictError, EventConflictError, TimeSlotConflictError, DuplicateClientError)):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
            headers={"X-Error-Details": str(exc.details)}
        )
    
    elif isinstance(exc, (InvalidPhoneError, InvalidEmailError, InvalidDateRangeError, InvalidRecurrenceRuleError)):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.message,
            headers={"X-Error-Details": str(exc.details)}
        )
    
    elif isinstance(exc, AuthenticationError):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message,
            headers={"X-Error-Details": str(exc.details)}
        )
    
    elif isinstance(exc, AuthorizationError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=exc.message,
            headers={"X-Error-Details": str(exc.details)}
        )
    
    elif isinstance(exc, (GoogleCalendarError, WhatsAppAPIError, OpenAIError)):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=exc.message,
            headers={"X-Error-Details": str(exc.details)}
        )
    
    elif isinstance(exc, (DatabaseError, CacheError)):
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=exc.message,
            headers={"X-Error-Details": str(exc.details)}
        )
    
    else:
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=exc.message,
            headers={"X-Error-Details": str(exc.details)}
        )

# =============================================================================
# EXCEPTION HANDLERS
# =============================================================================
def handle_simplificapsi_exception(exc: SimplificaPsiException) -> HTTPException:
    """Handle SimplificaPsi exceptions"""
    return to_http_exception(exc)

def handle_validation_exception(exc: ValidationError) -> HTTPException:
    """Handle validation exceptions"""
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=exc.message,
        headers={"X-Error-Details": str(exc.details)}
    )

def handle_not_found_exception(exc: NotFoundError) -> HTTPException:
    """Handle not found exceptions"""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=exc.message,
        headers={"X-Error-Details": str(exc.details)}
    )

def handle_conflict_exception(exc: ConflictError) -> HTTPException:
    """Handle conflict exceptions"""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=exc.message,
        headers={"X-Error-Details": str(exc.details)}
    )

