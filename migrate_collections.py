from datetime import datetime, timedelta
from operator import itemgetter

from pymongo import ASCENDING

from opensensor.collection_apis import new_collections, old_collections

# Create a MongoDB client
from opensensor.db import get_open_sensor_db

# Access the database
db = get_open_sensor_db()

collections_to_migrate = ["Temperature", "Humidity", "Pressure", "Lux", "CO2", "PH", "Moisture"]

migration = db.Migration.find_one({"migration_name": "FreeTier"})
if not migration:
    db["Migration"].insert_one({"migration_name": "FreeTier", "migration_complete": False})

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

start_date = earliest_timestamp
one_week = timedelta(weeks=1)

while start_date <= latest_timestamp:
    end_date = start_date + one_week
    buffer = {}

    for collection_name in collections_to_migrate:
        collection = db[collection_name]
        for document in collection.find({"timestamp": {"$gte": start_date, "$lt": end_date}}):
            unit = document["metadata"].get("unit")
            new_document = {
                "metadata": {
                    "device_id": document["metadata"]["device_id"],
                    "name": document["metadata"].get("name"),
                    "user_id": document.get("user_id"),
                },
                new_collections[collection_name]: document.get(old_collections[collection_name]),
                "timestamp": document["timestamp"],
            }
            if unit:
                new_document[f"{new_collections[collection_name]}_unit"] = unit

            for existing_timestamp in buffer.keys():
                if abs(existing_timestamp - document["timestamp"]) <= timedelta(seconds=3):
                    buffer[existing_timestamp][new_collections[collection_name]] = document.get(
                        old_collections[collection_name]
                    )
                    if unit:
                        buffer[existing_timestamp][
                            f"{new_collections[collection_name]}_unit"
                        ] = unit
                    break
            else:
                buffer[document["timestamp"]] = new_document

    all_documents = sorted(buffer.values(), key=itemgetter("timestamp"))
    free_tier_collection = db["FreeTier"]
    for document in all_documents:
        free_tier_collection.insert_one(document)

    # Update the latest_timestamp after processing this chunk, to check if new data has been added.
    new_latest_timestamp = datetime.min
    for collection_name in collections_to_migrate:
        collection = db[collection_name]
        latest_document = collection.find_one(sort=[("timestamp", -1)])
        if latest_document and latest_document["timestamp"] > new_latest_timestamp:
            new_latest_timestamp = latest_document["timestamp"]

    # If there are new records added, the while loop will continue until there are no more records.
    latest_timestamp = new_latest_timestamp
    start_date = end_date

# db["Migration"].update_one({"migration_name": "FreeTier"}, {"$set": {"migration_complete": True}})
