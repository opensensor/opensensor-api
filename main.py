import os
from datetime import datetime
from decimal import Decimal

from fastapi import FastAPI, Path
from pydantic import BaseModel
from pymongo import MongoClient

app = FastAPI()


def _get_mongo_connection():
    connection_str = os.environ.get("OPENSENSOR_DB") or ""
    client = MongoClient(connection_str)
    return client


@app.get("/")
async def root():
    return {"message": "Hello World"}


class Temperature(BaseModel):
    device_id: str | None = None
    name: str | None = None
    temperature: Decimal | None
    unit: str | None = None


@app.post("/temps/")
async def record_temperature(temp: Temperature):
    client = _get_mongo_connection()
    db = client["default"]
    temps = db.defaultTemp
    temp_data = {
        "timestamp": datetime.utcnow(),
        "metadata": {"device_id": temp.device_id, "name": temp.name, "unit": temp.unit},
        "temperature": str(temp.temperature),
    }
    temps.insert_one(temp_data)
    return temp


@app.get("/temps/{device_id}")
async def historical_temperatures(
    device_id: str = Path(title="The ID of the device about which to retrieve historical data."),
):
    client = _get_mongo_connection()
    db = client["default"]
    temps = db.defaultTemp
    results = temps.find({"metadata.device_id": device_id}, {"_id": 0})
    data = []
    for temp in results:
        print(temp)
        data.append(temp)
    return data
