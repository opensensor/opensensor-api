# Flexible Authentication for OpenSensor API

This document describes the new flexible authentication system that allows users to access historical data endpoints using either Fief tokens (existing method) or device API keys (new method).

## Problem Solved

Previously, users authenticated in the web app had no way to get temporary tokens for direct API access outside the web interface. They could only:
- Use Fief access tokens directly (not ideal for external tools)
- Generate device-specific API keys (permanent, only for data submission)

## Solution

The new flexible authentication system allows users to use their existing device API keys to access historical data endpoints directly, providing a simple solution for data export without complex token management.

## Features

### ✅ Device API Key Authentication
- Use existing device API keys for historical data retrieval
- No need to manage separate temporary tokens
- Automatic device access validation

### ✅ Fief Token Caching
- Reduced load on Fief authentication server
- 10-minute cache TTL for token validation
- Automatic cache invalidation on errors

### ✅ Backward Compatibility
- All existing Fief token authentication continues to work
- No breaking changes to current API usage

### ✅ Security
- API keys can only access their associated device data
- Strict device ID and name matching
- Same security model as existing system

## Usage Examples

### 1. Using Device API Key (New Method)

```bash
# Get temperature data using device API key
curl -H "X-API-Key: your_device_api_key_here" \
     "https://api.opensensor.io/temp/device123|MyDevice?page=1&size=10"
```

```python
import requests

headers = {"X-API-Key": "your_device_api_key_here"}
response = requests.get(
    "https://api.opensensor.io/temp/device123|MyDevice",
    headers=headers
)
data = response.json()
```

```javascript
const response = await fetch('https://api.opensensor.io/temp/device123|MyDevice', {
    headers: {
        'X-API-Key': 'your_device_api_key_here'
    }
});
const data = await response.json();
```

### 2. Using Fief Token (Existing Method)

```bash
# Get temperature data using Fief token
curl -H "Authorization: Bearer your_fief_token_here" \
     "https://api.opensensor.io/temp/device123|MyDevice?page=1&size=10"
```

## Supported Endpoints

All historical data endpoints now support both authentication methods:

- `/temp/{device_id}` - Temperature data
- `/humidity/{device_id}` - Humidity data
- `/CO2/{device_id}` - CO2 data
- `/moisture/{device_id}` - Moisture sensor data
- `/pH/{device_id}` - pH data
- `/VPD/{device_id}` - Vapor Pressure Deficit data
- `/pressure/{device_id}` - Pressure data
- `/lux/{device_id}` - Light intensity data
- `/liquid/{device_id}` - Liquid level data
- `/relays/{device_id}` - Relay status data
- `/pumps/{device_id}` - Pump data

## Authentication Flow

### Device API Key Flow
1. User provides API key in `X-API-Key` header
2. System validates API key exists in database
3. System checks if API key is authorized for requested device
4. If authorized, data is returned

### Fief Token Flow (with caching)
1. User provides token in `Authorization: Bearer` header
2. System checks Redis cache for token validation
3. If cache miss, validates with Fief server and caches result
4. If valid, checks device access permissions
5. If authorized, data is returned

## Error Responses

### 401 Unauthorized
```json
{
  "detail": "Authentication required"
}
```
- No authentication provided (neither API key nor token)

### 403 Forbidden
```json
{
  "detail": "API key is not authorized to access device device123|MyDevice"
}
```
- API key doesn't match the requested device

```json
{
  "detail": "Invalid API key"
}
```
- API key not found in database

## Getting Your API Key

1. Log into the web interface at https://opensensor.io
2. Navigate to the sensor dashboard
3. Your existing device API keys are displayed with masked values
4. Use the full API key value for direct API access

## Implementation Details

### Files Modified

1. **`opensensor/users.py`**
   - Added flexible authentication functions
   - Added Fief token caching
   - Added device access validation for API keys

2. **`opensensor/collection_apis.py`**
   - Updated historical data routes to use flexible authentication
   - Improved error messages for different auth types

3. **`opensensor/cache_strategy.py`**
   - Added Fief token caching methods
   - 10-minute TTL for token validation cache

### Security Considerations

- API keys can only access data from their associated device
- Device ID and name must exactly match the API key registration
- Fief tokens maintain existing access control logic
- Cache invalidation on authentication failures
- No sensitive data stored in cache (tokens are hashed)

### Performance Improvements

- **Reduced Fief Server Load**: Token validation cached for 10 minutes
- **Faster API Key Validation**: Direct database lookup without external calls
- **Existing Caching**: Leverages existing Redis caching for data queries

## Testing

Use the provided test script to verify functionality:

```bash
cd opensensor-api
python test_flexible_auth.py
```

Update the script with your actual API key and device ID before running.

## Migration Notes

- **No breaking changes**: All existing code continues to work
- **Gradual adoption**: Users can start using API keys when convenient
- **Monitoring**: Cache hit rates and authentication patterns can be monitored via Redis

## Benefits

1. **Immediate Solution**: Users can export data using existing API keys
2. **Simple Integration**: Easy to use in scripts and external tools
3. **Reduced Complexity**: No temporary token management needed
4. **Better Performance**: Cached authentication reduces server load
5. **Backward Compatible**: No impact on existing users

## Future Enhancements

Potential future improvements could include:
- Bulk export endpoints for large data sets
- API key usage analytics
- Rate limiting per API key
- API key expiration dates
- Scoped permissions for API keys

---

**Note**: This implementation provides the simplest solution to the immediate problem while maintaining security and performance. The flexible authentication system can be extended in the future as needed.
