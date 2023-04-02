import os
import uuid

import motor.motor_asyncio
from pydantic import Field
from pymongo import MongoClient


def get_motor_mongo_connection():
    connection_str = os.environ.get("OPENSENSOR_DB") or ""
    client = motor.motor_asyncio.AsyncIOMotorClient(connection_str, uuidRepresentation="standard")
    db = client["default"]
    return db


def get_mongo_connection():
    connection_str = os.environ.get("OPENSENSOR_DB") or ""
    client = MongoClient(connection_str)
    return client


def get_open_sensor_db():
    client = get_mongo_connection()
    db = client["default"]
    return db

