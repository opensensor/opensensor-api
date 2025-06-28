# Caching Migration: From In-Memory to Redis

## Overview

This document describes the migration from problematic in-memory caching to a Redis-based distributed caching solution for the opensensor-api running in Kubernetes.

## Problem Statement

The original implementation used simple in-memory caching with global dictionaries:

```python
# Problematic in-memory cache
_cache = {}
_cache_timestamps = {}
```

### Issues with In-Memory Caching in Kubernetes:

1. **Pod Isolation**: Each of the 4 replicas has its own memory space, so cached data isn't shared
2. **Cache Inconsistency**: Different pods may have different cached values for the same data
3. **Memory Waste**: Each pod duplicates the same cached data
4. **Pod Restarts**: Cache is lost when pods restart (common in K8s)
5. **Scaling Issues**: Adding more replicas multiplies memory usage and cache inconsistency

## Solution: Redis-Based Distributed Caching

### Architecture Changes

1. **New Cache Module**: `opensensor/cache.py`
   - Redis connection management with connection pooling
   - Graceful fallback when Redis is unavailable
   - Comprehensive error handling and logging

2. **Updated Collection APIs**: `opensensor/collection_apis.py`
   - Replaced `simple_cache` decorator with `redis_cache`
   - Updated `get_device_info_cached` function to use Redis

3. **Cache Management Endpoints**: Added to `opensensor/app.py`
   - `/cache/stats` - Get cache statistics
   - `/cache/clear` - Clear all cache entries
   - `/cache/invalidate` - Invalidate specific cache patterns

### Key Features

#### Redis Cache Decorator
```python
@redis_cache(ttl_seconds=300)
def get_device_info_cached(device_id: str):
    """Cached device information lookup using Redis"""
    api_keys, _ = get_api_keys_by_device_id(device_id)
    return reduce_api_keys_to_device_ids(api_keys, device_id)
```

#### Graceful Fallback
- If Redis is unavailable, functions execute without caching
- No service disruption when Redis is down
- Automatic reconnection attempts

#### Connection Management
- Uses existing `REDIS_URL` environment variable
- Connection pooling for optimal performance
- Health checks and timeout handling

## Configuration

### Environment Variables
- `REDIS_URL`: Redis connection string (already available in deployment)

### Dependencies
Added to `Pipfile`:
```toml
redis = "*"
```

## Cache Management

### Monitoring
```bash
# Get cache statistics
GET /cache/stats
```

Response includes:
- Redis connection status
- Number of opensensor cache keys
- Redis version and memory usage
- Cache hit/miss ratios

### Maintenance
```bash
# Clear all cache
POST /cache/clear

# Invalidate specific patterns
POST /cache/invalidate
{
  "pattern": "get_device_info_cached:*"
}
```

## Benefits

1. **Shared Cache**: All pods share the same cache, ensuring consistency
2. **Persistence**: Cache survives pod restarts
3. **Scalability**: Adding more API pods doesn't duplicate cache data
4. **Performance**: Redis is optimized for caching workloads
5. **Monitoring**: Built-in metrics and monitoring capabilities
6. **Reliability**: Graceful degradation when Redis is unavailable

## Deployment Notes

### Kubernetes Deployment
- No changes required to existing deployment YAML
- Uses existing `REDIS_URL` environment variable
- Backward compatible - works with or without Redis

### Rolling Update Strategy
1. Deploy new image with Redis caching
2. Old in-memory cache will be gradually replaced
3. No downtime or service interruption

### Monitoring
- Check `/cache/stats` endpoint for Redis connectivity
- Monitor Redis metrics through existing infrastructure
- Log analysis for cache hit/miss ratios

## Testing

### Local Development
```bash
# Install dependencies
pipenv install

# Set Redis URL (if testing locally)
export REDIS_URL="redis://localhost:6379"

# Run the application
uvicorn opensensor.app:app --reload
```

### Cache Verification
```bash
# Check cache stats
curl -X GET "http://localhost:8000/cache/stats" \
  -H "Authorization: Bearer <token>"

# Test cache invalidation
curl -X POST "http://localhost:8000/cache/invalidate" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"pattern": "*"}'
```

## Migration Checklist

- [x] Add Redis dependency to Pipfile
- [x] Create Redis cache utility module
- [x] Replace in-memory caching in collection_apis.py
- [x] Add cache management endpoints
- [x] Update main app to include collection router
- [x] Document migration process
- [ ] Deploy to staging environment
- [ ] Verify Redis connectivity
- [ ] Monitor cache performance
- [ ] Deploy to production

## Rollback Plan

If issues arise, the system gracefully falls back to no caching when Redis is unavailable. For complete rollback:

1. Revert to previous image version
2. In-memory caching will resume automatically
3. No data loss or service interruption

## Performance Expectations

- **Cache Hit Ratio**: Expected 80-90% for device info lookups
- **Response Time**: 10-50ms improvement for cached requests
- **Memory Usage**: Reduced per-pod memory usage
- **Consistency**: 100% cache consistency across all pods
