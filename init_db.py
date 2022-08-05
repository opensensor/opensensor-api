import pymongo

from opensensor.utils import get_open_sensor_db

# Script for creating the Time Series

db = get_open_sensor_db()
try:
    db.validate_collection("Temperature")  # Try to validate a collection
except pymongo.errors.OperationFailure:  # If the collection doesn't exist
    print("Temperature collection doesn't exist yet; Creating ...")
    db.create_collection(
        "Temperature",
        timeseries={"timeField": "timestamp", "metaField": "metadata", "granularity": "minutes"},
    )
try:
    db.validate_collection("Humidity")  # Try to validate a collection
except pymongo.errors.OperationFailure:  # If the collection doesn't exist
    print("Humidity collection doesn't exist yet; Creating ...")
    db.create_collection(
        "Humidity",
        timeseries={"timeField": "timestamp", "metaField": "metadata", "granularity": "minutes"},
    )
