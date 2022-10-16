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
    metadata: SensorMetaData
    temp: Decimal


class Humidity(BaseModel):
    rh: Decimal
    metadata: SensorMetaData | None = None


class Environment(BaseModel):
    temp: Temperature | None = None
    rh: Humidity | None = None


def _record_humidity_data(rh: Humidity):
    db = get_open_sensor_db()
    rhs = db.Humidity
    humidity_data = {
        "timestamp": datetime.utcnow(),
        "metadata": rh.metadata.dict(),
        "rh": str(rh.rh),
    }
    rhs.insert_one(humidity_data)


def _record_temperature_data(temp: Temperature):
    db = get_open_sensor_db()
    temps = db.Temperature
    temp_data = {
        "timestamp": datetime.utcnow(),
        "metadata": temp.metadata.dict(),
        "temp": str(temp.temp),
    }
    temps.insert_one(temp_data)


@app.post("/rh/", response_model=Humidity)
async def record_humidity(metadata: SensorMetaData, rh: Humidity):
    _record_humidity_data(rh)
    return {"metadata": metadata, "rh": rh}


@app.post("/temp/", response_model=Temperature)
async def record_temperature(temp: Temperature):
    _record_temperature_data(temp)
    return {"temp": temp}


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


@app.post("/environment/", response_model=Environment)
async def record_environment(environment: Environment):
    if environment.temp:
        _record_temperature_data(environment.temp)
    if environment.rh:
        _record_humidity_data(environment.rh)
    return {"environment": environment}


add_pagination(app)
