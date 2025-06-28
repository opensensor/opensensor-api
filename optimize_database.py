"""
Database optimization script for OpenSensor API
Adds indexes and optimizations for the FreeTier collection
"""

from pymongo import ASCENDING, DESCENDING

from opensensor.db import get_open_sensor_db


def create_indexes():
    """Create optimized indexes for the FreeTier collection"""
    db = get_open_sensor_db()
    collection = db["FreeTier"]

    print("Creating indexes for FreeTier collection...")

    # Primary compound index for time-series queries
    # This covers the most common query pattern: device + time range
    collection.create_index(
        [
            ("metadata.device_id", ASCENDING),
            ("metadata.name", ASCENDING),
            ("timestamp", DESCENDING),
        ],
        name="device_time_idx",
    )
    print("✓ Created device_time_idx")

    # Regular indexes for specific sensor types with timestamp
    # Note: Sparse indexes are not supported on time-series collections
    sensor_fields = [
        "temp",
        "rh",
        "ppm_CO2",
        "moisture_readings",
        "pH",
        "pressure",
        "lux",
        "liquid",
        "relays",
    ]

    for field in sensor_fields:
        try:
            collection.create_index(
                [(field, ASCENDING), ("timestamp", DESCENDING)], name=f"{field}_time_idx"
            )
            print(f"✓ Created {field}_time_idx")
        except Exception as e:
            # Skip if field doesn't exist or index creation fails
            print(f"⚠️  Skipped {field}_time_idx: {str(e)}")

    # User-based queries optimization
    try:
        collection.create_index(
            [("metadata.user_id", ASCENDING), ("timestamp", DESCENDING)], name="user_time_idx"
        )
        print("✓ Created user_time_idx")
    except Exception as e:
        print(f"⚠️  Skipped user_time_idx: {str(e)}")

    # Optimize Users collection
    users_collection = db["Users"]

    # API key lookup optimization
    users_collection.create_index(
        [("api_keys.device_id", ASCENDING), ("api_keys.device_name", ASCENDING)],
        name="api_keys_device_idx",
    )
    print("✓ Created api_keys_device_idx")

    # API key validation optimization
    users_collection.create_index("api_keys.key", name="api_key_lookup_idx")
    print("✓ Created api_key_lookup_idx")

    print("\nIndexes created successfully!")

    # Print index statistics
    print("\nCurrent indexes:")
    for index in collection.list_indexes():
        print(f"  - {index['name']}: {index.get('key', {})}")


def analyze_collection_stats():
    """Analyze collection statistics for optimization insights"""
    db = get_open_sensor_db()
    collection = db["FreeTier"]

    print("\n=== Collection Statistics ===")
    stats = db.command("collStats", "FreeTier")

    print(f"Document count: {stats.get('count', 0):,}")
    print(f"Average document size: {stats.get('avgObjSize', 0):,} bytes")
    print(f"Total collection size: {stats.get('size', 0) / (1024*1024):.2f} MB")
    print(f"Storage size: {stats.get('storageSize', 0) / (1024*1024):.2f} MB")
    print(f"Total index size: {stats.get('totalIndexSize', 0) / (1024*1024):.2f} MB")

    # Sample document analysis
    sample_doc = collection.find_one()
    if sample_doc:
        print(f"\nSample document fields: {list(sample_doc.keys())}")
        if "metadata" in sample_doc:
            print(f"Metadata fields: {list(sample_doc['metadata'].keys())}")


if __name__ == "__main__":
    print("OpenSensor Database Optimization")
    print("=" * 40)

    try:
        analyze_collection_stats()
        create_indexes()
        print("\n✅ Database optimization completed successfully!")

    except Exception as e:
        print(f"\n❌ Error during optimization: {e}")
        raise
