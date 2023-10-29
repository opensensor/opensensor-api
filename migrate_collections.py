from datetime import datetime, timedelta
from operator import itemgetter

from opensensor.collection_apis import new_collections, old_collections
from opensensor.db import get_open_sensor_db

# Access the database
db = get_open_sensor_db()

collections_to_migrate = ["Temperature", "Humidity", "Pressure", "Lux", "CO2", "pH", "Moisture"]

migration = db.Migration.find_one({"migration_name": "FreeTier"})
if not migration:
    db["Migration"].insert_one({"migration_name": "FreeTier", "migration_complete": False})

earliest_timestamp = datetime(2023, 1, 1)
start_date = earliest_timestamp
one_day = timedelta(days=1)


TIME_WINDOW = timedelta(seconds=3)


def find_nearby_key(timestamp, metadata):
    for (key_time, key_device_id, key_name, key_user_id) in buffer.keys():
        if (
            key_device_id == metadata["device_id"]
            and key_name == metadata.get("name", "NA")
            and key_user_id == metadata.get("user_id", "NA")
            and abs(key_time - timestamp) <= TIME_WINDOW
        ):
            return (key_time, key_device_id, key_name, key_user_id)
    return None


while start_date <= datetime(2023, 11, 10):
    end_date = start_date + one_day
    buffer = {}

    print(start_date, end_date)

    for collection_name in collections_to_migrate:
        collection = db[collection_name]
        for document in collection.find({"timestamp": {"$gte": start_date, "$lt": end_date}}):
            unit = document["metadata"].get("unit")

            key = (
                document["timestamp"],
                document["metadata"]["device_id"],
                document["metadata"].get("name", "NA"),
                document["metadata"].get("user_id", "NA"),
            )
            nearby_key = find_nearby_key(document["timestamp"], document["metadata"])

            if nearby_key:
                key = nearby_key

            # Initialize the key if it doesn't exist yet in the buffer
            if key not in buffer:
                buffer[key] = {
                    "metadata": {
                        "device_id": document["metadata"]["device_id"],
                        "name": document["metadata"].get("name"),
                        "user_id": document["metadata"].get("user_id"),
                    },
                    "timestamp": key[0],  # first part of the key is the timestamp
                }

            buffer[key][new_collections[collection_name]] = document.get(
                old_collections[collection_name]
            )
            if unit:
                buffer[key][f"{new_collections[collection_name]}_unit"] = unit

    all_documents = sorted(buffer.values(), key=itemgetter("timestamp"))

    if all_documents:
        db["FreeTier"].insert_many(all_documents)

    start_date = end_date

db["Migration"].update_one({"migration_name": "FreeTier"}, {"$set": {"migration_complete": True}})
