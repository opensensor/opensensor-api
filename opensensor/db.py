import os
from datetime import datetime

from bson import Binary
from pymongo import MongoClient

from opensensor.collections import DeviceMetadata
from opensensor.users import User


def get_mongo_connection():
    connection_str = os.environ.get("OPENSENSOR_DB") or ""
    client = MongoClient(connection_str)
    return client


def get_open_sensor_db():
    client = get_mongo_connection()
    db = client["default"]
    return db


def _record_data_point_to_ts_collection(
    collection,
    ts_column_name: str,
    device_metadata: DeviceMetadata,
    data_point,
    user: User = None,
):
    metadata = device_metadata.dict()
    metadata.pop("api_key", None)
    if user:
        metadata["user_id"] = Binary.from_uuid(user.fief_user_id)
    if hasattr(data_point, "unit"):
        metadata["unit"] = data_point.unit
    data = {
        "timestamp": datetime.utcnow(),
        "metadata": metadata,
        ts_column_name: str(getattr(data_point, ts_column_name)),
    }
    collection.insert_one(data)
