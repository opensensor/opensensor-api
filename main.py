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


class Temperature(BaseModel):
    temp: Decimal
    unit: str


class Humidity(BaseModel):
    rh: Decimal


class Environment(BaseModel):
    temp: Temperature | None = None
    rh: Humidity | None = None


def _get_sensor_ts_metadata(metadata: SensorMetaData):
    metadata = {"device_id": metadata.device_id, "name": metadata.name}
    return metadata


def _record_humidity_data(humidity: Humidity, metadata: SensorMetaData):
    db = get_open_sensor_db()
    rhs = db.Humidity
    humidity_data = {
        "timestamp": datetime.utcnow(),
        "metadata": _get_sensor_ts_metadata(metadata),
        "rh": str(humidity.rh),
    }
    rhs.insert_one(humidity_data)


def _record_temperature_data(temp: Temperature, metadata: SensorMetaData):
    db = get_open_sensor_db()
    temps = db.Temperature
    md = _get_sensor_ts_metadata(metadata)
    md["unit"] = temp.unit
    temp_data = {
        "timestamp": datetime.utcnow(),
        "metadata": md,
        "temp": str(temp.temp),
    }
    temps.insert_one(temp_data)


@app.post("/rh/")
async def record_humidity(humidity: Humidity, metadata: SensorMetaData):
    _record_humidity_data(humidity)
    return humidity


@app.post("/temp/")
async def record_temperature(temp: Temperature, metadata: SensorMetaData):
    _record_temperature_data(temp)
    return temp


@app.get("/temp/{device_id}")
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


@app.post("/environment/")
async def record_environment(environment: Environment, metadata: SensorMetaData):
    if environment.temp:
        _record_temperature_data(environment.temp, metadata)
    if environment.rh:
        _record_humidity_data(environment.rh, metadata)
