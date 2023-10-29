from datetime import datetime, timedelta
from operator import itemgetter

from opensensor.collection_apis import new_collections, old_collections
from opensensor.db import get_open_sensor_db

# Access the database
db = get_open_sensor_db()

collections_to_migrate = ["Temperature", "Humidity", "Pressure", "Lux", "CO2", "PH", "Moisture"]

migration = db.Migration.find_one({"migration_name": "FreeTier"})
if not migration:
    db["Migration"].insert_one({"migration_name": "FreeTier", "migration_complete": False})

earliest_timestamp = datetime(2023, 1, 1)
start_date = earliest_timestamp
one_day = timedelta(days=1)  # Change to one day

while start_date <= datetime(2023, 11, 10):
    end_date = start_date + one_day  # Use one day
    buffer = {}
    timestamps_set = set()  # For faster timestamp lookups
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

            found = False
            for existing_timestamp in timestamps_set:
                if abs(existing_timestamp - document["timestamp"]) <= timedelta(seconds=3):
                    buffer[existing_timestamp][new_collections[collection_name]] = document.get(
                        old_collections[collection_name]
                    )
                    if unit:
                        buffer[existing_timestamp][
                            f"{new_collections[collection_name]}_unit"
                        ] = unit
                    found = True
                    break

            if not found:
                buffer[document["timestamp"]] = new_document
                timestamps_set.add(document["timestamp"])

    all_documents = sorted(buffer.values(), key=itemgetter("timestamp"))

    if all_documents:  # Only insert if there are documents
        db["FreeTier"].insert_many(all_documents)

    start_date = end_date

db["Migration"].update_one({"migration_name": "FreeTier"}, {"$set": {"migration_complete": True}})
