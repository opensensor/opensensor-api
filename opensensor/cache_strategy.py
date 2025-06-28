"""
Improved caching strategy for opensensor-api

This module implements a more granular caching approach that caches
intermediate results rather than timestamp-dependent function calls.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from opensensor.cache import get_redis_client

logger = logging.getLogger(__name__)


class SensorDataCache:
    """
    Improved caching strategy for sensor data that caches:
    1. Device metadata (long TTL)
    2. Aggregated data chunks (medium TTL)
    3. Raw data segments (short TTL)
    """

    def __init__(self):
        self.redis_client = get_redis_client()

    # Device metadata caching (rarely changes)
    def cache_device_metadata(self, device_id: str, metadata: dict, ttl_hours: int = 24):
        """Cache device metadata with long TTL"""
        if not self.redis_client:
            return

        cache_key = f"opensensor:device_meta:{device_id}"
        try:
            self.redis_client.setex(cache_key, ttl_hours * 3600, json.dumps(metadata, default=str))
            logger.debug(f"Cached device metadata for {device_id}")
        except Exception as e:
            logger.warning(f"Failed to cache device metadata: {e}")

    def get_device_metadata(self, device_id: str) -> Optional[dict]:
        """Get cached device metadata"""
        if not self.redis_client:
            return None

        cache_key = f"opensensor:device_meta:{device_id}"
        try:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                logger.debug(f"Cache hit for device metadata: {device_id}")
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Failed to get cached device metadata: {e}")

        return None

    # Aggregated data caching (changes less frequently)
    def cache_aggregated_data(
        self,
        device_id: str,
        data_type: str,
        time_bucket: str,  # e.g., "2024-01-15-12" for hourly buckets
        resolution: int,
        data: List[dict],
        ttl_minutes: int = 30,
    ):
        """Cache aggregated data chunks"""
        if not self.redis_client:
            return

        cache_key = f"opensensor:agg:{data_type}:{device_id}:{time_bucket}:{resolution}"
        try:
            self.redis_client.setex(cache_key, ttl_minutes * 60, json.dumps(data, default=str))
            logger.debug(f"Cached aggregated data: {cache_key}")
        except Exception as e:
            logger.warning(f"Failed to cache aggregated data: {e}")

    def get_aggregated_data(
        self, device_id: str, data_type: str, time_bucket: str, resolution: int
    ) -> Optional[List[dict]]:
        """Get cached aggregated data"""
        if not self.redis_client:
            return None

        cache_key = f"opensensor:agg:{data_type}:{device_id}:{time_bucket}:{resolution}"
        try:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                logger.debug(f"Cache hit for aggregated data: {cache_key}")
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Failed to get cached aggregated data: {e}")

        return None

    # Pipeline result caching (for complex aggregations)
    def cache_pipeline_result(self, pipeline_hash: str, result: List[dict], ttl_minutes: int = 15):
        """Cache MongoDB aggregation pipeline results"""
        if not self.redis_client:
            return

        cache_key = f"opensensor:pipeline:{pipeline_hash}"
        try:
            self.redis_client.setex(cache_key, ttl_minutes * 60, json.dumps(result, default=str))
            logger.debug(f"Cached pipeline result: {pipeline_hash}")
        except Exception as e:
            logger.warning(f"Failed to cache pipeline result: {e}")

    def get_pipeline_result(self, pipeline_hash: str) -> Optional[List[dict]]:
        """Get cached pipeline result"""
        if not self.redis_client:
            return None

        cache_key = f"opensensor:pipeline:{pipeline_hash}"
        try:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                logger.debug(f"Cache hit for pipeline: {pipeline_hash}")
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Failed to get cached pipeline result: {e}")

        return None

    def generate_pipeline_hash(self, pipeline: List[dict]) -> str:
        """Generate a hash for a MongoDB aggregation pipeline"""
        # Remove pagination stages for consistent hashing
        core_pipeline = [
            stage for stage in pipeline if not any(key in stage for key in ["$skip", "$limit"])
        ]
        pipeline_str = json.dumps(core_pipeline, sort_keys=True, default=str)
        return hashlib.md5(pipeline_str.encode()).hexdigest()

    # Time-based bucket helpers
    def get_time_bucket(self, timestamp: datetime, resolution_minutes: int) -> str:
        """Generate time bucket string for caching"""
        if resolution_minutes <= 60:
            # For high-resolution data, use hourly buckets
            return timestamp.strftime("%Y-%m-%d-%H")
        elif resolution_minutes <= 1440:  # 24 hours
            # For medium resolution, use daily buckets
            return timestamp.strftime("%Y-%m-%d")
        else:
            # For low resolution, use weekly buckets
            week_start = timestamp - timedelta(days=timestamp.weekday())
            return week_start.strftime("%Y-W%U")

    def invalidate_device_cache(self, device_id: str):
        """Invalidate all cache entries for a specific device"""
        if not self.redis_client:
            return 0

        patterns = [
            f"opensensor:device_meta:{device_id}",
            f"opensensor:agg:*:{device_id}:*",
        ]

        deleted_count = 0
        for pattern in patterns:
            try:
                keys = self.redis_client.keys(pattern)
                if keys:
                    deleted_count += self.redis_client.delete(*keys)
            except Exception as e:
                logger.error(f"Failed to invalidate cache pattern {pattern}: {e}")

        logger.info(f"Invalidated {deleted_count} cache entries for device {device_id}")
        return deleted_count

    # Fief token caching (to reduce Fief server load)
    def cache_fief_token_validation(self, token_hash: str, user_info: dict, ttl_minutes: int = 10):
        """Cache Fief token validation results"""
        if not self.redis_client:
            return

        cache_key = f"opensensor:fief_token:{token_hash}"
        try:
            self.redis_client.setex(cache_key, ttl_minutes * 60, json.dumps(user_info, default=str))
            logger.debug(f"Cached Fief token validation: {token_hash[:8]}...")
        except Exception as e:
            logger.warning(f"Failed to cache Fief token validation: {e}")

    def get_cached_fief_token_validation(self, token_hash: str) -> Optional[dict]:
        """Get cached Fief token validation result"""
        if not self.redis_client:
            return None

        cache_key = f"opensensor:fief_token:{token_hash}"
        try:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                logger.debug(f"Cache hit for Fief token: {token_hash[:8]}...")
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Failed to get cached Fief token validation: {e}")

        return None

    def invalidate_fief_token_cache(self, token_hash: str):
        """Invalidate a specific Fief token cache entry"""
        if not self.redis_client:
            return False

        cache_key = f"opensensor:fief_token:{token_hash}"
        try:
            result = self.redis_client.delete(cache_key)
            logger.debug(f"Invalidated Fief token cache: {token_hash[:8]}...")
            return result > 0
        except Exception as e:
            logger.warning(f"Failed to invalidate Fief token cache: {e}")
            return False


# Global cache instance
sensor_cache = SensorDataCache()


def cache_aware_device_lookup(device_id: str) -> Tuple[List[str], str]:
    """
    Device lookup with intelligent caching

    This replaces get_device_info_cached with a more cache-friendly approach
    """
    # Try to get from cache first
    cached_metadata = sensor_cache.get_device_metadata(device_id)
    if cached_metadata:
        return cached_metadata["device_ids"], cached_metadata["device_name"]

    # Cache miss - fetch from database
    from opensensor.users import (
        get_api_keys_by_device_id,
        reduce_api_keys_to_device_ids,
    )

    api_keys, _ = get_api_keys_by_device_id(device_id)
    device_ids, device_name = reduce_api_keys_to_device_ids(api_keys, device_id)

    # Cache the result
    metadata = {
        "device_ids": device_ids,
        "device_name": device_name,
        "cached_at": datetime.utcnow().isoformat(),
    }
    sensor_cache.cache_device_metadata(device_id, metadata)

    return device_ids, device_name


def cache_aware_aggregation(
    collection, pipeline: List[dict], cache_ttl_minutes: int = 15
) -> List[dict]:
    """
    Execute MongoDB aggregation with intelligent caching

    This caches the results of expensive aggregation pipelines
    """
    # Generate hash for the core pipeline (excluding pagination)
    pipeline_hash = sensor_cache.generate_pipeline_hash(pipeline)

    # Try to get from cache
    cached_result = sensor_cache.get_pipeline_result(pipeline_hash)
    if cached_result is not None:
        return cached_result

    # Cache miss - execute pipeline
    result = list(collection.aggregate(pipeline))

    # Cache the result (only if it's not empty and not too large)
    if result and len(json.dumps(result, default=str)) < 1024 * 1024:  # 1MB limit
        sensor_cache.cache_pipeline_result(pipeline_hash, result, cache_ttl_minutes)

    return result
