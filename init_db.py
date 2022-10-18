import pymongo

from opensensor.utils import get_open_sensor_db

# Script for creating the Time Series

db = get_open_sensor_db()
try:
    db.Temperature  # Try to validate a collection
except pymongo.errors.OperationFailure:  # If the collection doesn't exist
    print("Temperature collection doesn't exist yet; Creating ...")
    db.create_collection(
        "Temperature",
        timeseries={"timeField": "timestamp", "metaField": "metadata", "granularity": "minutes"},
    )
try:
    db.Humidity  # Try to validate a collection
except pymongo.errors.OperationFailure:  # If the collection doesn't exist
    print("Humidity collection doesn't exist yet; Creating ...")
    db.create_collection(
        "Humidity",
        timeseries={"timeField": "timestamp", "metaField": "metadata", "granularity": "minutes"},
    )
try:
    db.Pressure  # Try to validate a collection
except pymongo.errors.OperationFailure:  # If the collection doesn't exist
    print("Pressure collection doesn't exist yet; Creating ...")
    db.create_collection(
        "Pressure",
        timeseries={"timeField": "timestamp", "metaField": "metadata", "granularity": "minutes"},
    )
