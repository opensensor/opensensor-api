import os
import pytest
from unittest.mock import Mock, patch
from opensensor.cache import redis_cache, get_redis_client, get_cache_stats, clear_all_cache


class TestRedisCache:
    """Test Redis caching functionality"""

    def test_redis_cache_decorator_with_redis_available(self):
        """Test cache decorator when Redis is available"""
        
        # Mock Redis client
        mock_redis = Mock()
        mock_redis.get.return_value = None  # Cache miss
        mock_redis.setex.return_value = True
        
        with patch('opensensor.cache.get_redis_client', return_value=mock_redis):
            @redis_cache(ttl_seconds=60)
            def test_function(arg1, arg2):
                return f"result_{arg1}_{arg2}"
            
            result = test_function("test", "value")
            
            assert result == "result_test_value"
            mock_redis.get.assert_called_once()
            mock_redis.setex.assert_called_once()

    def test_redis_cache_decorator_with_cache_hit(self):
        """Test cache decorator with cache hit"""
        
        # Mock Redis client with cached result
        mock_redis = Mock()
        mock_redis.get.return_value = '"cached_result"'  # Cache hit
        
        with patch('opensensor.cache.get_redis_client', return_value=mock_redis):
            @redis_cache(ttl_seconds=60)
            def test_function(arg1, arg2):
                return f"result_{arg1}_{arg2}"
            
            result = test_function("test", "value")
            
            assert result == "cached_result"
            mock_redis.get.assert_called_once()
            mock_redis.setex.assert_not_called()

    def test_redis_cache_decorator_without_redis(self):
        """Test cache decorator when Redis is unavailable"""
        
        with patch('opensensor.cache.get_redis_client', return_value=None):
            @redis_cache(ttl_seconds=60)
            def test_function(arg1, arg2):
                return f"result_{arg1}_{arg2}"
            
            result = test_function("test", "value")
            
            assert result == "result_test_value"

    def test_redis_cache_decorator_with_redis_error(self):
        """Test cache decorator when Redis throws an error"""
        
        # Mock Redis client that throws an error
        mock_redis = Mock()
        mock_redis.get.side_effect = Exception("Redis connection error")
        
        with patch('opensensor.cache.get_redis_client', return_value=mock_redis):
            @redis_cache(ttl_seconds=60)
            def test_function(arg1, arg2):
                return f"result_{arg1}_{arg2}"
            
            result = test_function("test", "value")
            
            assert result == "result_test_value"

    def test_get_redis_client_without_url(self):
        """Test Redis client creation without REDIS_URL"""
        
        with patch.dict(os.environ, {}, clear=True):
            client = get_redis_client()
            assert client is None

    def test_get_cache_stats_without_redis(self):
        """Test cache stats when Redis is unavailable"""
        
        with patch('opensensor.cache.get_redis_client', return_value=None):
            stats = get_cache_stats()
            assert stats["status"] == "unavailable"

    def test_get_cache_stats_with_redis(self):
        """Test cache stats when Redis is available"""
        
        mock_redis = Mock()
        mock_redis.info.return_value = {
            "redis_version": "6.2.0",
            "used_memory_human": "1.5M",
            "connected_clients": 5,
            "keyspace_hits": 100,
            "keyspace_misses": 20
        }
        mock_redis.keys.return_value = ["opensensor:key1", "opensensor:key2"]
        
        with patch('opensensor.cache.get_redis_client', return_value=mock_redis):
            stats = get_cache_stats()
            
            assert stats["status"] == "connected"
            assert stats["opensensor_keys"] == 2
            assert stats["redis_version"] == "6.2.0"
            assert stats["keyspace_hits"] == 100

    def test_clear_all_cache_without_redis(self):
        """Test cache clearing when Redis is unavailable"""
        
        with patch('opensensor.cache.get_redis_client', return_value=None):
            result = clear_all_cache()
            assert result is False

    def test_clear_all_cache_with_redis(self):
        """Test cache clearing when Redis is available"""
        
        mock_redis = Mock()
        mock_redis.keys.return_value = ["opensensor:key1", "opensensor:key2"]
        mock_redis.delete.return_value = 2
        
        with patch('opensensor.cache.get_redis_client', return_value=mock_redis):
            result = clear_all_cache()
            
            assert result is True
            mock_redis.keys.assert_called_with("opensensor:*")
            mock_redis.delete.assert_called_with("opensensor:key1", "opensensor:key2")


class TestCacheIntegration:
    """Integration tests for cache functionality"""

    @pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="Redis not available")
    def test_real_redis_connection(self):
        """Test actual Redis connection if available"""
        
        client = get_redis_client()
        if client:
            # Test basic Redis operations
            client.set("test_key", "test_value", ex=10)
            assert client.get("test_key") == "test_value"
            client.delete("test_key")

    def test_cache_key_generation(self):
        """Test that cache keys are generated consistently"""
        
        mock_redis = Mock()
        mock_redis.get.return_value = None
        mock_redis.setex.return_value = True
        
        with patch('opensensor.cache.get_redis_client', return_value=mock_redis):
            @redis_cache(ttl_seconds=60)
            def test_function(arg1, arg2):
                return f"result_{arg1}_{arg2}"
            
            # Call function twice with same arguments
            test_function("test", "value")
            test_function("test", "value")
            
            # Should use the same cache key both times
            assert mock_redis.get.call_count == 2
            call_args = [call[0][0] for call in mock_redis.get.call_args_list]
            assert call_args[0] == call_args[1]  # Same cache key
            assert call_args[0].startswith("opensensor:test_function:")
