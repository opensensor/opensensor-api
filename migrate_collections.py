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


# Function to create a composite key
def create_key(timestamp, metadata):
    return f"{timestamp}_{metadata['device_id']}_{metadata.get('name', 'NA')}_{metadata.get('user_id', 'NA')}"


while start_date <= datetime(2023, 11, 10):
    end_date = start_date + one_day
    buffer = {}

    print(start_date, end_date)

    for collection_name in collections_to_migrate:
        collection = db[collection_name]
        for document in collection.find({"timestamp": {"$gte": start_date, "$lt": end_date}}):
            unit = document["metadata"].get("unit")
            new_document = {
                "metadata": {
                    "device_id": document["metadata"]["device_id"],
                    "name": document["metadata"].get("name"),
                    "user_id": document["metadata"].get("user_id"),
                },
                new_collections[collection_name]: document.get(old_collections[collection_name]),
                "timestamp": document["timestamp"],
            }
            if unit:
                new_document[f"{new_collections[collection_name]}_unit"] = unit

            key = create_key(document["timestamp"], document["metadata"])

            if key in buffer:
                buffer[key][new_collections[collection_name]] = document.get(
                    old_collections[collection_name]
                )
                if unit:
                    buffer[key][f"{new_collections[collection_name]}_unit"] = unit
            else:
                buffer[key] = new_document

    all_documents = sorted(buffer.values(), key=itemgetter("timestamp"))

    # Insert the batch of documents for the current day
    if all_documents:
        db["FreeTier"].insert_many(all_documents)

    # Move to the next day
    start_date = end_date

db["Migration"].update_one({"migration_name": "FreeTier"}, {"$set": {"migration_complete": True}})
