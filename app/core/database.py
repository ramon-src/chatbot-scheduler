"""
Database configuration and session management
"""

from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from typing import Generator
import os
from contextlib import contextmanager

from app.core.config import settings

# =============================================================================
# DATABASE ENGINE
# =============================================================================
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=settings.DEBUG,
    # For testing, use in-memory SQLite
    poolclass=StaticPool if settings.TESTING else None,
    connect_args={"check_same_thread": False} if settings.TESTING else {}
)

# =============================================================================
# SESSION FACTORY
# =============================================================================
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# =============================================================================
# BASE CLASS
# =============================================================================
Base = declarative_base()

# =============================================================================
# METADATA
# =============================================================================
metadata = MetaData(schema="simplificapsi")

# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================
def get_db() -> Generator[Session, None, None]:
    """
    Dependency to get database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =============================================================================
# CONTEXT MANAGER
# =============================================================================
@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for database session
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# =============================================================================
# DATABASE UTILITIES
# =============================================================================
def create_tables():
    """Create all tables"""
    Base.metadata.create_all(bind=engine)

def drop_tables():
    """Drop all tables"""
    Base.metadata.drop_all(bind=engine)

def check_connection() -> bool:
    """Check if database connection is working"""
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False

# =============================================================================
# TESTING UTILITIES
# =============================================================================
def get_test_db() -> Generator[Session, None, None]:
    """
    Get test database session
    """
    if not settings.TESTING:
        raise ValueError("This function should only be used in testing")
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def reset_test_db():
    """Reset test database"""
    if not settings.TESTING:
        raise ValueError("This function should only be used in testing")
    
    drop_tables()
    create_tables()

