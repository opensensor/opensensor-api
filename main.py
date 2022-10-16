from datetime import datetime
from decimal import Decimal

from fastapi import FastAPI, Path
from fastapi_pagination import Page, add_pagination
from fastapi_pagination.ext.pymongo import paginate

from pydantic import BaseModel

from opensensor.utils import get_open_sensor_db

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


class SensorMetaData(BaseModel):
    device_id: str
    name: str | None = None
    unit: str | None = None


class Temperature(BaseModel):
    temp: Decimal
    metadata: SensorMetaData | None = None


class TemperatureMeta(BaseModel):
    metadata: SensorMetaData
    temp: Temperature


class TemperaturesMeta(BaseModel):
    metadata: SensorMetaData
    results: list[Temperature]


class Humidity(BaseModel):
    rh: Decimal


class HumidityMeta(BaseModel):
    metadata: SensorMetaData
    rh: Humidity


class Environment(BaseModel):
    temp: Temperature | None = None
    rh: Humidity | None = None


class EnvironmentMeta(BaseModel):
    metadata: SensorMetaData
    environment: Environment


def _record_humidity_data(metadata: SensorMetaData, rh: Humidity):
    db = get_open_sensor_db()
    rhs = db.Humidity
    humidity_data = {
        "timestamp": datetime.utcnow(),
        "metadata": metadata.dict(),
        "rh": str(rh.rh),
    }
    rhs.insert_one(humidity_data)


def _record_temperature_data(metadata: SensorMetaData, temp: Temperature):
    db = get_open_sensor_db()
    temps = db.Temperature
    temp_data = {
        "timestamp": datetime.utcnow(),
        "metadata": metadata.dict(),
        "temp": str(temp.temp),
    }
    temps.insert_one(temp_data)


@app.post("/rh/", response_model=HumidityMeta)
async def record_humidity(metadata: SensorMetaData, rh: Humidity):
    _record_humidity_data(metadata, rh)
    return {"metadata": metadata, "rh": rh}


@app.post("/temp/", response_model=TemperatureMeta)
async def record_temperature(metadata: SensorMetaData, temp: Temperature):
    _record_temperature_data(metadata, temp)
    return {"metadata": metadata, "temp": temp}


@app.get("/temp/{device_id}", response_model=Page[Temperature])
async def historical_temperatures(
    device_id: str = Path(title="The ID of the device about which to retrieve historical data."),
):
    db = get_open_sensor_db()
    matching_data = paginate(
        db.Temperature,
        {"metadata.device_id": device_id},
        projection={"_id": False}
    )
    return matching_data


@app.post("/environment/", response_model=EnvironmentMeta)
async def record_environment(metadata: SensorMetaData, environment: Environment):
    if environment.temp:
        _record_temperature_data(metadata, environment.temp)
    if environment.rh:
        _record_humidity_data(metadata, environment.rh)
    return {"metadata": metadata, "environment": environment}


add_pagination(app)
