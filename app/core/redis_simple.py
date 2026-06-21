"""
Redis configuration and utilities (simplified version)
"""

import json
import pickle
from datetime import timedelta
from typing import Any, Optional, Union

import redis
from redis.exceptions import RedisError

from app.core.config import settings

# =============================================================================
# REDIS CONFIGURATION
# =============================================================================

def get_redis_config() -> dict:
    """Get Redis configuration"""
    return {
        "host": settings.REDIS_URL.split("://")[1].split(":")[0],
        "port": int(settings.REDIS_URL.split(":")[-1].split("/")[0]),
        "db": int(settings.REDIS_URL.split("/")[-1]),
        "decode_responses": True,
        "socket_connect_timeout": 5,
        "socket_timeout": 5,
        "retry_on_timeout": True,
        "health_check_interval": 30,
    }

def get_redis_session_config() -> dict:
    """Get Redis session configuration"""
    config = get_redis_config()
    config["db"] = settings.REDIS_SESSION_DB
    return config

def get_redis_cache_config() -> dict:
    """Get Redis cache configuration"""
    config = get_redis_config()
    config["db"] = settings.REDIS_CACHE_DB
    return config

# =============================================================================
# REDIS CONNECTION POOLS
# =============================================================================

def get_redis() -> redis.Redis:
    """Get Redis client"""
    return redis.Redis(**get_redis_config())

def get_redis_session() -> redis.Redis:
    """Get Redis session client"""
    return redis.Redis(**get_redis_session_config())

def get_redis_cache() -> redis.Redis:
    """Get Redis cache client"""
    return redis.Redis(**get_redis_cache_config())

# =============================================================================
# REDIS HEALTH CHECK
# =============================================================================

def check_redis_health() -> bool:
    """Check Redis health"""
    try:
        redis_client = get_redis()
        redis_client.ping()
        return True
    except Exception:
        return False

# =============================================================================
# SESSION MANAGER
# =============================================================================

class SessionManager:
    """Session manager using Redis"""
    
    def __init__(self):
        self.redis = get_redis_session()
    
    def create_session(self, session_id: str, user_id: str, data: dict) -> bool:
        """Create a new session"""
        try:
            session_data = {
                "user_id": user_id,
                "data": data,
                "created_at": str(timedelta().total_seconds())
            }
            self.redis.setex(
                f"session:{session_id}",
                settings.SESSION_EXPIRE_SECONDS,
                json.dumps(session_data)
            )
            return True
        except Exception:
            return False
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session data"""
        try:
            data = self.redis.get(f"session:{session_id}")
            if data:
                return json.loads(data)
            return None
        except Exception:
            return None
    
    def update_session(self, session_id: str, data: dict) -> bool:
        """Update session data"""
        try:
            session = self.get_session(session_id)
            if session:
                session["data"].update(data)
                self.redis.setex(
                    f"session:{session_id}",
                    settings.SESSION_EXPIRE_SECONDS,
                    json.dumps(session)
                )
                return True
            return False
        except Exception:
            return False
    
    def delete_session(self, session_id: str) -> bool:
        """Delete session"""
        try:
            self.redis.delete(f"session:{session_id}")
            return True
        except Exception:
            return False

# =============================================================================
# CACHE MANAGER
# =============================================================================

class CacheManager:
    """Cache manager using Redis"""
    
    def __init__(self):
        self.redis = get_redis_cache()
    
    def cache_set(
        self, 
        namespace: str, 
        key: str, 
        value: Any, 
        expire: int = 3600
    ) -> bool:
        """Set cache value"""
        try:
            cache_key = f"{namespace}:{key}"
            serialized_value = json.dumps(value, default=str)
            self.redis.setex(cache_key, expire, serialized_value)
            return True
        except Exception:
            return False
    
    def cache_get(self, namespace: str, key: str) -> Optional[Any]:
        """Get cache value"""
        try:
            cache_key = f"{namespace}:{key}"
            data = self.redis.get(cache_key)
            if data:
                return json.loads(data)
            return None
        except Exception:
            return None
    
    def cache_delete(self, namespace: str, key: str) -> bool:
        """Delete cache value"""
        try:
            cache_key = f"{namespace}:{key}"
            self.redis.delete(cache_key)
            return True
        except Exception:
            return False
    
    def cache_clear_namespace(self, namespace: str) -> bool:
        """Clear all cache in namespace"""
        try:
            pattern = f"{namespace}:*"
            keys = self.redis.keys(pattern)
            if keys:
                self.redis.delete(*keys)
            return True
        except Exception:
            return False

# =============================================================================
# GLOBAL INSTANCES
# =============================================================================

# Create global instances
session_manager = SessionManager()
cache_manager = CacheManager()
