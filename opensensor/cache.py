import hashlib
import json
import logging
import os
from functools import wraps
from typing import Optional

import redis
from redis.exceptions import ConnectionError, RedisError

logger = logging.getLogger(__name__)

# Redis connection
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> Optional[redis.Redis]:
    """Get Redis client instance with connection pooling"""
    global _redis_client

    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            logger.warning("REDIS_URL environment variable not set, caching disabled")
            return None

        try:
            _redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            # Test connection
            _redis_client.ping()
            logger.info("Redis connection established successfully")
        except (ConnectionError, RedisError) as e:
            logger.error(f"Failed to connect to Redis: {e}")
            _redis_client = None

    return _redis_client


def redis_cache(ttl_seconds: int = 300):
    """Redis-based cache decorator with fallback to no caching"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            redis_client = get_redis_client()

            # If Redis is not available, execute function without caching
            if redis_client is None:
                logger.debug(f"Redis unavailable, executing {func.__name__} without cache")
                return func(*args, **kwargs)

            # Create cache key from function name and arguments
            cache_key = f"opensensor:{func.__name__}:{hashlib.md5(str(args + tuple(kwargs.items())).encode()).hexdigest()}"

            try:
                # Try to get cached result
                cached_result = redis_client.get(cache_key)
                if cached_result is not None:
                    logger.debug(f"Cache hit for {cache_key}")
                    return json.loads(cached_result)

                # Execute function and cache result
                result = func(*args, **kwargs)

                # Cache the result with TTL
                redis_client.setex(
                    cache_key,
                    ttl_seconds,
                    json.dumps(result, default=str),  # default=str handles datetime objects
                )
                logger.debug(f"Cache miss for {cache_key}, result cached with TTL {ttl_seconds}s")

                return result

            except (ConnectionError, RedisError) as e:
                logger.warning(f"Redis error during cache operation: {e}, executing without cache")
                return func(*args, **kwargs)

        return wrapper

    return decorator


def invalidate_cache_pattern(pattern: str) -> int:
    """Invalidate cache entries matching a pattern"""
    redis_client = get_redis_client()
    if redis_client is None:
        return 0

    try:
        keys = redis_client.keys(f"opensensor:{pattern}")
        if keys:
            deleted = redis_client.delete(*keys)
            logger.info(f"Invalidated {deleted} cache entries matching pattern: {pattern}")
            return deleted
        return 0
    except (ConnectionError, RedisError) as e:
        logger.error(f"Failed to invalidate cache pattern {pattern}: {e}")
        return 0


def clear_all_cache() -> bool:
    """Clear all opensensor cache entries"""
    redis_client = get_redis_client()
    if redis_client is None:
        return False

    try:
        keys = redis_client.keys("opensensor:*")
        if keys:
            deleted = redis_client.delete(*keys)
            logger.info(f"Cleared {deleted} cache entries")
        return True
    except (ConnectionError, RedisError) as e:
        logger.error(f"Failed to clear cache: {e}")
        return False


def get_cache_stats() -> dict:
    """Get cache statistics"""
    redis_client = get_redis_client()
    if redis_client is None:
        return {"status": "unavailable"}

    try:
        info = redis_client.info()
        keys_count = len(redis_client.keys("opensensor:*"))

        return {
            "status": "connected",
            "opensensor_keys": keys_count,
            "redis_version": info.get("redis_version"),
            "used_memory": info.get("used_memory_human"),
            "connected_clients": info.get("connected_clients"),
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
        }
    except (ConnectionError, RedisError) as e:
        logger.error(f"Failed to get cache stats: {e}")
        return {"status": "error", "error": str(e)}
