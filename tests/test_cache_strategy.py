import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from opensensor.cache_strategy import (
    SensorDataCache,
    cache_aware_device_lookup,
    cache_aware_aggregation,
    sensor_cache
)


class TestSensorDataCache:
    """Test the improved sensor data caching strategy"""

    def test_device_metadata_caching(self):
        """Test device metadata caching with long TTL"""
        mock_redis = Mock()
        mock_redis.setex.return_value = True
        mock_redis.get.return_value = None
        
        with patch('opensensor.cache_strategy.get_redis_client', return_value=mock_redis):
            cache = SensorDataCache()
            
            # Test caching metadata
            metadata = {"device_ids": ["dev1"], "device_name": "test_device"}
            cache.cache_device_metadata("device123", metadata, ttl_hours=24)
            
            mock_redis.setex.assert_called_once()
            args = mock_redis.setex.call_args[0]
            assert args[0] == "opensensor:device_meta:device123"
            assert args[1] == 24 * 3600  # 24 hours in seconds

    def test_device_metadata_retrieval(self):
        """Test retrieving cached device metadata"""
        mock_redis = Mock()
        cached_data = '{"device_ids": ["dev1"], "device_name": "test_device"}'
        mock_redis.get.return_value = cached_data
        
        with patch('opensensor.cache_strategy.get_redis_client', return_value=mock_redis):
            cache = SensorDataCache()
            
            result = cache.get_device_metadata("device123")
            
            assert result is not None
            assert result["device_ids"] == ["dev1"]
            assert result["device_name"] == "test_device"
            mock_redis.get.assert_called_with("opensensor:device_meta:device123")

    def test_aggregated_data_caching(self):
        """Test caching of aggregated data chunks"""
        mock_redis = Mock()
        mock_redis.setex.return_value = True
        
        with patch('opensensor.cache_strategy.get_redis_client', return_value=mock_redis):
            cache = SensorDataCache()
            
            data = [{"timestamp": "2024-01-01T12:00:00", "temp": 25.5}]
            cache.cache_aggregated_data(
                device_id="device123",
                data_type="temperature",
                time_bucket="2024-01-01-12",
                resolution=30,
                data=data,
                ttl_minutes=30
            )
            
            mock_redis.setex.assert_called_once()
            args = mock_redis.setex.call_args[0]
            assert args[0] == "opensensor:agg:temperature:device123:2024-01-01-12:30"
            assert args[1] == 30 * 60  # 30 minutes in seconds

    def test_pipeline_hash_generation(self):
        """Test that pipeline hashes are generated consistently"""
        cache = SensorDataCache()
        
        pipeline1 = [
            {"$match": {"device_id": "dev1"}},
            {"$group": {"_id": "$hour", "avg": {"$avg": "$temp"}}},
            {"$skip": 0},
            {"$limit": 50}
        ]
        
        pipeline2 = [
            {"$match": {"device_id": "dev1"}},
            {"$group": {"_id": "$hour", "avg": {"$avg": "$temp"}}},
            {"$skip": 10},
            {"$limit": 50}
        ]
        
        # Should generate same hash (pagination stages removed)
        hash1 = cache.generate_pipeline_hash(pipeline1)
        hash2 = cache.generate_pipeline_hash(pipeline2)
        
        assert hash1 == hash2
        assert len(hash1) == 32  # MD5 hash length

    def test_time_bucket_generation(self):
        """Test time bucket generation for different resolutions"""
        cache = SensorDataCache()
        test_time = datetime(2024, 1, 15, 14, 30, 0)
        
        # High resolution (30 min) -> hourly buckets
        bucket_high = cache.get_time_bucket(test_time, 30)
        assert bucket_high == "2024-01-15-14"
        
        # Medium resolution (6 hours) -> daily buckets
        bucket_medium = cache.get_time_bucket(test_time, 360)
        assert bucket_medium == "2024-01-15"
        
        # Low resolution (2 days) -> weekly buckets
        bucket_low = cache.get_time_bucket(test_time, 2880)
        assert bucket_low.startswith("2024-W")

    def test_cache_invalidation(self):
        """Test cache invalidation for a device"""
        mock_redis = Mock()
        mock_redis.keys.side_effect = [
            ["opensensor:device_meta:device123"],
            ["opensensor:agg:temp:device123:2024-01-01:30"]
        ]
        mock_redis.delete.return_value = 2
        
        with patch('opensensor.cache_strategy.get_redis_client', return_value=mock_redis):
            cache = SensorDataCache()
            
            deleted_count = cache.invalidate_device_cache("device123")
            
            assert deleted_count == 2
            assert mock_redis.keys.call_count == 2
            mock_redis.delete.assert_called()


class TestCacheAwareFunctions:
    """Test the cache-aware wrapper functions"""

    def test_cache_aware_device_lookup_hit(self):
        """Test device lookup with cache hit"""
        mock_redis = Mock()
        cached_data = '{"device_ids": ["dev1", "dev2"], "device_name": "test_device"}'
        mock_redis.get.return_value = cached_data
        
        with patch('opensensor.cache_strategy.get_redis_client', return_value=mock_redis):
            device_ids, device_name = cache_aware_device_lookup("device123")
            
            assert device_ids == ["dev1", "dev2"]
            assert device_name == "test_device"

    def test_cache_aware_device_lookup_miss(self):
        """Test device lookup with cache miss"""
        mock_redis = Mock()
        mock_redis.get.return_value = None
        mock_redis.setex.return_value = True
        
        with patch('opensensor.cache_strategy.get_redis_client', return_value=mock_redis):
            with patch('opensensor.cache_strategy.get_api_keys_by_device_id') as mock_get_keys:
                with patch('opensensor.cache_strategy.reduce_api_keys_to_device_ids') as mock_reduce:
                    mock_get_keys.return_value = (["key1"], None)
                    mock_reduce.return_value = (["dev1"], "test_device")
                    
                    device_ids, device_name = cache_aware_device_lookup("device123")
                    
                    assert device_ids == ["dev1"]
                    assert device_name == "test_device"
                    mock_redis.setex.assert_called_once()

    def test_cache_aware_aggregation_hit(self):
        """Test aggregation with cache hit"""
        mock_redis = Mock()
        cached_result = '[{"timestamp": "2024-01-01", "temp": 25.5}]'
        mock_redis.get.return_value = cached_result
        
        mock_collection = Mock()
        pipeline = [{"$match": {"device_id": "dev1"}}]
        
        with patch('opensensor.cache_strategy.get_redis_client', return_value=mock_redis):
            result = cache_aware_aggregation(mock_collection, pipeline)
            
            assert len(result) == 1
            assert result[0]["temp"] == 25.5
            mock_collection.aggregate.assert_not_called()

    def test_cache_aware_aggregation_miss(self):
        """Test aggregation with cache miss"""
        mock_redis = Mock()
        mock_redis.get.return_value = None
        mock_redis.setex.return_value = True
        
        mock_collection = Mock()
        mock_collection.aggregate.return_value = [{"timestamp": "2024-01-01", "temp": 25.5}]
        pipeline = [{"$match": {"device_id": "dev1"}}]
        
        with patch('opensensor.cache_strategy.get_redis_client', return_value=mock_redis):
            result = cache_aware_aggregation(mock_collection, pipeline)
            
            assert len(result) == 1
            assert result[0]["temp"] == 25.5
            mock_collection.aggregate.assert_called_once_with(pipeline)
            mock_redis.setex.assert_called_once()

    def test_cache_aware_aggregation_without_redis(self):
        """Test aggregation when Redis is unavailable"""
        mock_collection = Mock()
        mock_collection.aggregate.return_value = [{"timestamp": "2024-01-01", "temp": 25.5}]
        pipeline = [{"$match": {"device_id": "dev1"}}]
        
        with patch('opensensor.cache_strategy.get_redis_client', return_value=None):
            result = cache_aware_aggregation(mock_collection, pipeline)
            
            assert len(result) == 1
            assert result[0]["temp"] == 25.5
            mock_collection.aggregate.assert_called_once_with(pipeline)


class TestCacheIntegration:
    """Integration tests for the caching strategy"""

    def test_cache_key_consistency(self):
        """Test that cache keys are generated consistently"""
        cache = SensorDataCache()
        
        # Same pipeline should generate same hash
        pipeline = [{"$match": {"device_id": "dev1"}}]
        hash1 = cache.generate_pipeline_hash(pipeline)
        hash2 = cache.generate_pipeline_hash(pipeline)
        
        assert hash1 == hash2

    def test_cache_size_limit(self):
        """Test that large results are not cached"""
        mock_redis = Mock()
        mock_redis.get.return_value = None
        
        # Create a large result that exceeds 1MB limit
        large_result = [{"data": "x" * 1000} for _ in range(2000)]
        mock_collection = Mock()
        mock_collection.aggregate.return_value = large_result
        
        with patch('opensensor.cache_strategy.get_redis_client', return_value=mock_redis):
            result = cache_aware_aggregation(mock_collection, [])
            
            # Should execute but not cache due to size
            assert len(result) == 2000
            mock_redis.setex.assert_not_called()

    @pytest.mark.skipif(True, reason="Requires actual Redis connection")
    def test_real_redis_integration(self):
        """Test with real Redis if available"""
        # This would test actual Redis operations
        # Skip by default to avoid requiring Redis in CI
        pass
