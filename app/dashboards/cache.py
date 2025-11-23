"""
Caching system for dashboards
"""
from functools import wraps
from typing import Any, Callable, Optional
from datetime import datetime, timedelta
import hashlib
import json
import logging

logger = logging.getLogger(__name__)


class DashboardCache:
    """Simple in-memory cache for dashboard data"""
    
    _cache: dict = {}
    _ttl: dict = {}
    
    @classmethod
    def get(cls, key: str) -> Optional[Any]:
        """Get cached value if not expired"""
        if key in cls._cache:
            if datetime.now() < cls._ttl.get(key, datetime.min):
                logger.debug(f"Cache hit: {key}")
                return cls._cache[key]
            else:
                # Expired, remove it
                del cls._cache[key]
                del cls._ttl[key]
                logger.debug(f"Cache expired: {key}")
        return None
    
    @classmethod
    def set(cls, key: str, value: Any, ttl: int = 300):
        """Set cached value with TTL in seconds"""
        cls._cache[key] = value
        cls._ttl[key] = datetime.now() + timedelta(seconds=ttl)
        logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
    
    @classmethod
    def clear(cls, pattern: Optional[str] = None):
        """Clear cache entries matching pattern"""
        if pattern:
            keys_to_delete = [k for k in cls._cache.keys() if pattern in k]
            for k in keys_to_delete:
                del cls._cache[k]
                if k in cls._ttl:
                    del cls._ttl[k]
            logger.info(f"Cleared {len(keys_to_delete)} cache entries matching '{pattern}'")
        else:
            count = len(cls._cache)
            cls._cache.clear()
            cls._ttl.clear()
            logger.info(f"Cleared all {count} cache entries")
    
    @classmethod
    def generate_key(cls, prefix: str, **kwargs) -> str:
        """Generate cache key from prefix and kwargs"""
        key_str = f"{prefix}:{json.dumps(kwargs, sort_keys=True)}"
        key_hash = hashlib.md5(key_str.encode()).hexdigest()
        return f"{prefix}:{key_hash}"


def cached(ttl: int = 300, key_prefix: Optional[str] = None):
    """
    Decorator for caching function results
    
    Args:
        ttl: Time to live in seconds (default: 300 = 5 minutes)
        key_prefix: Optional prefix for cache key (default: function name)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            prefix = key_prefix or f"{func.__module__}.{func.__name__}"
            cache_key = DashboardCache.generate_key(prefix, args=args, kwargs=kwargs)
            
            # Try to get from cache
            cached_value = DashboardCache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            DashboardCache.set(cache_key, result, ttl)
            return result
        
        return wrapper
    return decorator


