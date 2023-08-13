from datetime import datetime, timedelta
from operator import itemgetter

from pymongo import ASCENDING

# Create a MongoDB client
from opensensor.db import get_open_sensor_db

# Access the database
db = get_open_sensor_db()

# List of all collections/models to migrate
collections_to_migrate = ["Temperature", "Humidity", "Pressure", "Lux", "CO2", "PH", "Moisture"]
old_collections = {
    "Temperature": "temp",
    "Humidity": "rh",
    "Pressure": "pressure",
    "Lux": "percent",
    "CO2": "ppm",
    "PH": "pH",
    "Moisture": "readings",
}

new_collections = {
    "Temperature": "temp",
    "Humidity": "rh",
    "Pressure": "pressure",
    "Lux": "lux",
    "CO2": "ppm_CO2",
    "PH": "pH",
    "Moisture": "moisture_readings",
}

db["GlobalDataMigration"].insert_one({"migration_name": "FreeTier", "migration_complete": False})

# Determine the earliest and latest timestamps in your data
earliest_timestamp = datetime.now()
latest_timestamp = datetime.min

for collection_name in collections_to_migrate:
    collection = db[collection_name]
    earliest_document = collection.find_one(sort=[("timestamp", ASCENDING)])
    latest_document = collection.find_one(sort=[("timestamp", -1)])
    if earliest_document and earliest_document["timestamp"] < earliest_timestamp:
        earliest_timestamp = earliest_document["timestamp"]
    if latest_document and latest_document["timestamp"] > latest_timestamp:
        latest_timestamp = latest_document["timestamp"]

# Migrate data in chunks, e.g., one week at a time
start_date = earliest_timestamp
one_week = timedelta(weeks=1)

while start_date <= latest_timestamp:
    end_date = start_date + one_week
    all_documents = []

    # Define a "reasonable" time window
    reasonable_time = timedelta(seconds=2)  # Adjust this to whatever makes sense for your data

    # Migrate data in chunks
    start_date = earliest_timestamp

    while start_date <= latest_timestamp:
        end_date = start_date + one_week
        buffer = {}  # We'll store the records for the current time window here

        for collection_name in collections_to_migrate:
            collection = db[collection_name]
            for document in collection.find({"timestamp": {"$gte": start_date, "$lt": end_date}}):
                # Convert to the FreeTier model
                new_document = {
                    "device_metadata": {
                        "device_id": document["device_id"],
                        "name": document.get("name"),
                        "api_key": document.get("api_key"),
                    },
                    new_collections[collection_name]: document.get(
                        old_collections[collection_name]
                    ),
                    "timestamp": document["timestamp"],
                }

                # Merge with an existing document if it's within a reasonable time,
                # otherwise add a new document to the buffer
                for existing_timestamp in buffer.keys():
                    if abs(existing_timestamp - document["timestamp"]) <= reasonable_time:
                        buffer[existing_timestamp][new_collections[collection_name]] = document.get(
                            old_collections[collection_name]
                        )
                        break
                else:
                    buffer[document["timestamp"]] = new_document

        # Sort all documents by timestamp
        all_documents = sorted(buffer.values(), key=itemgetter("timestamp"))

        # Access the destination collection
        free_tier_collection = db["FreeTier"]

        # Insert all documents into the new collection, in sorted order
        for document in all_documents:
            free_tier_collection.insert_one(document)

        # Advance to the next time chunk
        start_date = end_date


db["GlobalDataMigration"].update_one(
    {"migration_name": "FreeTier"}, {"$set": {"migration_complete": True}}
)
