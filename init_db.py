from opensensor.utils import get_open_sensor_db

# Script for creating the Time Series

db = get_open_sensor_db()
db.create_collection(
    "Temperature",
    timeseries={"timeField": "timestamp", "metaField": "metadata", "granularity": "minutes"},
)
db.create_collection(
    "Humidity",
    timeseries={"timeField": "timestamp", "metaField": "metadata", "granularity": "minutes"},
)
