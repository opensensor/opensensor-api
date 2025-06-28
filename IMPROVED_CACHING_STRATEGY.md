# Improved Caching Strategy for OpenSensor API

## Problem Analysis

The original caching implementation had a fundamental flaw: it was caching function results that included timestamp parameters in the cache key. This meant:

```python
# OLD: Cache key included ALL parameters including timestamps
@redis_cache(ttl_seconds=300)
def get_device_info_cached(device_id: str):
    # Cache key: opensensor:get_device_info_cached:md5(device_id + start_date + end_date + resolution)
```

**Issues:**
- Different time ranges = different cache keys
- Different resolutions = different cache keys
- Cache hit rate was essentially 0% for time-series data
- Wasted Redis memory with duplicate device lookups

## Solution: Granular Caching Strategy

### 1. **Device Metadata Caching** (Long TTL - 24 hours)
```python
# Cache device info separately from query parameters
cache_key = f"opensensor:device_meta:{device_id}"
# TTL: 24 hours (device metadata rarely changes)
```

### 2. **Pipeline Result Caching** (Medium TTL - 15 minutes)
```python
# Cache MongoDB aggregation results by pipeline hash
pipeline_hash = md5(core_pipeline_without_pagination)
cache_key = f"opensensor:pipeline:{pipeline_hash}"
# TTL: 15 minutes (good balance for time-series data)
```

### 3. **Aggregated Data Chunks** (Short TTL - 30 minutes)
```python
# Cache pre-aggregated data by time buckets
cache_key = f"opensensor:agg:{data_type}:{device_id}:{time_bucket}:{resolution}"
# TTL: 30 minutes (for frequently accessed data ranges)
```

## Key Improvements

### ✅ **Cache Key Independence**
- Device metadata cached independently of query parameters
- Pipeline results cached by content hash, not input parameters
- Time-based bucketing for aggregated data

### ✅ **Intelligent TTL Strategy**
- **Device metadata**: 24 hours (rarely changes)
- **Pipeline results**: 15 minutes (balance freshness vs performance)
- **Aggregated chunks**: 30 minutes (frequently accessed ranges)

### ✅ **Smart Cache Invalidation**
```python
# Invalidate relevant caches when new data arrives
def _record_data_to_ts_collection(collection, environment, user=None):
    # ... insert data ...
    device_id = environment.device_metadata.device_id
    sensor_cache.invalidate_device_cache(device_id)
```

### ✅ **Size-Aware Caching**
```python
# Don't cache results larger than 1MB
if result and len(json.dumps(result, default=str)) < 1024 * 1024:
    sensor_cache.cache_pipeline_result(pipeline_hash, result, ttl_minutes)
```

### ✅ **Graceful Degradation**
- Falls back to direct database queries when Redis unavailable
- No service disruption if caching fails

## Implementation Details

### Cache-Aware Device Lookup
```python
def cache_aware_device_lookup(device_id: str) -> Tuple[List[str], str]:
    # Try cache first
    cached_metadata = sensor_cache.get_device_metadata(device_id)
    if cached_metadata:
        return cached_metadata['device_ids'], cached_metadata['device_name']

    # Cache miss - fetch and cache
    api_keys, _ = get_api_keys_by_device_id(device_id)
    device_ids, device_name = reduce_api_keys_to_device_ids(api_keys, device_id)

    metadata = {
        'device_ids': device_ids,
        'device_name': device_name,
        'cached_at': datetime.utcnow().isoformat()
    }
    sensor_cache.cache_device_metadata(device_id, metadata)
    return device_ids, device_name
```

### Cache-Aware Aggregation
```python
def cache_aware_aggregation(collection, pipeline: List[dict], cache_ttl_minutes: int = 15) -> List[dict]:
    # Generate hash excluding pagination
    pipeline_hash = sensor_cache.generate_pipeline_hash(pipeline)

    # Try cache
    cached_result = sensor_cache.get_pipeline_result(pipeline_hash)
    if cached_result is not None:
        return cached_result

    # Execute and cache
    result = list(collection.aggregate(pipeline))
    if result and len(json.dumps(result, default=str)) < 1024 * 1024:
        sensor_cache.cache_pipeline_result(pipeline_hash, result, cache_ttl_minutes)

    return result
```

## Performance Benefits

### Expected Improvements:
- **Cache Hit Rate**: 80-90% for device lookups (vs ~0% before)
- **Response Time**: 10-50ms improvement for cached requests
- **Database Load**: Significant reduction in MongoDB aggregation queries
- **Memory Efficiency**: No duplicate device metadata across cache entries

### Cache Effectiveness by Use Case:

1. **Dashboard Loading**: High hit rate for device metadata
2. **Time Series Charts**: Medium hit rate for common time ranges
3. **Real-time Updates**: Smart invalidation ensures data freshness
4. **API Pagination**: Same core data cached across pages

## Migration Strategy

### Phase 1: ✅ **Implement New Strategy**
- [x] Create `cache_strategy.py` with improved caching logic
- [x] Update `collection_apis.py` to use new caching functions
- [x] Add cache invalidation to data recording functions
- [x] Create comprehensive tests

### Phase 2: **Deploy and Monitor**
- [ ] Deploy to staging environment
- [ ] Monitor cache hit rates via `/cache/stats` endpoint
- [ ] Verify performance improvements
- [ ] Monitor Redis memory usage

### Phase 3: **Optimize and Scale**
- [ ] Fine-tune TTL values based on usage patterns
- [ ] Add more granular cache invalidation
- [ ] Consider implementing cache warming for popular devices

## Monitoring and Debugging

### Cache Statistics Endpoint
```bash
GET /cache/stats
```

Returns:
```json
{
  "status": "connected",
  "opensensor_keys": 1250,
  "redis_version": "6.2.0",
  "used_memory": "15.2M",
  "keyspace_hits": 8420,
  "keyspace_misses": 1580,
  "hit_rate": "84.2%"
}
```

### Cache Management
```bash
# Clear all cache
POST /cache/clear

# Invalidate specific patterns
POST /cache/invalidate
{"pattern": "device_meta:*"}
```

### Debugging Cache Behavior
```python
# Enable debug logging
import logging
logging.getLogger('opensensor.cache_strategy').setLevel(logging.DEBUG)
```

## Backward Compatibility

- ✅ **Zero Breaking Changes**: All existing API endpoints work unchanged
- ✅ **Graceful Fallback**: Works without Redis (falls back to direct DB queries)
- ✅ **Incremental Adoption**: Can be deployed alongside existing caching

## Future Enhancements

### Potential Optimizations:
1. **Cache Warming**: Pre-populate cache for popular devices
2. **Compression**: Compress large cached results
3. **Distributed Caching**: Shard cache across multiple Redis instances
4. **Predictive Caching**: Cache likely-to-be-requested time ranges
5. **Cache Analytics**: Track which data types benefit most from caching

### Advanced Features:
1. **Time-based Expiration**: Expire cache entries based on data age
2. **Smart Prefetching**: Prefetch adjacent time ranges
3. **Cache Hierarchy**: Multi-level caching (Redis + in-memory)
4. **Query Optimization**: Cache intermediate aggregation steps

## Conclusion

This improved caching strategy addresses the fundamental issue with timestamp-dependent cache keys by:

1. **Separating concerns**: Device metadata vs query results
2. **Using content-based hashing**: Pipeline results cached by content, not parameters
3. **Implementing intelligent TTLs**: Different expiration times for different data types
4. **Adding smart invalidation**: Cache cleared when new data arrives

The result is a much more effective caching system that should significantly improve API performance while maintaining data freshness and consistency.
