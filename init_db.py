import pymongo

from opensensor.db import get_open_sensor_db

# Script for creating the Time Series

db = get_open_sensor_db()
# try:
#     db.create_collection(
#         "Temperature",
#         timeseries={"timeField": "timestamp", "metaField": "metadata", "granularity": "minutes"},
#     )
# except pymongo.errors.CollectionInvalid:
#     print("Temperature collection Already exists, skipping ...")
#
# try:
#     db.create_collection(
#         "Humidity",
#         timeseries={"timeField": "timestamp", "metaField": "metadata", "granularity": "minutes"},
#     )
# except pymongo.errors.CollectionInvalid:
#     print("Humidity collection Already exists, skipping ...")
#
# try:
#     db.create_collection(
#         "Pressure",
#         timeseries={"timeField": "timestamp", "metaField": "metadata", "granularity": "minutes"},
#     )
# except pymongo.errors.CollectionInvalid:
#     print("Pressure collection Already exists, skipping ...")
#
# try:
#     db.create_collection(
#         "Lux",
#         timeseries={"timeField": "timestamp", "metaField": "metadata", "granularity": "minutes"},
#     )
# except pymongo.errors.CollectionInvalid:
#     print("Lux collection Already exists, skipping ...")
#
# try:
#     db.create_collection(
#         "CO2",
#         timeseries={"timeField": "timestamp", "metaField": "metadata", "granularity": "minutes"},
#     )
# except pymongo.errors.CollectionInvalid:
#     print("CO2 collection Already exists, skipping ...")
#
# try:
#     db.create_collection(
#         "Moisture",
#         timeseries={"timeField": "timestamp", "metaField": "metadata", "granularity": "minutes"},
#     )
# except pymongo.errors.CollectionInvalid:
#     print("Moisture collection Already exists, skipping ...")
#
# try:
#     db.create_collection(
#         "pH",
#         timeseries={"timeField": "timestamp", "metaField": "metadata", "granularity": "minutes"},
#     )
# except pymongo.errors.CollectionInvalid:
#     print("pH collection Already exists, skipping ...")

try:
    db.create_collection(
        "FreeTier",
        timeseries={"timeField": "timestamp", "metaField": "metadata", "granularity": "minutes"},
        expireAfterSeconds=8000000,
    )
except pymongo.errors.CollectionInvalid:
    print("Temperature collection Already exists, skipping ...")
