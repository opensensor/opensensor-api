from datetime import datetime
from decimal import Decimal

from fastapi import FastAPI, Path
from pydantic import BaseModel

from opensensor.utils import get_open_sensor_db

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


class SensorMetaData(BaseModel):
    device_id: str
    name: str | None = None


class Temperature(SensorMetaData):
    temperature: Decimal
    unit: str


class Humidity(SensorMetaData):
    rh: Decimal


def _get_sensor_ts_metadata(data):
    metadata = {"device_id": data.device_id, "name": data.name}
    if hasattr(data, "unit"):
        metadata["unit"] = data.unit
    return metadata


def _record_temperature_data(temp: Temperature):
    db = get_open_sensor_db()
    temps = db.Temperature
    temp_data = {
        "timestamp": datetime.utcnow(),
        "metadata": _get_sensor_ts_metadata(temp),
        "temperature": str(temp.temperature),
    }
    temps.insert_one(temp_data)


@app.post("/temps/")
async def record_temperature(temp: Temperature):
    _record_temperature_data(temp)
    return temp


@app.get("/temps/{device_id}")
async def historical_temperatures(
    device_id: str = Path(title="The ID of the device about which to retrieve historical data."),
):
    db = get_open_sensor_db()
    temps = db.defaultTemp
    results = temps.find({"metadata.device_id": device_id}, {"_id": 0})
    data = []
    for temp in results:
        data.append(temp)
    return data
