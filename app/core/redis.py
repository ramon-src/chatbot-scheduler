"""
Redis configuration and session management
"""

import asyncio
import json
import pickle
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, Optional, Union

import redis

# import aioredis  # Temporarily disabled due to compatibility issues
from redis.exceptions import RedisError

from app.core.config import settings

# =============================================================================
# REDIS CONNECTION POOLS
# =============================================================================
redis_pool = None
redis_session_pool = None
redis_cache_pool = None

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
# REDIS CONNECTION MANAGEMENT
# =============================================================================
def get_redis_connection() -> redis.Redis:
    """Get Redis connection"""
    global redis_pool
    if redis_pool is None:
        redis_pool = redis.ConnectionPool(**get_redis_config())
    return redis.Redis(connection_pool=redis_pool)

def get_redis_session_connection() -> redis.Redis:
    """Get Redis session connection"""
    global redis_session_pool
    if redis_session_pool is None:
        redis_session_pool = redis.ConnectionPool(**get_redis_session_config())
    return redis.Redis(connection_pool=redis_session_pool)

def get_redis_cache_connection() -> redis.Redis:
    """Get Redis cache connection"""
    global redis_cache_pool
    if redis_cache_pool is None:
        redis_cache_pool = redis.ConnectionPool(**get_redis_cache_config())
    return redis.Redis(connection_pool=redis_cache_pool)

# =============================================================================
# ASYNC REDIS CONNECTION
# =============================================================================
async def get_async_redis() -> aioredis.Redis:
    """Get async Redis connection"""
    return await aioredis.from_url(settings.REDIS_URL)

async def get_async_redis_session() -> aioredis.Redis:
    """Get async Redis session connection"""
    return await aioredis.from_url(settings.redis_session_url)

async def get_async_redis_cache() -> aioredis.Redis:
    """Get async Redis cache connection"""
    return await aioredis.from_url(settings.redis_cache_url)

# =============================================================================
# REDIS UTILITIES
# =============================================================================
class RedisManager:
    """Redis manager for common operations"""
    
    def __init__(self, connection: redis.Redis):
        self.redis = connection
    
    def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Set a key-value pair"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            elif not isinstance(value, (str, int, float)):
                value = pickle.dumps(value)
            
            return self.redis.set(key, value, ex=expire)
        except RedisError as e:
            print(f"Redis set error: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a value by key"""
        try:
            value = self.redis.get(key)
            if value is None:
                return default
            
            # Try to parse as JSON first
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                # If not JSON, try to unpickle
                try:
                    return pickle.loads(value)
                except (pickle.PickleError, TypeError):
                    # Return as string
                    return value
        except RedisError as e:
            print(f"Redis get error: {e}")
            return default
    
    def delete(self, key: str) -> bool:
        """Delete a key"""
        try:
            return bool(self.redis.delete(key))
        except RedisError as e:
            print(f"Redis delete error: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists"""
        try:
            return bool(self.redis.exists(key))
        except RedisError as e:
            print(f"Redis exists error: {e}")
            return False
    
    def expire(self, key: str, seconds: int) -> bool:
        """Set expiration for a key"""
        try:
            return bool(self.redis.expire(key, seconds))
        except RedisError as e:
            print(f"Redis expire error: {e}")
            return False
    
    def ttl(self, key: str) -> int:
        """Get time to live for a key"""
        try:
            return self.redis.ttl(key)
        except RedisError as e:
            print(f"Redis ttl error: {e}")
            return -1
    
    def keys(self, pattern: str = "*") -> list:
        """Get keys matching pattern"""
        try:
            return self.redis.keys(pattern)
        except RedisError as e:
            print(f"Redis keys error: {e}")
            return []
    
    def flushdb(self) -> bool:
        """Flush current database"""
        try:
            return self.redis.flushdb()
        except RedisError as e:
            print(f"Redis flushdb error: {e}")
            return False

# =============================================================================
# SESSION MANAGEMENT
# =============================================================================
class SessionManager(RedisManager):
    """Session manager for user sessions"""
    
    def __init__(self):
        super().__init__(get_redis_session_connection())
    
    def create_session(self, session_id: str, user_id: str, data: dict = None) -> bool:
        """Create a new session"""
        session_data = {
            "user_id": user_id,
            "created_at": str(asyncio.get_event_loop().time()),
            "data": data or {}
        }
        return self.set(f"session:{session_id}", session_data, expire=86400)  # 24 hours
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session data"""
        return self.get(f"session:{session_id}")
    
    def update_session(self, session_id: str, data: dict) -> bool:
        """Update session data"""
        session = self.get_session(session_id)
        if session:
            session["data"].update(data)
            return self.set(f"session:{session_id}", session, expire=86400)
        return False
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        return self.delete(f"session:{session_id}")
    
    def extend_session(self, session_id: str, seconds: int = 86400) -> bool:
        """Extend session expiration"""
        return self.expire(f"session:{session_id}", seconds)

# =============================================================================
# CACHE MANAGEMENT
# =============================================================================
class CacheManager(RedisManager):
    """Cache manager for application caching"""
    
    def __init__(self):
        super().__init__(get_redis_cache_connection())
    
    def cache_key(self, prefix: str, *args) -> str:
        """Generate cache key"""
        return f"{prefix}:{':'.join(str(arg) for arg in args)}"
    
    def cache_get(self, prefix: str, *args) -> Any:
        """Get cached value"""
        key = self.cache_key(prefix, *args)
        return self.get(key)
    
    def cache_set(self, prefix: str, value: Any, expire: int = 3600, *args) -> bool:
        """Set cached value"""
        key = self.cache_key(prefix, *args)
        return self.set(key, value, expire=expire)
    
    def cache_delete(self, prefix: str, *args) -> bool:
        """Delete cached value"""
        key = self.cache_key(prefix, *args)
        return self.delete(key)
    
    def cache_clear_pattern(self, pattern: str) -> int:
        """Clear cache by pattern"""
        keys = self.keys(pattern)
        if keys:
            return self.redis.delete(*keys)
        return 0

# =============================================================================
# GLOBAL INSTANCES
# =============================================================================
session_manager = SessionManager()
cache_manager = CacheManager()

# =============================================================================
# HEALTH CHECK
# =============================================================================
def check_redis_health() -> bool:
    """Check if Redis is healthy"""
    try:
        redis_conn = get_redis_connection()
        redis_conn.ping()
        return True
    except RedisError:
        return False

async def check_async_redis_health() -> bool:
    """Check if async Redis is healthy"""
    try:
        redis_conn = await get_async_redis()
        await redis_conn.ping()
        await redis_conn.close()
        return True
    except RedisError:
        return False

